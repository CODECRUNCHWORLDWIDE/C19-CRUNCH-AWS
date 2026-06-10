# Lecture 1 — S3 Is a Database. Treat It Like One.

> **Duration:** ~3 hours of reading + hands-on.
> **Outcome:** You can reason about S3 the way you reason about a database — consistency, keyspace design, a multi-dimensional cost model, a lifecycle engine, encryption, versioning, WORM retention, a transform layer, and a query surface — and you can build all of it in CDK with the CloudFormation and OpenTofu underneath legible to you.

If you only remember one sentence from this lecture, remember this:

> **S3 is not a folder. It is a strongly-consistent, infinitely-scalable, eleven-nines-durable key-value store with a lifecycle engine, a replication topology, a transform layer, and a cost model with five-plus dimensions. The teams that treat it like a folder lose money and lose data. We will not be one of them.**

---

## 1. The mental model: a key-value store, not a filesystem

Open any tutorial and it will tell you S3 has "buckets" and "folders." Half of that is a lie. S3 has **buckets** (a global namespace, one flat keyspace per bucket) and **objects** (a key, a blob of bytes up to 5 TiB, metadata, and a storage class). There are no folders. The `/` in `logs/2026/06/09/app.log` is just a character in the key. The console *renders* a tree because humans like trees, but the keyspace is flat. `ListObjectsV2` with a `Delimiter` of `/` and a `Prefix` is how the console fakes a directory listing.

Why does this matter? Because it changes how you design keys. In a filesystem you organize for humans browsing. In S3 you organize for **the access pattern of your code** and for **request-rate scaling**. S3 scales request throughput per *prefix*: you get at least 3,500 `PUT`/`COPY`/`POST`/`DELETE` and 5,500 `GET`/`HEAD` requests per second **per prefix**, and S3 splits prefixes automatically as load grows. If every object is under `data/`, you have one prefix and one scaling unit. If you spread keys across `data/a1/`, `data/b7/`, `data/c3/` (a hash or a high-cardinality field first), you get parallel scaling for free.

This is the first place S3 behaves like a database: **your key is your primary index, and your prefix design is your partition strategy.** The old advice was "put a random hash at the front of your key." Since the 2018 performance update that auto-partitions prefixes, you no longer need to manually shard — but you still need *high-cardinality prefixes* if you intend to drive tens of thousands of requests per second. Date-first keys (`2026/06/09/...`) concentrate today's writes into one hot prefix; that is the S3 equivalent of a hot partition in DynamoDB (Week 9). You have seen this problem before. It is the same problem.

```text
Bad (hot prefix — all of today's writes hit one scaling unit):
  events/2026/06/09/00/evt-000001.json
  events/2026/06/09/00/evt-000002.json

Better (high-cardinality first segment spreads the write load):
  events/3f/2026/06/09/00/evt-000001.json   # 3f = first 2 hex of a hash(key)
  events/a1/2026/06/09/00/evt-000002.json
```

For a data lake you query with Athena (Week 11), you flip this again and partition by date *on purpose* so partition pruning works. The lesson is not "always do X." The lesson is: **the keyspace is a design decision with throughput and query consequences. Make it deliberately.**

---

## 2. Consistency: stop coding around eventual consistency

For its first fourteen years S3 was eventually consistent for overwrites and deletes, and a generation of engineers wrote retry loops and "list to confirm the write landed" hacks. **Delete those.** Since December 2020, S3 provides **strong read-after-write consistency** for all operations, in all regions, at no extra cost. After a successful `PUT`, any subsequent `GET`, `HEAD`, or `LIST` immediately reflects it. After a successful `DELETE`, the object is gone for the next read.

What S3 still does *not* give you:

- **No object-level locking for concurrent writers by default.** Two `PUT`s to the same key race; last writer wins. There is no transaction across two keys.
- **No conditional update by default** — until you ask for it. As of 2024, S3 supports `If-None-Match: *` on `PUT` to implement **write-if-absent** (fail if the key exists), and conditional `PUT`/`DELETE` against an `ETag`. This is your optimistic-concurrency primitive. Use it instead of "list then put."

```bash
# Write only if the key does not already exist (atomic "create").
# Returns 412 PreconditionFailed if the object is already there.
aws s3api put-object \
  --bucket my-bucket \
  --key config/lock.json \
  --body lock.json \
  --if-none-match '*'
```

This is the second database-like property: **strong consistency plus conditional writes give you enough to build a coordinating primitive on top of S3** — a leader-election lock, an idempotency guard, an "exactly-once" sink. You will use exactly this pattern in the event-driven weeks.

---

## 3. The cost model: five-plus dimensions, and most of them are not "storage"

Here is the mistake that costs real money: pricing S3 as "GB stored × $/GB." Storage is one of *at least five* dimensions you pay on, and for many workloads it is not the dominant one.

| Dimension | What you pay for | The gotcha |
|---|---|---|
| **Storage** | GB-month, per class | Standard ≈ $0.023/GB-mo; Deep Archive ≈ $0.00099/GB-mo. ~23x cheaper. |
| **Requests** | `PUT`/`COPY`/`POST`/`LIST` (~$0.005/1k) and `GET`/`HEAD` (~$0.0004/1k) | A million tiny objects is a request bill, not a storage bill. |
| **Retrieval** | Per-GB to read back from Glacier classes | Deep Archive retrieval is cheap to store, expensive and slow to read. |
| **Data transfer out** | Egress to the internet (~$0.09/GB) | Cross-region, cross-AZ, NAT — all separate lines. S3→internet is the big one. |
| **Management & replication** | Inventory, Storage Lens advanced, Intelligent-Tiering monitoring, replication transfer | Per-object and per-GB fees that hide in the bill. |

Three traps that catch every team at least once:

1. **Minimum object size charges.** Standard-IA and One-Zone-IA bill a *minimum of 128 KB per object*. Glacier classes have their own minimums. Put a million 4 KB objects in IA and you pay for 128 KB each — 32x the bytes you stored. **IA is for big, cold objects, not small ones.**
2. **Minimum storage duration.** Standard-IA: 30 days. Glacier IR: 90 days. Glacier Flexible / Deep Archive: 90 / 180 days. Delete or transition an object *before* its minimum and you are billed for the full minimum anyway. A lifecycle rule that moves objects to Glacier IR at 90 days and expires them at 100 days pays the full 90-day Glacier minimum for 10 days of value. **Tier on the same cadence you actually keep data.**
3. **The KMS request bill.** Every `GET`/`PUT` against an SSE-KMS object is a KMS API call (`Decrypt`/`GenerateDataKey`) at ~$0.03/10k. At a billion reads a month that is ~$3,000 *just for KMS*, on top of S3. The fix is **S3 Bucket Keys** (Section 6), which cut KMS calls ~99%.

The fourth database-like property: **S3 has a query optimizer's worth of cost knobs, and you are the optimizer.** You decide the class, the lifecycle, the encryption strategy, the request shape. Estimate before you deploy. The mini-project requires it.

---

## 4. Storage classes: the latency / durability / cost triangle

There are six "manual" classes plus Intelligent-Tiering. The axes are **retrieval latency**, **availability/AZ-redundancy**, and **price**. Memorize the *shape*, not the exact dollars (they drift).

| Class | Retrieval | AZs | Min duration | Min size | Use it for |
|---|---|---|---|---|---|
| **Standard** | ms | ≥3 | none | none | Hot data, anything read often |
| **Standard-IA** | ms | ≥3 | 30 d | 128 KB | Warm data, read monthly-ish, big objects |
| **One-Zone-IA** | ms | 1 | 30 d | 128 KB | Re-creatable warm data you can afford to lose if an AZ dies |
| **Glacier Instant Retrieval** | ms | ≥3 | 90 d | 128 KB | Archives you still read occasionally, fast |
| **Glacier Flexible Retrieval** | minutes–hours | ≥3 | 90 d | (per object) | Backups, retrieval-tolerant archives |
| **Glacier Deep Archive** | 12 h | ≥3 | 180 d | (per object) | Compliance archives, "never read unless audited" |
| **Intelligent-Tiering** | ms (frequent/infrequent tiers) | ≥3 | none* | — | Unknown/changing access; pay a small monitoring fee, AWS moves objects |

Key judgment calls:

- **One-Zone-IA** trades a 9 of availability and AZ redundancy for ~20% off IA. Only use it for data you can *regenerate* (thumbnails, transcodes, derived artifacts). If losing it means a 3am page, do not use One-Zone.
- **Glacier Instant Retrieval (IR)** is the unsung hero: archive-tier *storage* price with *millisecond* retrieval. It is the right home for "we keep it for compliance but might occasionally need it fast." It is the `Glacier IR at 90d` step in our lifecycle.
- **Intelligent-Tiering** is the answer when you genuinely cannot predict access. It auto-moves objects between a Frequent and Infrequent tier (and optionally Archive tiers) and charges a per-object monitoring fee (~$0.0025/1k objects/mo). For *predictable* access patterns, a lifecycle rule is cheaper because you skip the monitoring fee. For unpredictable, Intelligent-Tiering wins because a wrong lifecycle rule costs more than the monitoring fee. **Predictable → lifecycle. Unpredictable → Intelligent-Tiering.**

---

## 5. Lifecycle rules: the engine that moves your money

A lifecycle configuration is a set of rules attached to a bucket. Each rule has a **filter** (prefix, tag, object size) and one or more **actions**: `Transition` (change storage class after N days), `Expiration` (delete after N days), `NoncurrentVersionTransition` / `NoncurrentVersionExpiration` (same, for old versions), and `AbortIncompleteMultipartUpload` (clean up half-finished uploads — *always set this; orphaned multipart parts silently accrue storage cost*).

The canonical staircase this week, in CDK:

```typescript
import { Bucket, StorageClass } from 'aws-cdk-lib/aws-s3';
import { Duration } from 'aws-cdk-lib';

const bucket = new Bucket(this, 'DataLakeBucket', {
  versioned: true,
  lifecycleRules: [
    {
      id: 'tier-down-staircase',
      enabled: true,
      transitions: [
        { storageClass: StorageClass.INFREQUENT_ACCESS,    transitionAfter: Duration.days(30) },
        { storageClass: StorageClass.GLACIER_INSTANT_RETRIEVAL, transitionAfter: Duration.days(90) },
        { storageClass: StorageClass.DEEP_ARCHIVE,          transitionAfter: Duration.days(365) },
      ],
      // Clean up old versions so versioning doesn't quietly 10x your bill.
      noncurrentVersionExpiration: Duration.days(90),
      noncurrentVersionsToRetain: 3,
      // Never leave half-finished multipart uploads paying rent.
      abortIncompleteMultipartUploadAfter: Duration.days(7),
    },
  ],
});
```

The same thing in **CloudFormation** (this is what CDK synthesizes — read it so the substrate is not magic):

```yaml
Resources:
  DataLakeBucket:
    Type: AWS::S3::Bucket
    Properties:
      VersioningConfiguration:
        Status: Enabled
      LifecycleConfiguration:
        Rules:
          - Id: tier-down-staircase
            Status: Enabled
            Transitions:
              - StorageClass: STANDARD_IA
                TransitionInDays: 30
              - StorageClass: GLACIER_IR
                TransitionInDays: 90
              - StorageClass: DEEP_ARCHIVE
                TransitionInDays: 365
            NoncurrentVersionExpiration:
              NoncurrentDays: 90
              NewerNoncurrentVersions: 3
            AbortIncompleteMultipartUpload:
              DaysAfterInitiation: 7
```

And in **OpenTofu** (the AWS provider splits the bucket into many small resources — this is the cross-cloud substrate you should be able to read):

```hcl
resource "aws_s3_bucket" "data_lake" {
  bucket = "c19-week6-data-lake-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "tier-down-staircase"
    status = "Enabled"
    filter {}

    transition { days = 30  storage_class = "STANDARD_IA" }
    transition { days = 90  storage_class = "GLACIER_IR" }
    transition { days = 365 storage_class = "DEEP_ARCHIVE" }

    noncurrent_version_expiration {
      noncurrent_days           = 90
      newer_noncurrent_versions = 3
    }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}
```

Three rules of thumb that keep lifecycle from biting you:

1. **Respect minimum durations.** Do not transition to Glacier IR at 90 days and expire at 120 — you pay the 90-day Glacier minimum either way; transitioning that late buys you little. Either keep it long (our 365→Deep Archive step) or do not bother tiering it.
2. **Watch the transition request cost.** Each transition is a request, billed per object. Tiering a billion tiny objects has a non-trivial *transition* cost. Sometimes the cheaper move is to *expire* small objects rather than tier them.
3. **Tier the data, not the index.** If you have an Athena/Glue manifest or a small "current" set you read constantly, exclude it with a prefix filter so it stays in Standard.

---

## 6. Encryption: SSE-KMS with a CMK, and why Bucket Keys are non-optional

S3 encrypts everything at rest by default (SSE-S3, AES-256) since 2023. The question is not *whether* to encrypt; it is *which key controls decryption*.

- **SSE-S3** — AWS owns the key. You cannot audit who decrypts. Fine for non-sensitive data.
- **SSE-KMS with an AWS-managed key (`aws/s3`)** — KMS-logged, but you do not control the key policy.
- **SSE-KMS with a customer-managed key (CMK)** — *you* own the key policy. You decide which principals can `Decrypt`. CloudTrail logs every use. **This is the production default for anything sensitive, and what we use this week.**
- **DSSE-KMS** — double-layer KMS encryption for the rare regulatory requirement that mandates two independent layers.
- **SSE-C** — you supply the key on every request. Almost nobody should use this; key management becomes your problem.

The CMK + bucket, in CDK, with the two settings that matter:

```typescript
import { Key } from 'aws-cdk-lib/aws-kms';
import { Bucket, BucketEncryption, BlockPublicAccess } from 'aws-cdk-lib/aws-s3';
import { RemovalPolicy } from 'aws-cdk-lib';

const key = new Key(this, 'BucketKey', {
  enableKeyRotation: true,          // annual automatic rotation — always on
  description: 'CMK for the C19 data-lake bucket',
  removalPolicy: RemovalPolicy.RETAIN, // never auto-delete a key that encrypted data
});

const bucket = new Bucket(this, 'DataLakeBucket', {
  encryption: BucketEncryption.KMS,   // SSE-KMS with the CMK below
  encryptionKey: key,
  bucketKeyEnabled: true,             // <-- THE setting that saves ~99% of KMS calls
  enforceSSL: true,                   // deny any request not over TLS
  blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
  versioned: true,
});
```

**Why `bucketKeyEnabled: true` is not optional.** Without a bucket key, S3 calls KMS once per object operation. With it, S3 derives a short-lived bucket-level data key and reuses it, collapsing thousands of object reads into one KMS call. The savings are typically ~99% of KMS request cost. At any real read volume this is the difference between a $5 KMS bill and a $5,000 one. Turn it on. Always.

**The key policy is the real access control.** The bucket policy says who can call `s3:GetObject`; the *key* policy says who can `kms:Decrypt`. A principal needs *both*. This is a frequent production bug: someone has S3 read permission, the object is SSE-KMS, and the `GET` fails with `AccessDenied` because the key policy never granted them `kms:Decrypt`. When you debug "I have s3:GetObject but it's denied," check the **key policy** second (and the bucket policy / BPA first). You read twelve broken IAM policies in Week 2; this is the storage flavor of the same skill.

---

## 7. Block Public Access: the answer is almost always "all four, on"

S3 has four Block Public Access (BPA) toggles, at both the *account* level and the *bucket* level. Account-level wins (most restrictive applies):

- `BlockPublicAcls` — reject `PUT`s that set a public ACL.
- `IgnorePublicAcls` — ignore any public ACL that already exists.
- `BlockPublicPolicy` — reject bucket policies that grant public access.
- `RestrictPublicBuckets` — even if a policy is "public," only AWS service principals and authorized users can use it.

In 2026 the default for new buckets is **all four on, and ACLs disabled** (Object Ownership = `BucketOwnerEnforced`). That is correct. The way you serve public content is **not** a public bucket — it is a private bucket behind **CloudFront with Origin Access Control** (Week 4/14) or a **presigned URL** (Section 9). If a requirement says "make the bucket public," push back: it almost always means "let the internet read these specific objects," and the right answer is CloudFront + OAC. Public buckets are how data leaks make the news.

Set it at the account level once and stop worrying:

```bash
aws s3control put-public-access-block \
  --account-id "$(aws sts get-caller-identity --query Account --output text)" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

---

## 8. Versioning, Object Lock, and WORM

**Versioning** keeps every version of an object; a "delete" writes a *delete marker* over the latest version rather than destroying data. It is the cheapest insurance against `aws s3 rm` accidents and ransomware-style overwrites. The cost is that old versions accumulate — which is exactly why the lifecycle rule in Section 5 expires noncurrent versions. Versioning without a noncurrent-version lifecycle rule is how a bucket quietly 10x's its bill.

**Object Lock** layers WORM (write-once-read-many) retention on top of versioning. Two modes:

- **Governance mode** — objects are protected, but a principal with `s3:BypassGovernanceRetention` can shorten or remove the lock. Use this for "protect against accidents, but let an admin fix mistakes."
- **Compliance mode** — *no one*, including the root user, can shorten the retention or delete the object until the period expires. This is for genuine legal/regulatory WORM (SEC 17a-4, etc.). It is a one-way door. Set a 7-year compliance retention by accident on a 50 TiB bucket and you are paying to store 50 TiB for 7 years. Treat compliance mode like `rm -rf /`: be very, very sure.

Object Lock must be enabled at **bucket creation** (it implies versioning). You then set retention per object version, or a default retention on the bucket.

```bash
# Bucket created with Object Lock enabled (must be at creation time).
aws s3api create-bucket --bucket my-worm-bucket --object-lock-enabled-for-bucket \
  --create-bucket-configuration LocationConstraint=us-west-2

# Apply a 30-day GOVERNANCE retention to one object version.
aws s3api put-object-retention \
  --bucket my-worm-bucket --key audit/2026-06.log \
  --retention 'Mode=GOVERNANCE,RetainUntilDate=2026-07-09T00:00:00Z'
```

The database parallel: **Object Lock is your `ALTER TABLE ... ADD CONSTRAINT immutable` — a guarantee about what can happen to a row, enforced by the platform, not your application code.**

---

## 9. Presigned URLs and multipart upload

A **presigned URL** is a regular HTTPS URL with a signature and an expiry baked into the query string. Anyone holding it can perform exactly one operation (`GET` or `PUT`) on exactly one object until it expires — with no AWS credentials. This is how you let a browser upload directly to S3 without your backend proxying bytes, and how you hand out a time-boxed download link.

```python
import boto3
from botocore.config import Config

s3 = boto3.client("s3", config=Config(signature_version="s3v4"))

# A 15-minute download link.
get_url = s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": "my-bucket", "Key": "reports/q2.pdf"},
    ExpiresIn=900,
)

# A 5-minute upload slot for the browser to PUT straight to S3.
put_url = s3.generate_presigned_url(
    "put_object",
    Params={"Bucket": "my-bucket", "Key": "uploads/incoming.bin", "ContentType": "application/octet-stream"},
    ExpiresIn=300,
)
print(get_url)
print(put_url)
```

Rules: the URL inherits the *signer's* permissions, so sign with a tightly-scoped role, not an admin. Keep expiries short. For uploads, constrain `ContentType` and use a `Content-Length` policy (or a presigned **POST** with conditions) so a client cannot upload a 5 TiB object to a slot you meant for a 2 MB avatar.

**Multipart upload** splits a large object into parts (5 MiB–5 GiB each, up to 10,000 parts → 5 TiB max object) uploaded in parallel, then assembled with a `CompleteMultipartUpload`. The SDK's high-level transfer manager (`upload_file`, `s3.TransferConfig`) does this automatically above a threshold. The thing to *remember* is the failure mode: an aborted multipart upload leaves parts in the bucket that you pay for and that do not show up in a normal `ListObjects`. That is why the lifecycle rule in Section 5 always sets `AbortIncompleteMultipartUpload`.

---

## 10. Object Lambda: transform on read

An **S3 Object Lambda Access Point** puts a Lambda function in the `GET` path. The client requests an object through the access point; S3 invokes your Lambda with a presigned URL to the original object; your Lambda fetches it, transforms the bytes, and returns them via `WriteGetObjectResponse`. The original object in the bucket is never modified.

This week's transform is **watermarking JPEGs on `GET`** (Exercise 2). The shape of the handler:

```python
import boto3
import urllib.request
from PIL import Image, ImageDraw
import io

s3 = boto3.client("s3")

def handler(event, _context):
    ctx = event["getObjectContext"]
    # 1. Fetch the original object using the presigned URL S3 hands us.
    original = urllib.request.urlopen(ctx["inputS3Url"]).read()

    # 2. Transform: stamp a watermark.
    img = Image.open(io.BytesIO(original)).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "CRUNCH LABS — CONFIDENTIAL", fill=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="JPEG")

    # 3. Stream the transformed bytes back to the original caller.
    s3.write_get_object_response(
        Body=out.getvalue(),
        RequestRoute=ctx["outputRoute"],
        RequestToken=ctx["outputToken"],
    )
    return {"statusCode": 200}
```

**When Object Lambda wins:** the transform is cheap, the output is not worth persisting, or you need per-requester variation (redact PII for one role, not another; watermark with the *caller's* identity). **When it loses:** the transform is expensive and the output is reused — then a pre-transform pipeline (transform once on `PUT`, store the derivative) is cheaper than transforming on every `GET`. The decision is the same read-vs-write trade-off you make everywhere: **transform-on-read is lazy and per-request-cheap-but-repeated; transform-on-write is eager and amortized.** Pick based on read:write ratio.

This is the transform layer that completes the "S3 is a database" picture: you now have a key index, strong consistency, conditional writes, a cost-tunable storage engine, WORM constraints, *and* a view/transform layer (`CREATE VIEW`-like behavior) on read.

---

## 11. S3 Select and querying in place

**S3 Select** lets you run a SQL `SELECT` against a single CSV, JSON, or Parquet object and get back only the matching rows/columns, without downloading the whole object. For a single large CSV where you want three columns, it cuts transfer and parse cost dramatically.

```bash
aws s3api select-object-content \
  --bucket my-bucket --key data/events.csv.gz \
  --expression "SELECT s.user_id, s.amount FROM s3object s WHERE s.amount > 100" \
  --expression-type SQL \
  --input-serialization '{"CSV":{"FileHeaderInfo":"USE"},"CompressionType":"GZIP"}' \
  --output-serialization '{"CSV":{}}' \
  /dev/stdout
```

The honest 2026 framing: **S3 Select is single-object only and AWS now steers you toward Athena (Week 11) or S3 Tables for anything multi-object or analytical.** You must understand S3 Select because it is on the exam and it shows up in older codebases, but for a real data lake you will reach for Athena. S3 Select is the `SELECT ... WHERE` against one file; Athena is the query engine across the whole lake.

---

## 12. Putting it together — the production bucket checklist

When you provision a serious S3 bucket, you set *all* of this, every time. The mini-project bucket has every box checked:

- [ ] **Block Public Access**: all four, on.
- [ ] **ACLs disabled** (`BucketOwnerEnforced`).
- [ ] **`enforceSSL: true`** — deny non-TLS requests.
- [ ] **SSE-KMS with a CMK**, `enableKeyRotation: true`, `bucketKeyEnabled: true`.
- [ ] **Versioning on**, with a **noncurrent-version expiration** lifecycle rule.
- [ ] **`AbortIncompleteMultipartUpload`** in the lifecycle config.
- [ ] **A tiering staircase** matched to the real access pattern (or Intelligent-Tiering if access is unpredictable).
- [ ] **Object Lock** if and only if WORM is a genuine requirement — and governance mode unless compliance is legally mandated.
- [ ] **CRR/SRR** if the data is a recovery target (the lake bucket is — Week 13).
- [ ] **Tags**: `team`, `service`, `environment` (Week 14 FinOps needs them).
- [ ] **S3 Storage Lens** enabled at the account level so you can see the storage-class breakdown.

If you can recite that list from memory by Friday, you have internalized the lecture.

---

## 13. Recap

You should now be able to:

- Explain why S3 is a key-value store with a flat keyspace, and design prefixes for throughput and query pruning.
- State that S3 is strongly consistent and use conditional writes (`If-None-Match`) instead of "list then put."
- Name the five-plus cost dimensions and the three traps (minimum size, minimum duration, KMS request bill).
- Pick a storage class from an access pattern and author a four-tier lifecycle staircase in CDK, CloudFormation, and OpenTofu.
- Configure SSE-KMS with a CMK and explain why Bucket Keys are non-optional.
- Set Block Public Access correctly and explain why "public bucket" is the wrong answer.
- Configure versioning, Object Lock (governance vs compliance), presigned URLs, multipart upload, Object Lambda, and S3 Select.

Next up: the cost-engineering and block/file-storage half of the week. Continue to [Lecture 2 — Storage Cost Engineering](./02-storage-cost-engineering.md).

---

## References

- *Amazon S3 User Guide*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html>
- *S3 consistency model*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel>
- *Storage classes*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html>
- *Lifecycle management*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html>
- *Server-side encryption & Bucket Keys*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/serv-side-encryption.html>
- *Block Public Access*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html>
- *Object Lock*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html>
- *S3 Object Lambda*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/transforming-objects.html>
- *Presigned URLs*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html>
