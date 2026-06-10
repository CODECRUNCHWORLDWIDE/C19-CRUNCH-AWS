/**
 * Exercise 3 — Prove zero NAT
 *
 * Goal: deploy a single EC2 instance into the ISOLATED subnet tier (no route to
 * the internet at all), reachable only via Session Manager, then prove that when
 * it reads from S3 and pulls from ECR, ZERO bytes cross the NAT Gateway — because
 * that traffic takes the VPC endpoints from Exercise 2.
 *
 * The instance has:
 *   - No public IP, no SSH key, in an isolated subnet (no NAT route).
 *   - An instance role with AmazonSSMManagedInstanceCore (so Session Manager
 *     works over the SSM interface endpoints), plus read on S3 and ECR.
 *
 * Because it's in the ISOLATED tier, if the endpoints were missing the instance
 * could not reach S3/ECR/SSM AT ALL — there's no NAT fallback. That's the whole
 * point: the isolated tier makes the proof airtight.
 *
 * Runnable CDK stack. Drop in `lib/private-host-stack.ts`, wire in bin, then:
 *
 *   npx cdk deploy CrunchNetworkStack CrunchEndpointsStack CrunchPrivateHostStack \
 *     --require-approval never
 *
 * The proof procedure is in the block comment at the bottom.
 */

import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';

export interface PrivateHostStackProps extends StackProps {
  readonly vpc: ec2.Vpc;
}

export class PrivateHostStack extends Stack {
  constructor(scope: Construct, id: string, props: PrivateHostStackProps) {
    super(scope, id, props);

    const { vpc } = props;

    // Instance role: Session Manager + read-only S3 and ECR for the proof.
    const role = new iam.Role(this, 'InstanceRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonS3ReadOnlyAccess'),
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          'AmazonEC2ContainerRegistryReadOnly',
        ),
      ],
    });

    // A security group with NO inbound rules — Session Manager is outbound-only
    // over the SSM endpoints, so the host needs nothing open inbound.
    const hostSg = new ec2.SecurityGroup(this, 'HostSg', {
      vpc,
      description: 'Isolated proof host — no inbound, egress to VPC only',
      allowAllOutbound: false,
    });
    // Allow HTTPS egress within the VPC so the host can reach the interface
    // endpoint ENIs. No 0.0.0.0/0 egress — there is no internet route anyway.
    hostSg.addEgressRule(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(443),
      'HTTPS to VPC endpoints',
    );

    const instance = new ec2.Instance(this, 'ProofHost', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO,
      ),
      // Amazon Linux 2023 ships the SSM agent and the AWS CLI v2 preinstalled.
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      role,
      securityGroup: hostSg,
      requireImdsv2: true,
      detailedMonitoring: false,
    });

    new CfnOutput(this, 'InstanceId', { value: instance.instanceId });
    new CfnOutput(this, 'AvailabilityZone', {
      value: instance.instanceAvailabilityZone,
    });
  }
}

/*
 * Wire it in bin/crunch-week04.ts:
 *
 *   const network = new NetworkStack(app, 'CrunchNetworkStack', { env });
 *   new EndpointsStack(app, 'CrunchEndpointsStack', { env, vpc: network.vpc });
 *   new PrivateHostStack(app, 'CrunchPrivateHostStack', { env, vpc: network.vpc });
 *
 * ---------------------------------------------------------------------------
 * THE PROOF
 * ---------------------------------------------------------------------------
 *
 * 0) Find your NAT Gateway id and the instance id:
 *
 *   VPC_ID=$(aws cloudformation describe-stacks --stack-name CrunchNetworkStack \
 *     --query "Stacks[0].Outputs[?OutputKey=='VpcId'].OutputValue" --output text)
 *   NAT_ID=$(aws ec2 describe-nat-gateways --filter "Name=vpc-id,Values=$VPC_ID" \
 *     --query "NatGateways[0].NatGatewayId" --output text)
 *   INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name CrunchPrivateHostStack \
 *     --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
 *   echo "NAT=$NAT_ID INSTANCE=$INSTANCE_ID"
 *
 * 1) Record the NAT baseline BEFORE generating any traffic:
 *
 *   aws cloudwatch get-metric-statistics --namespace AWS/NATGateway \
 *     --metric-name BytesOutToDestination \
 *     --dimensions Name=NatGatewayId,Value=$NAT_ID \
 *     --start-time "$(date -u -v-10M +%Y-%m-%dT%H:%M:%SZ)" \
 *     --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
 *     --period 300 --statistics Sum
 *
 * 2) Open a Session Manager shell (no SSH key, no bastion — rides the SSM
 *    interface endpoints from Exercise 2):
 *
 *   aws ssm start-session --target "$INSTANCE_ID"
 *
 *   It can take ~1-2 minutes after deploy for the instance to register with SSM.
 *   If it won't connect, your SSM/ssmmessages/ec2messages endpoints are missing
 *   or their security group blocks 443 — go back to Exercise 2.
 *
 * 3) Inside the session, generate AWS-service traffic. Reading from a public AWS
 *    S3 bucket in your region exercises the S3 GATEWAY endpoint:
 *
 *   # Confirm credentials resolve via the STS endpoint (no NAT):
 *   aws sts get-caller-identity
 *
 *   # Read a real object through the S3 gateway endpoint. Substitute any object
 *   # in a bucket you own in this region; even listing exercises the endpoint:
 *   aws s3 ls
 *
 *   # Pull a container image through the ECR API + DKR + S3 endpoints. Substitute
 *   # an image in YOUR account's ECR (push one first if you don't have one):
 *   ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
 *   REGION=us-east-1
 *   aws ecr get-login-password --region $REGION | \
 *     sudo docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com
 *   sudo docker pull $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/your-repo:latest
 *
 *   # Exit the session:
 *   exit
 *
 * 4) Query the NAT metric for the window you just ran. THIS IS THE PROOF:
 *
 *   aws cloudwatch get-metric-statistics --namespace AWS/NATGateway \
 *     --metric-name BytesOutToDestination \
 *     --dimensions Name=NatGatewayId,Value=$NAT_ID \
 *     --start-time "$(date -u -v-10M +%Y-%m-%dT%H:%M:%SZ)" \
 *     --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
 *     --period 300 --statistics Sum
 *
 *   Expected: every Sum datapoint is 0 (or a few hundred bytes of OS chatter).
 *   The multi-megabyte `docker pull` did NOT show up on the NAT, because it went
 *   through the endpoints.
 *
 * 5) The CONTRAST (optional but the most instructive step): temporarily remove
 *    the S3 gateway endpoint from Exercise 2's stack and redeploy, then repeat
 *    the docker pull. Now watch the SAME metric climb into the megabytes — that's
 *    the image layers going out the expensive door. Re-add the endpoint, redeploy,
 *    and the metric goes flat again. Run it both ways once; you'll never forget
 *    why the S3 endpoint matters behind ECR.
 *
 * Expected outcome: a CloudWatch result showing 0 NAT BytesOutToDestination while
 * a private, isolated host read S3 and pulled from ECR. The flat line is the deliverable.
 *
 * Teardown (do this — the NAT Gateway and the instance both bill):
 *
 *   npx cdk destroy CrunchPrivateHostStack CrunchEndpointsStack CrunchNetworkStack
 */
