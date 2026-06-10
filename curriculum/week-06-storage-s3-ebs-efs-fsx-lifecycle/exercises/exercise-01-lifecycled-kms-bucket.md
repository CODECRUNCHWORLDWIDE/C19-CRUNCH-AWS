# Exercise 1 — A Lifecycled, KMS-CMK, Versioned Bucket

**Goal:** Build the production-shape S3 bucket the whole week is built on. SSE-KMS with a customer-managed key, Bucket Keys on, versioning on, Block Public Access fully on, TLS enforced, and a four-tier lifecycle staircase (Standard → IA at 30d → Glacier IR at 90d → Deep Archive at 365d) with noncurrent-version cleanup. You build it in CDK, then verify every property with the CLI.

**Estimated time:** 90 minutes.

---

## Setup

You need an AWS SSO profile and a bootstrapped CDK environment in `dev` from Week 3.

```bash
aws --version                 # aws-cli/2.x
cdk --version                 # 2.x
node --version                # v20+
aws sts get-caller-identity   # confirm you're in dev
```

Scaffold a fresh CDK app (TypeScript):

```bash
mkdir c19-week6-storage && cd c19-week6-storage
cdk init app --language typescript
npm install
```

---

## Step 1 — Write the stack

Open `lib/c19-week6-storage-stack.ts` and replace its body with the following. Read every property — each one is a checkbox from the Lecture 1 production checklist.

```typescript
import { Stack, StackProps, Duration, RemovalPolicy, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Key } from 'aws-cdk-lib/aws-kms';
import {
  Bucket,
  BucketEncryption,
  BlockPublicAccess,
  StorageClass,
  ObjectOwnership,
} from 'aws-cdk-lib/aws-s3';

export class C19Week6StorageStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Customer-managed KMS key. Rotation on, never auto-delete a key that
    // encrypted data — RETAIN means cdk destroy leaves the key (scheduled for
    // deletion manually) rather than orphaning ciphertext.
    const key = new Key(this, 'BucketCmk', {
      description: 'CMK for the C19 week-6 data-lake bucket',
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.RETAIN,
      alias: 'alias/c19-week6-data-lake',
    });

    const bucket = new Bucket(this, 'DataLakeBucket', {
      // --- encryption ---
      encryption: BucketEncryption.KMS,
      encryptionKey: key,
      bucketKeyEnabled: true,                 // cuts KMS request cost ~99%
      // --- access posture ---
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      objectOwnership: ObjectOwnership.BUCKET_OWNER_ENFORCED, // ACLs disabled
      enforceSSL: true,                       // deny non-TLS requests
      // --- data protection ---
      versioned: true,
      // --- lifecycle staircase ---
      lifecycleRules: [
        {
          id: 'tier-down-staircase',
          enabled: true,
          transitions: [
            { storageClass: StorageClass.INFREQUENT_ACCESS,         transitionAfter: Duration.days(30) },
            { storageClass: StorageClass.GLACIER_INSTANT_RETRIEVAL, transitionAfter: Duration.days(90) },
            { storageClass: StorageClass.DEEP_ARCHIVE,              transitionAfter: Duration.days(365) },
          ],
          noncurrentVersionExpiration: Duration.days(90),
          noncurrentVersionsToRetain: 3,
          abortIncompleteMultipartUploadAfter: Duration.days(7),
        },
      ],
      // dev-only: allow cdk destroy to remove the bucket + contents.
      // NEVER set autoDeleteObjects in prod on a versioned data-lake bucket.
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // FinOps tags — graded habit (Week 14 needs them).
    bucket.node.addMetadata('team', 'platform');

    new CfnOutput(this, 'BucketName', { value: bucket.bucketName });
    new CfnOutput(this, 'KeyArn', { value: key.keyArn });
  }
}
```

Wire the stack into `bin/c19-week6-storage.ts` and add tags:

```typescript
import { App, Tags } from 'aws-cdk-lib';
import { C19Week6StorageStack } from '../lib/c19-week6-storage-stack';

const app = new App();
const stack = new C19Week6StorageStack(app, 'C19Week6StorageStack', {
  env: { region: 'us-east-1' },
});
Tags.of(stack).add('team', 'platform');
Tags.of(stack).add('service', 'data-lake');
Tags.of(stack).add('environment', 'dev');
```

---

## Step 2 — Read the synthesized CloudFormation

Before you deploy, look at what CDK generates. This is the substrate.

```bash
cdk synth | head -120
```

Find the `AWS::S3::Bucket`, the `AWS::KMS::Key`, and the `BucketEncryption` / `LifecycleConfiguration` / `PublicAccessBlockConfiguration` blocks. Confirm `BucketKeyEnabled: true` is present. If it is missing, you forgot `bucketKeyEnabled`.

---

## Step 3 — Diff and deploy

```bash
cdk diff
cdk deploy
```

Read the diff. You should see one KMS key, one bucket, and the auto-delete custom resource. Approve and deploy. Capture the outputs:

```bash
BUCKET=$(aws cloudformation describe-stacks --stack-name C19Week6StorageStack \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)
echo "$BUCKET"
```

---

## Step 4 — Verify every property from the CLI

This is the part that matters. Do not trust the console; assert from the API.

**Encryption (must be `aws:kms` with `BucketKeyEnabled: true`):**

```bash
aws s3api get-bucket-encryption --bucket "$BUCKET"
```

Expected (abridged):

```json
{
  "ServerSideEncryptionConfiguration": {
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "aws:kms",
          "KMSMasterKeyID": "arn:aws:kms:us-east-1:...:key/..."
        },
        "BucketKeyEnabled": true
      }
    ]
  }
}
```

**Versioning (must be `Enabled`):**

```bash
aws s3api get-bucket-versioning --bucket "$BUCKET"
```

```json
{ "Status": "Enabled" }
```

**Block Public Access (all four `true`):**

```bash
aws s3api get-public-access-block --bucket "$BUCKET"
```

```json
{
  "PublicAccessBlockConfiguration": {
    "BlockPublicAcls": true,
    "IgnorePublicAcls": true,
    "BlockPublicPolicy": true,
    "RestrictPublicBuckets": true
  }
}
```

**Lifecycle (three transitions + noncurrent expiration + abort-multipart):**

```bash
aws s3api get-bucket-lifecycle-configuration --bucket "$BUCKET"
```

```json
{
  "Rules": [
    {
      "ID": "tier-down-staircase",
      "Status": "Enabled",
      "Transitions": [
        { "Days": 30,  "StorageClass": "STANDARD_IA" },
        { "Days": 90,  "StorageClass": "GLACIER_IR" },
        { "Days": 365, "StorageClass": "DEEP_ARCHIVE" }
      ],
      "NoncurrentVersionExpiration": { "NoncurrentDays": 90, "NewerNoncurrentVersions": 3 },
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 7 }
    }
  ]
}
```

---

## Step 5 — Prove TLS enforcement and KMS gating

Upload an object (this succeeds — your CLI uses TLS and your principal can use the key):

```bash
echo "hello storage week" > hello.txt
aws s3 cp hello.txt "s3://$BUCKET/test/hello.txt"
aws s3 cp "s3://$BUCKET/test/hello.txt" -    # reads it back
```

Now prove the data is actually KMS-encrypted by inspecting the object's metadata:

```bash
aws s3api head-object --bucket "$BUCKET" --key test/hello.txt \
  --query "{enc:ServerSideEncryption, key:SSEKMSKeyId, bucketKey:BucketKeyEnabled}"
```

Expected:

```json
{ "enc": "aws:kms", "key": "arn:aws:kms:us-east-1:...:key/...", "bucketKey": true }
```

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] `cdk deploy` succeeds and the stack outputs a bucket name and key ARN.
- [ ] `get-bucket-encryption` shows `aws:kms` with your CMK and `BucketKeyEnabled: true`.
- [ ] `get-bucket-versioning` shows `Enabled`.
- [ ] `get-public-access-block` shows all four toggles `true`.
- [ ] `get-bucket-lifecycle-configuration` shows the three transitions, noncurrent expiration, and abort-multipart rule.
- [ ] `head-object` on an uploaded object confirms `aws:kms` + bucket key.
- [ ] The stack and all three resources are tagged `team` / `service` / `environment`.
- [ ] You pasted the four verification JSON blobs into your engineering journal.

---

## Stretch

- Add a bucket policy statement that **denies** any `s3:PutObject` whose `s3:x-amz-server-side-encryption` is not `aws:kms` — belt-and-suspenders on top of default encryption.
- Add a second lifecycle rule, filtered to prefix `tmp/`, that simply expires objects after 7 days (no tiering). Confirm both rules coexist.
- Turn on **S3 Storage Lens** at the account level and screenshot the (initially tiny) storage-class breakdown for this bucket.

---

## Hints

<details>
<summary>If get-bucket-encryption returns "ServerSideEncryptionConfigurationNotFoundError"</summary>

You deployed before the encryption config attached, or you are querying the wrong bucket name. Re-run with the exact `$BUCKET` from the stack output, and `cdk deploy` again.

</details>

<details>
<summary>If your upload fails with AccessDenied and you ARE the deployer</summary>

Your principal needs `kms:GenerateDataKey` on the CMK to *write* an SSE-KMS object, not just `s3:PutObject`. The CDK `Key` grants the deploying role usage by default, but if you switched SSO profiles between deploy and upload, the new profile may lack key permission. Check the **key policy**, then the bucket policy — same debugging order as Lecture 1, Section 6.

</details>

<details>
<summary>If cdk destroy fails on the bucket</summary>

A versioned bucket with objects will not delete unless `autoDeleteObjects: true` (set above) handles the version cleanup. The KMS key is `RETAIN` on purpose — schedule its deletion manually with `aws kms schedule-key-deletion` if you truly want it gone.

</details>

---

When this bucket exists and verifies, move to [Exercise 2 — CRR + Object Lambda](exercise-02-crr-and-object-lambda.ts).
