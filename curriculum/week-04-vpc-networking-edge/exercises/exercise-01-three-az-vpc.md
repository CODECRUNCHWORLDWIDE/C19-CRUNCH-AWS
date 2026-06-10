# Exercise 1 — Build a Three-AZ VPC

**Goal:** Provision a production-shape VPC across three Availability Zones with **public**, **private (egress)**, and **isolated (no-egress)** subnets in each AZ, served by exactly **one** NAT Gateway. Then read the synthesized CloudFormation to understand what the L2 construct emitted, and verify the live topology with the AWS CLI.

**Estimated time:** 90 minutes.

---

## Setup

You need the project scaffold from the exercises README (`npx aws-cdk init app --language typescript`), a bootstrapped account/region, and the AWS CLI v2 configured with a role that can create VPC resources.

```bash
aws --version          # expect aws-cli/2.x
npx cdk --version      # expect 2.x
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1
```

---

## Step 1 — Write the network stack

Create `lib/network-stack.ts`:

```typescript
import { Stack, StackProps, CfnOutput, Tags } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

export class NetworkStack extends Stack {
  public readonly vpc: ec2.Vpc;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/16'),
      maxAzs: 3,
      // The cost decision: ONE NAT Gateway, not one per AZ.
      natGateways: 1,
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 20 },
        { name: 'private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 20 },
        { name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 20 },
      ],
    });

    Tags.of(this.vpc).add('Project', 'crunch-week04');

    new CfnOutput(this, 'VpcId', { value: this.vpc.vpcId });
    new CfnOutput(this, 'PublicSubnetIds', {
      value: this.vpc.publicSubnets.map((s) => s.subnetId).join(','),
    });
    new CfnOutput(this, 'IsolatedSubnetIds', {
      value: this.vpc.isolatedSubnets.map((s) => s.subnetId).join(','),
    });
  }
}
```

Wire it in `bin/crunch-week04.ts`:

```typescript
#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { NetworkStack } from '../lib/network-stack';

const app = new cdk.App();
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

new NetworkStack(app, 'CrunchNetworkStack', { env });
```

---

## Step 2 — Synthesize and count what you got

Before deploying, look at what the construct emits:

```bash
npx cdk synth CrunchNetworkStack > /tmp/synth.yaml
grep -c 'AWS::EC2::Subnet' /tmp/synth.yaml
grep -c 'AWS::EC2::RouteTable' /tmp/synth.yaml
grep -c 'AWS::EC2::NatGateway' /tmp/synth.yaml
grep -c 'AWS::EC2::InternetGateway' /tmp/synth.yaml
```

Expected:

```
9    # 3 AZs × 3 tiers
9    # one route table per subnet
1    # one NAT Gateway (because natGateways: 1)
1    # one Internet Gateway
```

Pause on that. **One** construct (`ec2.Vpc`) emitted roughly 40 CloudFormation resources: nine subnets, nine route tables, nine associations, routes, one IGW, one NAT Gateway, one Elastic IP, and the VPC itself. This is exactly the "L2 hides a lot" point from Lecture 1. If you had written this in raw CloudFormation or OpenTofu, you'd write every one of those by hand.

---

## Step 3 — Deploy

```bash
npx cdk deploy CrunchNetworkStack --require-approval never
```

It takes ~3–4 minutes (NAT Gateways are slow to provision). When it finishes you'll see the outputs:

```
Outputs:
CrunchNetworkStack.VpcId = vpc-0abc1234def567890
CrunchNetworkStack.PublicSubnetIds = subnet-0aaa...,subnet-0bbb...,subnet-0ccc...
CrunchNetworkStack.IsolatedSubnetIds = subnet-0ddd...,subnet-0eee...,subnet-0fff...
```

Save the VPC id:

```bash
export VPC_ID=$(aws cloudformation describe-stacks \
  --stack-name CrunchNetworkStack \
  --query "Stacks[0].Outputs[?OutputKey=='VpcId'].OutputValue" --output text)
echo "$VPC_ID"
```

---

## Step 4 — Verify the subnet topology with the CLI

Don't trust the console. Prove it:

```bash
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query "Subnets[].{AZ:AvailabilityZone,Cidr:CidrBlock,Public:MapPublicIpOnLaunch,Name:Tags[?Key=='aws-cdk:subnet-name']|[0].Value}" \
  --output table
```

You should see nine rows: three AZs, each with `public`, `private`, and `isolated`, with `/20` CIDRs and only the `public` rows showing `MapPublicIpOnLaunch: True`:

```
-------------------------------------------------------------------
|                         DescribeSubnets                         |
+--------------+-----------------+----------+----------------------+
|      AZ      |      Cidr       |  Public  |        Name          |
+--------------+-----------------+----------+----------------------+
|  us-east-1a  |  10.0.0.0/20    |  True    |  public              |
|  us-east-1a  |  10.0.48.0/20   |  False   |  private             |
|  us-east-1a  |  10.0.96.0/20   |  False   |  isolated            |
|  us-east-1b  |  10.0.16.0/20   |  True    |  public              |
|  ...         |  ...            |  ...     |  ...                 |
+--------------+-----------------+----------+----------------------+
```

---

## Step 5 — Read the route tables (the tier proof)

The tier is defined by the route table. Confirm each tier routes where Lecture 1 said it should.

```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query "RouteTables[].{Name:Tags[?Key=='aws-cdk:subnet-name']|[0].Value,Routes:Routes[].{Dest:DestinationCidrBlock,GW:GatewayId,NAT:NatGatewayId}}" \
  --output json
```

What you're verifying:

- **public** route tables have a `0.0.0.0/0 → igw-...` route.
- **private** route tables have a `0.0.0.0/0 → nat-...` route (all three private subnets point at the single NAT).
- **isolated** route tables have **only** the `local` route (`10.0.0.0/16 → local`) and no `0.0.0.0/0` at all.

If an isolated subnet has a default route, your tier is wrong — fix the `subnetConfiguration` and redeploy.

---

## Step 6 — Confirm there is exactly one NAT Gateway

```bash
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=$VPC_ID" \
  --query "NatGateways[].{Id:NatGatewayId,State:State,Subnet:SubnetId}" \
  --output table
```

Exactly **one** row. If you see three, you forgot `natGateways: 1` and you are now paying triple. Fix it and redeploy.

---

## Expected outcome

You have a live VPC with:

- 9 subnets (3 AZs × {public, private, isolated}), each `/20`.
- 1 Internet Gateway, 1 NAT Gateway, 1 Elastic IP.
- Public subnets routing to the IGW, private subnets routing to the single NAT, isolated subnets with no egress route.

The whole thing came from one `ec2.Vpc` construct plus a `natGateways: 1` override.

---

## Teardown

Leave it up if you're going straight into Exercise 2 (which extends this stack). Otherwise:

```bash
npx cdk destroy CrunchNetworkStack
```

The NAT Gateway and its Elastic IP are the billable parts — destroying the stack releases both.

---

## Hints

<details>
<summary>"cdk deploy" hangs for minutes on the NAT Gateway</summary>

That's normal — NAT Gateways take 2–4 minutes to provision and to delete. CloudFormation is waiting on the resource to reach `available`. Be patient; if it exceeds ~10 minutes, check the CloudFormation events tab for a stuck resource.
</details>

<details>
<summary>I only got 4 or 6 subnets, not 9</summary>

Your account may only expose two AZs in the region, or `maxAzs` is capped. Check `aws ec2 describe-availability-zones --query "AvailabilityZones[].ZoneName"`. Use a region with at least three AZs (us-east-1, us-west-2, eu-west-1 all qualify). With `maxAzs: 3` and three tiers you must get 9.
</details>

<details>
<summary>Why is the private subnet CIDR 10.0.48.0/20 and not 10.0.16.0/20?</summary>

CDK allocates subnet CIDRs per-AZ-then-per-tier in a way that interleaves them; the exact offsets depend on AZ count. The important properties are: every subnet is a `/20`, none overlap, and they all fit inside `10.0.0.0/16`. Don't memorize the offsets — verify the properties.
</details>
