# Exercise 1 — A TS CDK App: VPC + KMS-encrypted S3 + Lambda

**Goal:** Scaffold a CDK app in TypeScript from a blank folder, build a stack with a VPC, a KMS-encrypted S3 bucket with lifecycle rules, and a Lambda that reads from the bucket with least-privilege IAM. Synthesize the CloudFormation, read it, and deploy — to LocalStack for free, then optionally to real `dev`.

**Estimated time:** 90 minutes.

---

## Setup

You need:

```bash
node --version        # v20.x or newer
npm --version
aws --version         # aws-cli/2.x
docker --version      # for asset bundling and LocalStack
```

Install the CDK CLI globally (or use `npx cdk` everywhere):

```bash
npm install -g aws-cdk
cdk --version
# 2.x.y (build ...)
```

You should have a `crunch-dev` AWS profile from Week 1 that you can assume with `aws sso login --profile crunch-dev`. Confirm:

```bash
aws sts get-caller-identity --profile crunch-dev
```

---

## Step 0 — See the substrate by hand (10 min)

Before CDK hides CloudFormation, deploy a trivial template by hand so you have seen the raw machinery once. Create `bucket.yaml`:

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: One bucket, deployed without any CDK.
Resources:
  DemoBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Delete
    Properties:
      VersioningConfiguration:
        Status: Enabled
Outputs:
  BucketName:
    Value: !Ref DemoBucket
```

Deploy and inspect, then tear it down:

```bash
aws cloudformation deploy --template-file bucket.yaml \
  --stack-name hand-rolled --profile crunch-dev
aws cloudformation describe-stacks --stack-name hand-rolled \
  --query "Stacks[0].Outputs" --profile crunch-dev
aws cloudformation delete-stack --stack-name hand-rolled --profile crunch-dev
```

That is the substrate. Everything below generates exactly this kind of document — just more of it.

---

## Step 1 — Scaffold the CDK app

```bash
mkdir crunch-iac-ts && cd crunch-iac-ts
cdk init app --language=typescript
```

`cdk init` lays down a complete project. Read every file it created — you will work with all of them:

```
crunch-iac-ts/
├── bin/crunch-iac-ts.ts          # the App entry point (instantiates your stack)
├── lib/crunch-iac-ts-stack.ts    # your stack definition (mostly empty)
├── cdk.json                      # CDK config: how to run the app, feature flags
├── package.json
├── tsconfig.json
└── test/                         # a jest test scaffold
```

Build and synth the empty stack to confirm the toolchain works:

```bash
npm run build
cdk synth
```

`cdk synth` prints a near-empty CloudFormation template (just CDK metadata). Good — the loop works.

---

## Step 2 — Create the Lambda handler

CDK bundles your Lambda code as an asset. Create the handler at `lambda/read_object.py`:

```python
import json
import os

import boto3

s3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]


def handler(event, _context):
    """Read a key from the bucket and return its size and first 200 bytes."""
    key = event.get("key", "hello.txt")
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    body = obj["Body"].read()
    return {
        "statusCode": 200,
        "bucket": BUCKET,
        "key": key,
        "size": len(body),
        "preview": body[:200].decode("utf-8", errors="replace"),
    }
```

This handler reads an object from the bucket — which is exactly the access we will grant with one line of CDK.

---

## Step 3 — Write the stack

Replace the contents of `lib/crunch-iac-ts-stack.ts`:

```typescript
import {
  Stack,
  StackProps,
  Duration,
  RemovalPolicy,
  CfnOutput,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Key } from 'aws-cdk-lib/aws-kms';
import {
  Bucket,
  BucketEncryption,
  BlockPublicAccess,
  StorageClass,
} from 'aws-cdk-lib/aws-s3';
import { Vpc, IpAddresses, SubnetType } from 'aws-cdk-lib/aws-ec2';
import { Function as LambdaFunction, Runtime, Code } from 'aws-cdk-lib/aws-lambda';

export class CrunchIacTsStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // --- VPC: two AZs, public + isolated subnets, NO NAT Gateway (cost discipline). ---
    const vpc = new Vpc(this, 'Vpc', {
      ipAddresses: IpAddresses.cidr('10.42.0.0/16'),
      maxAzs: 2,
      natGateways: 0, // deliberately zero — NAT is the silent budget killer
      subnetConfiguration: [
        { name: 'public', subnetType: SubnetType.PUBLIC, cidrMask: 24 },
        { name: 'isolated', subnetType: SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // --- KMS customer-managed key with rotation. ---
    const key = new Key(this, 'DataKey', {
      enableKeyRotation: true,
      description: 'CMK for the Crunch IaC starter data bucket',
      removalPolicy: RemovalPolicy.DESTROY, // dev only; RETAIN in prod
    });

    // --- S3 bucket: KMS-encrypted, versioned, locked down, with lifecycle rules. ---
    const bucket = new Bucket(this, 'Data', {
      encryption: BucketEncryption.KMS,
      encryptionKey: key,
      bucketKeyEnabled: true, // reduce KMS API calls / cost
      enforceSSL: true,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      removalPolicy: RemovalPolicy.DESTROY, // dev only; RETAIN in prod
      autoDeleteObjects: true, // dev only; lets `cdk destroy` empty the bucket
      lifecycleRules: [
        {
          id: 'tier-and-expire',
          transitions: [
            { storageClass: StorageClass.INFREQUENT_ACCESS, transitionAfter: Duration.days(30) },
          ],
          expiration: Duration.days(365),
          noncurrentVersionExpiration: Duration.days(90),
        },
      ],
    });

    // --- Lambda that reads from the bucket. ---
    const reader = new LambdaFunction(this, 'Reader', {
      runtime: Runtime.PYTHON_3_12,
      handler: 'read_object.handler',
      code: Code.fromAsset('lambda'),
      timeout: Duration.seconds(15),
      environment: { BUCKET_NAME: bucket.bucketName },
      vpc,
      vpcSubnets: { subnetType: SubnetType.PRIVATE_ISOLATED },
    });

    // --- The one line that writes least-privilege IAM for you. ---
    // grantRead adds s3:GetObject/List* scoped to this bucket AND kms:Decrypt on the key.
    bucket.grantRead(reader);

    // --- Outputs so you can find your resources after deploy. ---
    new CfnOutput(this, 'BucketName', { value: bucket.bucketName });
    new CfnOutput(this, 'KeyArn', { value: key.keyArn });
    new CfnOutput(this, 'FunctionName', { value: reader.functionName });
  }
}
```

Update `bin/crunch-iac-ts.ts` so the stack has an explicit environment (you need this for `Vpc` to resolve AZs at synth):

```typescript
#!/usr/bin/env node
import 'source-map-files';
import * as cdk from 'aws-cdk-lib';
import { CrunchIacTsStack } from '../lib/crunch-iac-ts-stack';

const app = new cdk.App();
new CrunchIacTsStack(app, 'CrunchIacTsStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
  },
});
```

> If `cdk init` generated `import 'source-map-support/register';` keep that line instead — just ensure the imports compile. The exact first import line varies by CDK version; the rest of the file is what matters.

---

## Step 4 — Synth and read the template

```bash
npm run build
cdk synth > template.json
```

Open `cdk.out/CrunchIacTsStack.template.json`. Find and read these, because they are the payoff of the `grant*` line:

- The `AWS::KMS::Key` with `EnableKeyRotation: true`.
- The `AWS::S3::Bucket` with `BucketEncryption` referencing the key, `PublicAccessBlockConfiguration` all-true, and a `LifecycleConfiguration`.
- An `AWS::S3::BucketPolicy` denying `s3:*` when `aws:SecureTransport` is `false` (that is what `enforceSSL` generated).
- The Lambda's IAM **role policy**: search for `s3:GetObject` and confirm the `Resource` is scoped to your bucket ARN and `bucket/*` — and that there is a `kms:Decrypt` statement scoped to your key ARN. **You did not write that by hand. `grantRead` did.**

Count the resources:

```bash
cdk synth | grep -c "Type: AWS::"
```

You will see a couple dozen — the VPC alone expands into subnets, route tables, and an internet gateway. This is the L2 leverage: ~70 lines of TypeScript become hundreds of lines of CloudFormation.

---

## Step 5 — Deploy to LocalStack (free path)

Install the LocalStack CDK wrapper and start LocalStack:

```bash
npm install -g aws-cdk-local
docker run --rm -d --name localstack -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  localstack/localstack:latest
```

Bootstrap and deploy against LocalStack with `cdklocal` (it points CDK at `localhost:4566` for you):

```bash
cdklocal bootstrap
cdklocal deploy --require-approval never
```

You will see CloudFormation events stream by and the outputs print at the end:

```
Outputs:
CrunchIacTsStack.BucketName = crunchiactsstack-databucket-...
CrunchIacTsStack.FunctionName = CrunchIacTsStack-Reader...
CrunchIacTsStack.KeyArn = arn:aws:kms:us-east-1:000000000000:key/...
```

Put an object in the emulated bucket and confirm it is there:

```bash
BUCKET=$(cdklocal synth --quiet >/dev/null; aws --endpoint-url=http://localhost:4566 s3 ls | awk '/databucket/{print $3}')
echo "hello from localstack" | aws --endpoint-url=http://localhost:4566 s3 cp - "s3://$BUCKET/hello.txt"
aws --endpoint-url=http://localhost:4566 s3 ls "s3://$BUCKET/"
```

(You invoke the Lambda against this bucket in the Friday challenge with `sam local invoke`.)

---

## Step 6 — (Optional) Deploy to real `dev`

If you want to see the real thing, bootstrap your `dev` account once and deploy. This is the only step that costs real money — pennies, if you destroy after.

```bash
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text --profile crunch-dev)
export CDK_DEFAULT_REGION=us-east-1

cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION --profile crunch-dev
cdk diff --profile crunch-dev          # ALWAYS diff before deploy
cdk deploy --profile crunch-dev --require-approval broadening
```

Read the change set CDK prints before you confirm. Note the IAM-change warning — that is `--require-approval broadening` doing its job.

After you have looked at the real resources in the console, **destroy** so you stop paying:

```bash
cdk destroy --profile crunch-dev --force
```

The KMS key enters a deletion window (7 days) rather than vanishing — that is expected and stops billing on schedule.

---

## Expected output

After `cdklocal deploy`, `cdklocal synth | grep -c "AWS::"` reports more than 20 resources, and the three `CfnOutput` values print. The Lambda's role in the template contains an `s3:GetObject` statement scoped to the bucket and a `kms:Decrypt` statement scoped to the key — both generated by the single `bucket.grantRead(reader)` call.

---

## Acceptance criteria

- [ ] `npm run build` compiles with no TypeScript errors.
- [ ] `cdk synth` produces a template with **no unresolved tokens** (no literal `${Token[...]}` strings in the output).
- [ ] The synthesized template contains a KMS key with rotation, a KMS-encrypted versioned bucket with the lifecycle rule, an SSL-enforcing bucket policy, and a Lambda.
- [ ] The Lambda's IAM policy contains `s3:GetObject` scoped to the bucket **and** `kms:Decrypt` scoped to the key — and you can point to them in the template.
- [ ] You deployed to LocalStack with `cdklocal deploy` and saw the outputs.
- [ ] If you deployed to real `dev`, you ran `cdk destroy` afterward.
- [ ] You can explain, in one sentence, what `bucket.grantRead(reader)` generated and why the `kms:Decrypt` appeared.

---

## Stretch

- Add a VPC **Gateway endpoint for S3** (`vpc.addGatewayEndpoint`) so the isolated-subnet Lambda can reach S3 with no NAT and no internet. Re-synth and find the `AWS::EC2::VPCEndpoint` in the template. (This is the trick Week 4 makes central.)
- Add `cdk-nag` (the `AwsSolutionsChecks` aspect) and fix or suppress every finding with a documented reason. (Week 13 makes this mandatory.)
- Replace `bucket.grantRead` with a hand-written `iam.PolicyStatement` and confirm you can reproduce exactly what `grantRead` generated. Appreciate why you never want to.

---

## Hints

<details>
<summary>`cdk synth` complains it cannot determine the number of AZs</summary>

`Vpc` needs a concrete account+region to look up availability zones at synth. Make sure `bin/crunch-iac-ts.ts` sets `env: { account, region }` as shown in Step 3, and that `CDK_DEFAULT_ACCOUNT`/`CDK_DEFAULT_REGION` are set (or you pass a hard-coded region). For LocalStack, `cdklocal` injects a fake account `000000000000`.

</details>

<details>
<summary>`cdklocal deploy` fails on the Lambda asset</summary>

LocalStack needs the Docker socket mounted (the `-v /var/run/docker.sock:/var/run/docker.sock` flag) to bundle and run the Python asset. Confirm the container started with that mount: `docker inspect localstack | grep docker.sock`.

</details>

<details>
<summary>I see `${Token[TOKEN.nn]}` in my output</summary>

You are likely `console.log`-ing or string-concatenating a token (e.g. `bucket.bucketName`) outside of CDK's token-aware helpers. Use a template literal that CDK intercepts, or pass the token straight into a construct prop — never `.split`/`.substring` it. See Lecture 1 §10.

</details>

---

When this exercise feels comfortable, move to [Exercise 2 — Python CDK parity](exercise-02-python-cdk-parity.py).
