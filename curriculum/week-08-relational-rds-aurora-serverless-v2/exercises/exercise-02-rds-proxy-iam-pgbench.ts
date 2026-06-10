// Exercise 2 — RDS Proxy + IAM database auth from an IRSA pod, then pgbench
//
// Goal: Put an RDS Proxy in front of the Exercise-1 Aurora cluster, enable
//       IAM database authentication END TO END, and connect from an
//       IRSA-bound EKS pod that holds ZERO long-lived database passwords —
//       the connection token is minted from the pod's IAM role at connect
//       time. Then run pgbench against the proxy's writer and reader
//       endpoints and read the TPS/latency numbers.
//
// Estimated time: 120 minutes.
//
// WHY THIS SHAPE
//
//   A Lambda fleet or a large EKS deployment opens far more connections than
//   Postgres `max_connections` allows. RDS Proxy multiplexes thousands of
//   client connections onto a small pool of backend connections (Lecture 1,
//   and resources.md "Using Amazon RDS Proxy"). IAM auth removes the password
//   entirely: the pod's IRSA role is allowed `rds-db:connect`, it mints a
//   15-minute token, and Postgres trusts it because the DB user was GRANTed
//   `rds_iam`. No password is ever stored in the pod, in a Secret, or in env.
//
// HOW TO USE THIS FILE
//
//   1. This is a runnable AWS CDK (TypeScript) stack. Drop it into the
//      `week8-aurora` app from Exercise 1 as `lib/week8-proxy-stack.ts`,
//      OR run it as its own app:
//
//        mkdir week8-proxy && cd week8-proxy
//        cdk init app --language typescript
//        npm install aws-cdk-lib constructs
//        # replace lib/week8-proxy-stack.ts with THIS FILE
//        # and reference it from bin/<app>.ts (see the bottom of this file)
//
//   2. It imports the existing cluster by identifier, so deploy Exercise 1
//      first (or pass the cluster in directly if you keep one app).
//
//   3. cdk deploy. Then run the Kubernetes manifest and pgbench commands in
//      the long comment block at the bottom.
//
// ACCEPTANCE CRITERIA
//
//   [ ] An RDS Proxy fronts the cluster with `iamAuth: REQUIRED`.
//   [ ] An IAM role exists that allows ONLY `rds-db:connect` to the proxy,
//       scoped to a specific DB user resource ARN (not "*").
//   [ ] The role's trust policy is an IRSA trust on the EKS OIDC provider,
//       scoped to one namespace + service account (not the whole cluster).
//   [ ] A `psql` connection from the pod succeeds with NO password set,
//       using a token from `aws rds generate-db-auth-token`.
//   [ ] `show rds.force_ssl;` returns 1 through the proxy (TLS end to end).
//   [ ] pgbench runs against the proxy writer endpoint and prints a TPS.
//   [ ] pgbench against the proxy READ-ONLY endpoint round-robins readers.
//   [ ] `cdk destroy` removes the proxy and the IAM role cleanly.

import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';

export interface Week8ProxyStackProps extends cdk.StackProps {
  /** The Aurora cluster identifier from Exercise 1, e.g. the physical id. */
  readonly clusterIdentifier: string;
  /** The Secrets Manager secret ARN holding the master credential. */
  readonly masterSecretArn: string;
  /** The VPC id the cluster lives in. */
  readonly vpcId: string;
  /** The security group id attached to the cluster. */
  readonly dbSecurityGroupId: string;
  /** The EKS cluster's OIDC provider URL, WITHOUT the https:// prefix,
   *  e.g. "oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539...". */
  readonly eksOidcProviderUrl: string;
  /** The EKS cluster's OIDC provider ARN. */
  readonly eksOidcProviderArn: string;
  /** Kubernetes namespace + service account the pod runs as. */
  readonly k8sNamespace: string;
  readonly k8sServiceAccount: string;
  /** The DB user the pod connects as (must be GRANTed rds_iam in Postgres). */
  readonly dbIamUser: string;
}

export class Week8ProxyStack extends cdk.Stack {
  public readonly proxyEndpoint: string;
  public readonly proxyReadEndpoint: string;
  public readonly irsaRoleArn: string;

  constructor(scope: Construct, id: string, props: Week8ProxyStackProps) {
    super(scope, id, props);

    // --- Import the existing cluster, VPC, and SG -------------------------
    const vpc = ec2.Vpc.fromLookup(this, 'Vpc', { vpcId: props.vpcId });
    const dbSg = ec2.SecurityGroup.fromSecurityGroupId(
      this,
      'DbSg',
      props.dbSecurityGroupId,
    );
    const masterSecret = secretsmanager.Secret.fromSecretCompleteArn(
      this,
      'MasterSecret',
      props.masterSecretArn,
    );
    const cluster = rds.DatabaseCluster.fromDatabaseClusterAttributes(this, 'Cluster', {
      clusterIdentifier: props.clusterIdentifier,
      // The reader/writer endpoints are resolved by the proxy; we only need
      // the identifier and SG to register the cluster as a proxy target.
    });

    // --- Security group for the proxy -------------------------------------
    // Clients (pods) -> proxy on 5432; proxy -> DB on 5432.
    const proxySg = new ec2.SecurityGroup(this, 'ProxySg', {
      vpc,
      description: 'RDS Proxy SG (Week 8)',
      allowAllOutbound: true,
    });
    // Proxy must reach the DB.
    dbSg.addIngressRule(proxySg, ec2.Port.tcp(5432), 'Proxy to Aurora');

    // --- The RDS Proxy ----------------------------------------------------
    // iamAuth REQUIRED forces every client to authenticate with an IAM token.
    // The proxy still authenticates to the DB using the master secret it holds.
    const proxy = new rds.DatabaseProxy(this, 'Proxy', {
      proxyTarget: rds.ProxyTarget.fromCluster(cluster),
      secrets: [masterSecret],
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [proxySg],
      iamAuth: true,                 // <-- IAM auth REQUIRED on the proxy
      requireTLS: true,              // TLS from client to proxy
      idleClientTimeout: cdk.Duration.minutes(30),
      maxConnectionsPercent: 90,     // pool may use up to 90% of max_connections
      maxIdleConnectionsPercent: 50,
      debugLogging: false,
    });

    // A separate READ-ONLY proxy endpoint so we can pgbench the readers.
    const readEndpoint = proxy.addEndpoint('ReadOnly', {
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [proxySg],
      targetRole: rds.ProxyEndpointTargetRole.READ_ONLY,
    });

    // --- The IRSA role the pod assumes ------------------------------------
    // Trust: the EKS OIDC provider, pinned to ONE namespace + service account.
    const oidcConditions = new cdk.CfnJson(this, 'OidcConditions', {
      value: {
        [`${props.eksOidcProviderUrl}:aud`]: 'sts.amazonaws.com',
        [`${props.eksOidcProviderUrl}:sub`]:
          `system:serviceaccount:${props.k8sNamespace}:${props.k8sServiceAccount}`,
      },
    });

    const irsaRole = new iam.Role(this, 'PgbenchIrsaRole', {
      roleName: 'week8-pgbench-irsa',
      assumedBy: new iam.FederatedPrincipal(
        props.eksOidcProviderArn,
        {
          StringEquals: oidcConditions,
        },
        'sts:AssumeRoleWithWebIdentity',
      ),
      description: 'IRSA role allowing rds-db:connect to the Week 8 proxy',
    });

    // --- The ONLY permission this role gets: rds-db:connect --------------
    // The resource ARN format is:
    //   arn:aws:rds-db:<region>:<account>:dbuser:<proxy-resource-id>/<db-user>
    // The proxy resource id (prx-...) is available after creation; we build
    // the ARN with the proxy's resourceId.
    irsaRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'AllowRdsDbConnect',
        effect: iam.Effect.ALLOW,
        actions: ['rds-db:connect'],
        resources: [
          cdk.Stack.of(this).formatArn({
            service: 'rds-db',
            resource: 'dbuser',
            resourceName: `${proxy.dbProxyName}/${props.dbIamUser}`,
            arnFormat: cdk.ArnFormat.SLASH_RESOURCE_NAME,
          }),
        ],
      }),
    );

    this.proxyEndpoint = proxy.endpoint;
    this.proxyReadEndpoint = readEndpoint.endpoint;
    this.irsaRoleArn = irsaRole.roleArn;

    new cdk.CfnOutput(this, 'ProxyEndpoint', { value: this.proxyEndpoint });
    new cdk.CfnOutput(this, 'ProxyReadEndpoint', { value: this.proxyReadEndpoint });
    new cdk.CfnOutput(this, 'IrsaRoleArn', { value: this.irsaRoleArn });
    new cdk.CfnOutput(this, 'ProxySgId', { value: proxySg.securityGroupId });
  }
}

// ---------------------------------------------------------------------------
// bin/<app>.ts — wire the stack (fill in the values from Exercise 1 + EKS):
// ---------------------------------------------------------------------------
//
//   #!/usr/bin/env node
//   import * as cdk from 'aws-cdk-lib';
//   import { Week8ProxyStack } from '../lib/week8-proxy-stack';
//
//   const app = new cdk.App();
//   new Week8ProxyStack(app, 'Week8ProxyStack', {
//     env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'us-east-1' },
//     clusterIdentifier:  'week8aurorastack-auroraXXXX',          // from Ex1
//     masterSecretArn:    'arn:aws:secretsmanager:...:week8/aurora/master-XXXX',
//     vpcId:              'vpc-0abc123',
//     dbSecurityGroupId:  'sg-0db123',
//     eksOidcProviderUrl: 'oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539...',
//     eksOidcProviderArn: 'arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539...',
//     k8sNamespace:       'data',
//     k8sServiceAccount:  'pgbench',
//     dbIamUser:          'app_iam',
//   });
//
// ---------------------------------------------------------------------------
// STEP A — Create the IAM-auth DB user in Postgres (one time, as the master)
// ---------------------------------------------------------------------------
//
//   -- connect to the writer endpoint as crunchadmin (Exercise 1, Step 7):
//   CREATE USER app_iam;                    -- no password
//   GRANT rds_iam TO app_iam;               -- this user authenticates via IAM
//   GRANT ALL PRIVILEGES ON DATABASE appdb TO app_iam;
//   \c appdb
//   GRANT ALL ON SCHEMA public TO app_iam;
//
//   A user GRANTed rds_iam CANNOT log in with a password — only with a token.
//
// ---------------------------------------------------------------------------
// STEP B — The Kubernetes ServiceAccount + Pod (IRSA)
// ---------------------------------------------------------------------------
// Save as pgbench-pod.yaml, substitute the IrsaRoleArn output, then:
//   kubectl create namespace data
//   kubectl apply -f pgbench-pod.yaml
//
//   apiVersion: v1
//   kind: ServiceAccount
//   metadata:
//     name: pgbench
//     namespace: data
//     annotations:
//       eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/week8-pgbench-irsa
//   ---
//   apiVersion: v1
//   kind: Pod
//   metadata:
//     name: pgbench
//     namespace: data
//   spec:
//     serviceAccountName: pgbench            # <-- binds the IRSA role to the pod
//     containers:
//       - name: pgbench
//         image: postgres:16                 # ships psql + pgbench
//         command: ["sleep", "infinity"]
//         env:
//           - name: AWS_REGION
//             value: us-east-1
//
//   The pod gets AWS_ROLE_ARN + AWS_WEB_IDENTITY_TOKEN_FILE injected by the
//   EKS pod-identity webhook. No AWS keys, no DB password.
//
// ---------------------------------------------------------------------------
// STEP C — Connect passwordlessly from the pod (the payoff)
// ---------------------------------------------------------------------------
//   kubectl exec -it -n data pgbench -- bash
//
//   # inside the pod:
//   apt-get update && apt-get install -y awscli jq >/dev/null     # if not present
//   PROXY=<ProxyEndpoint output>
//   export PGSSLMODE=require
//   # Mint a 15-minute IAM auth token from the pod's IRSA role:
//   export PGPASSWORD="$(aws rds generate-db-auth-token \
//        --hostname "$PROXY" --port 5432 --username app_iam --region us-east-1)"
//   psql "host=$PROXY dbname=appdb user=app_iam" \
//        -c "select current_user, inet_server_addr();" \
//        -c "show rds.force_ssl;"
//
//   Expected: current_user = app_iam, rds.force_ssl = 1, and you typed NO
//   stored password — PGPASSWORD held a short-lived token, not a secret.
//
// ---------------------------------------------------------------------------
// STEP D — pgbench the writer through the proxy
// ---------------------------------------------------------------------------
//   # initialize a scale-10 dataset (~150 MB) ONE TIME:
//   pgbench -i -s 10 "host=$PROXY dbname=appdb user=app_iam"
//
//   # run: 16 clients, 4 threads, 60 seconds, TPC-B-like default script
//   pgbench -c 16 -j 4 -T 60 "host=$PROXY dbname=appdb user=app_iam"
//
//   Expected (numbers vary by instance class and proxy pool):
//     scaling factor: 10
//     number of clients: 16
//     number of threads: 4
//     duration: 60 s
//     latency average = 5.412 ms
//     tps = 2956.84 (without initial connection time)
//
// ---------------------------------------------------------------------------
// STEP E — pgbench the READERS through the read-only proxy endpoint
// ---------------------------------------------------------------------------
//   READ=<ProxyReadEndpoint output>
//   export PGPASSWORD="$(aws rds generate-db-auth-token \
//        --hostname "$READ" --port 5432 --username app_iam --region us-east-1)"
//   # -S = SELECT-only (read) workload; safe against the read-only endpoint:
//   pgbench -S -c 32 -j 8 -T 60 "host=$READ dbname=appdb user=app_iam"
//
//   Open two such runs and watch the ReadIOPS metric split across BOTH
//   readers in the RDS console — the read-only proxy endpoint round-robins
//   connections across the reader fleet (Lecture 1 §1.7).
//
// ---------------------------------------------------------------------------
// STEP F — Tear down (required)
// ---------------------------------------------------------------------------
//   kubectl delete -f pgbench-pod.yaml
//   cdk destroy Week8ProxyStack          # removes proxy + IRSA role
//   # leave the cluster up only if going straight to Exercise 3.
//
// ---------------------------------------------------------------------------
// HINTS
// ---------------------------------------------------------------------------
//   - "PAM authentication failed for user app_iam": you did not GRANT rds_iam
//     to the user (Step A), or you connected with sslmode=disable. IAM auth
//     requires TLS.
//   - "no pg_hba.conf entry ... SSL off": set PGSSLMODE=require.
//   - "is not authorized to perform: rds-db:connect": the resource ARN in the
//     IAM policy must use the PROXY resource id (prx-...) for proxy auth, and
//     the db-user must match the --username you pass. Check the dbuser ARN.
//   - Token expired mid-run: tokens last 15 minutes. pgbench opens its
//     connections at the start, so a 60s run is fine; for long runs, RDS Proxy
//     keeps the backend pool warm, but re-mint the token for each new psql.
//   - Pinning: if the proxy logs show "pinned" sessions, you used a session
//     feature (SET, advisory lock, temp table) that forces a dedicated backend
//     connection. The default pgbench script does not pin; custom scripts might.
