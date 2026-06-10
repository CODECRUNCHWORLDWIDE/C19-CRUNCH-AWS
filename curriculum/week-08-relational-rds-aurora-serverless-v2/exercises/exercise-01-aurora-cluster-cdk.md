# Exercise 1 — Stand up an Aurora PostgreSQL cluster via CDK

**Goal:** From a blank CDK app, provision a production-shaped Aurora PostgreSQL cluster — **one writer + two readers across three AZs** — that is KMS-encrypted at rest, TLS-enforced in transit, uses a **custom DB cluster parameter group**, has **Performance Insights** on, and stores its master credential in **Secrets Manager** (managed rotation). Deploy it, inspect the three endpoint kinds from Lecture 1, connect with `psql` over TLS, and tear it down clean.

**Estimated time:** 120 minutes.

This is the foundation for Exercises 2 and 3 and for the mini-project. Build it like you mean it.

---

## Setup

You need the prerequisites from `exercises/README.md` (Node 20+, CDK 2.150+, `psql` 16+) and a `cdk bootstrap`-ed `dev` account. Scaffold a fresh app:

```bash
mkdir week8-aurora && cd week8-aurora
cdk init app --language typescript
npm install aws-cdk-lib constructs
```

CDK pins `aws-cdk-lib` for you; confirm it is 2.150 or newer:

```bash
npm ls aws-cdk-lib
```

---

## Step 1 — The VPC (reuse Week 4, or use the fallback)

Aurora must live in private/isolated subnets across **at least three AZs** so the writer and the two readers each land in a different AZ. If your Week-4 VPC is up, look it up by name; otherwise the stack below creates a minimal three-AZ VPC.

Open `lib/week8-aurora-stack.ts` and replace its contents with the following. Read every line — this is the stack you are responsible for.

```typescript
import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as kms from 'aws-cdk-lib/aws-kms';

export class Week8AuroraStack extends cdk.Stack {
  public readonly cluster: rds.DatabaseCluster;
  public readonly vpc: ec2.IVpc;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // --- Network -----------------------------------------------------------
    // Three AZs so writer + 2 readers each land in a distinct AZ.
    // ISOLATED subnets: the database needs no outbound internet.
    this.vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 3,
      natGateways: 0, // no NAT — the DB does not egress to the internet
      subnetConfiguration: [
        { name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });
```

> **Hint — reuse your Week-4 VPC instead.** Swap the `new ec2.Vpc(...)` block for `ec2.Vpc.fromLookup(this, 'Vpc', { vpcName: 'week4-vpc' })`. Lookups require an account/region context, so set `env: { account, region }` on the stack props (see Step 6). Using the real VPC avoids a NAT-free isolated VPC that cannot reach VPC endpoints you have not added — for this exercise the isolated fallback is fine because the DB needs no egress.

---

## Step 2 — The encryption key and the parameter group

Continue in the same constructor. A customer-managed KMS key (so you control rotation and the key policy), and a **DB cluster parameter group** that forces SSL and turns on `pg_stat_statements`:

```typescript
    // --- Encryption at rest ------------------------------------------------
    const key = new kms.Key(this, 'AuroraKmsKey', {
      enableKeyRotation: true,
      alias: 'alias/week8-aurora',
      description: 'CMK for the Week 8 Aurora cluster',
      removalPolicy: cdk.RemovalPolicy.DESTROY, // dev only — RETAIN in prod
    });

    // --- DB cluster parameter group ---------------------------------------
    // rds.force_ssl=1 rejects non-TLS connections (Lecture 1 §1.8).
    // pg_stat_statements gives us the open-source comparator to Perf Insights.
    const parameterGroup = new rds.ParameterGroup(this, 'ClusterParams', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_6,
      }),
      description: 'Week 8 Aurora PG16 cluster parameters',
      parameters: {
        'rds.force_ssl': '1',
        shared_preload_libraries: 'pg_stat_statements',
        'pg_stat_statements.track': 'all',
        log_min_duration_statement: '500', // log statements slower than 500ms
      },
    });
```

---

## Step 3 — The cluster: one writer + two readers across three AZs

This is the heart of the exercise. The `writer` is one provisioned instance; `readers` is an array of two more, each told to live in a different AZ via the cluster's subnet placement. Performance Insights is enabled per instance.

```typescript
    // --- The cluster -------------------------------------------------------
    this.cluster = new rds.DatabaseCluster(this, 'Aurora', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_6,
      }),
      vpc: this.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      parameterGroup,
      storageEncrypted: true,
      storageEncryptionKey: key,
      // Master credential -> Secrets Manager with managed rotation.
      credentials: rds.Credentials.fromGeneratedSecret('crunchadmin', {
        secretName: 'week8/aurora/master',
      }),
      defaultDatabaseName: 'appdb',
      backup: { retention: cdk.Duration.days(7) },
      // 1 writer + 2 readers. Aurora spreads them across the 3 AZs.
      writer: rds.ClusterInstance.provisioned('writer', {
        instanceType: ec2.InstanceType.of(ec2.InstanceClass.R7G, ec2.InstanceSize.LARGE),
        enablePerformanceInsights: true,
        performanceInsightRetention: rds.PerformanceInsightRetention.DEFAULT, // free 7 days
      }),
      readers: [
        rds.ClusterInstance.provisioned('reader1', {
          instanceType: ec2.InstanceType.of(ec2.InstanceClass.R7G, ec2.InstanceSize.LARGE),
          enablePerformanceInsights: true,
          // promotionTier 1 -> promoted before tier-2 readers on failover
          promotionTier: 1,
        }),
        rds.ClusterInstance.provisioned('reader2', {
          instanceType: ec2.InstanceType.of(ec2.InstanceClass.R7G, ec2.InstanceSize.LARGE),
          enablePerformanceInsights: true,
          promotionTier: 2,
        }),
      ],
      cloudwatchLogsExports: ['postgresql'],
      removalPolicy: cdk.RemovalPolicy.DESTROY, // dev only
    });

    // --- Outputs -----------------------------------------------------------
    new cdk.CfnOutput(this, 'WriterEndpoint', {
      value: this.cluster.clusterEndpoint.hostname,
    });
    new cdk.CfnOutput(this, 'ReaderEndpoint', {
      value: this.cluster.clusterReadEndpoint.hostname,
    });
    new cdk.CfnOutput(this, 'SecretArn', {
      value: this.cluster.secret!.secretArn,
    });
  }
}
```

---

## Step 4 — Wire the stack into the app

Open `bin/week8-aurora.ts` and make it deploy to your `dev` account/region explicitly (required if you used `fromLookup` in Step 1):

```typescript
#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { Week8AuroraStack } from '../lib/week8-aurora-stack';

const app = new cdk.App();
new Week8AuroraStack(app, 'Week8AuroraStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
  },
});
```

---

## Step 5 — Synthesize, then deploy

Always look at the CloudFormation before you deploy. `cdk synth` shows you the `AWS::RDS::DBCluster`, three `AWS::RDS::DBInstance`s, the KMS key, and the parameter group:

```bash
cdk synth | head -60
cdk diff
cdk deploy
```

The deploy takes **10–15 minutes** (Aurora cluster + 3 instances is slow to create). When it finishes you will see the outputs:

```
Week8AuroraStack.WriterEndpoint = week8aurorastack-aurora....cluster-abc123.us-east-1.rds.amazonaws.com
Week8AuroraStack.ReaderEndpoint = week8aurorastack-aurora....cluster-ro-abc123.us-east-1.rds.amazonaws.com
Week8AuroraStack.SecretArn      = arn:aws:secretsmanager:us-east-1:...:secret:week8/aurora/master-xxxxx
```

---

## Step 6 — Inspect the architecture you built

Confirm the writer/reader split and that all three instances are in different AZs:

```bash
aws rds describe-db-clusters \
  --query 'DBClusters[?starts_with(DBClusterIdentifier, `week8`)].DBClusterMembers[].{Id:DBInstanceIdentifier,Writer:IsClusterWriter,Tier:PromotionTier}'

aws rds describe-db-instances \
  --query 'DBInstances[?starts_with(DBInstanceIdentifier, `week8`)].{Id:DBInstanceIdentifier,AZ:AvailabilityZone,PI:PerformanceInsightsEnabled}'
```

Expected (AZs will be three distinct ones in your region):

```json
[
  { "Id": "writer",  "AZ": "us-east-1a", "PI": true },
  { "Id": "reader1", "AZ": "us-east-1b", "PI": true },
  { "Id": "reader2", "AZ": "us-east-1c", "PI": true }
]
```

If two instances landed in the same AZ, your VPC has fewer than three AZs with isolated subnets — fix `maxAzs: 3`.

---

## Step 7 — Connect over TLS

Pull the generated password from Secrets Manager and connect to the **writer** endpoint. The `rds.force_ssl=1` parameter means a non-TLS connection is rejected.

```bash
SECRET_ARN=$(aws cloudformation describe-stacks --stack-name Week8AuroraStack \
  --query 'Stacks[0].Outputs[?OutputKey==`SecretArn`].OutputValue' --output text)
WRITER=$(aws cloudformation describe-stacks --stack-name Week8AuroraStack \
  --query 'Stacks[0].Outputs[?OutputKey==`WriterEndpoint`].OutputValue' --output text)

PGPASSWORD=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" \
  --query SecretString --output text | jq -r .password)

# From inside the VPC (e.g. a bastion or an EKS pod) — the DB is in isolated subnets:
PGSSLMODE=require psql "host=$WRITER dbname=appdb user=crunchadmin" \
  -c "select version();" \
  -c "show rds.force_ssl;" \
  -c "select count(*) from pg_stat_statements;"
```

> **Hint — "connection timed out."** The cluster is in **isolated** subnets with no public access. You must run `psql` from inside the VPC: an EC2 bastion, an SSM Session Manager session, or (as in Exercise 2) an EKS pod. If you need a quick bastion, the `<details>` block below has a one-liner.

<details>
<summary>Quick SSM-managed bastion (no SSH key, no public IP)</summary>

```bash
# Launch a t3.micro in a private subnet with the SSM agent, then:
aws ssm start-session --target i-0yourbastion
# inside the session, install psql and connect to $WRITER as above.
```

A cleaner option is to skip the bastion entirely and do all `psql`/`pgbench` work from the EKS pod you set up in Exercise 2 — that is the intended path.

</details>

Expected output:

```
                 version
------------------------------------------
 PostgreSQL 16.6 on aarch64-... Aurora ...
 rds.force_ssl
---------------
 1
 count
-------
     0
```

---

## Acceptance criteria

Mark this exercise done when:

- [ ] `cdk deploy` succeeds with **0 errors** and emits the three outputs.
- [ ] `describe-db-clusters` shows **one writer and exactly two readers**, with promotion tiers 1 and 2 on the readers.
- [ ] `describe-db-instances` shows the three instances in **three distinct AZs**, all with `PerformanceInsightsEnabled: true`.
- [ ] A `PGSSLMODE=disable` connection is **rejected** and a `PGSSLMODE=require` connection **succeeds** (proves `rds.force_ssl=1`).
- [ ] The cluster is **KMS-encrypted** (`describe-db-clusters` shows `StorageEncrypted: true` and your CMK ARN).
- [ ] The master password came from **Secrets Manager**, not a hard-coded string anywhere in your code.
- [ ] You can explain, in your own words, why the cluster (writer) endpoint and reader endpoint are different CNAMEs (Lecture 1 §1.7).

---

## Step 8 — Tear down (required)

Aurora bills while it idles. Tear it down before you walk away:

```bash
cdk destroy Week8AuroraStack
```

```
Week8AuroraStack: destroying... [1/1]
 ✅  Week8AuroraStack: destroyed
```

> **Keep it up only if you are going straight into Exercise 2**, which extends this exact cluster. If you are stopping for the day, destroy it — Exercise 2 redeploys in 15 minutes.

Confirm nothing billable is left:

```bash
aws rds describe-db-clusters --query 'DBClusters[?starts_with(DBClusterIdentifier, `week8`)].DBClusterIdentifier'
# []  <- empty array means clean
```

---

## Stretch

- Add a **custom endpoint** that load-balances across only the two readers, and confirm it appears in `describe-db-cluster-endpoints`.
- Switch the cluster to **Aurora I/O-Optimized** (`storageType: rds.DBClusterStorageType.AURORA_IOPT1`) and note the parameter on the cluster. You will use this in the challenge's I/O cost discussion.
- Re-implement the whole stack in **Python CDK** and `cdk diff` the two synthesized templates — they should be byte-identical CloudFormation.

When the cluster is up and you can connect over TLS, move to [Exercise 2 — RDS Proxy + IAM auth + pgbench](exercise-02-rds-proxy-iam-pgbench.ts).
