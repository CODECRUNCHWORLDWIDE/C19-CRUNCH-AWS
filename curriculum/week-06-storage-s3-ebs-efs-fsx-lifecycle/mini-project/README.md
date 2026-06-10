# Mini-Project — The Storage Layer (Data-Lake Foundation)

> Deliver a single CDK app that stands up a **fully lifecycled, CRR-replicated, KMS-encrypted S3 bucket with an Object Lambda transform**, plus a **shared-EFS demonstration** across Fargate and EC2. This is not a throwaway lab. The bucket you ship here becomes the **data-lake bucket** in Week 11 (S3 + Athena + Glue), the **CRR-protected lake bucket** in Week 13 (multi-region DR), and the **shared-storage foundation** the capstone reuses wherever it needs shared state. Build it like production, because it is going to *be* your production storage layer for the rest of the course.

**Estimated time:** ~9 hours (Tuesday → Sunday in the suggested schedule).

This mini-project assembles the three exercises into one coherent, deployable storage layer and adds the production polish the exercises skip: Storage Lens, S3 Inventory, a cost estimate reconciled against actuals, a presigned-URL upload path, and a written architecture decision record.

---

## What you will build

A CDK monorepo (TypeScript primary; one stack in Python to keep both languages live, per the course charter) that deploys, with `cdk deploy --all`:

1. **A primary data-lake bucket** in `us-east-1`:
   - SSE-KMS with a customer-managed key, key rotation on, **Bucket Keys on**.
   - Versioning on, with noncurrent-version expiration and abort-incomplete-multipart cleanup.
   - Block Public Access fully on, ACLs disabled, TLS enforced via bucket policy.
   - The four-tier lifecycle staircase: **Standard → IA at 30d → Glacier IR at 90d → Deep Archive at 365d**.
   - Object Lock in **governance mode** enabled on a dedicated `compliance/` prefix path (via a second bucket configured at creation, since Object Lock is creation-time only) — to demonstrate WORM without locking the whole lake.
   - Tags: `team`, `service`, `environment`, `dataclass`.

2. **A replica bucket** in `us-west-2` with its own regional CMK, receiving **Cross-Region Replication** from the primary, with **replica re-encryption** under the destination key, the replica stored in `STANDARD_IA`, and delete-marker replication on.

3. **An S3 Object Lambda Access Point** in front of the primary bucket whose Lambda **watermarks JPEGs on `GET`** (and passes non-images through untouched).

4. **A presigned-URL upload path**: a small Lambda (behind a Function URL or API Gateway HTTP API) that issues a short-lived, content-type-constrained presigned `PUT` URL so a browser can upload directly to the lake without your backend proxying bytes.

5. **A shared-EFS demonstration** (the Python stack): one EFS file system + access point mounted into an ECS Fargate task and an EC2 instance simultaneously, proving concurrent shared read/write with a round-trip file.

6. **Observability + FinOps**: S3 Storage Lens enabled, S3 Inventory configured on the primary bucket, and a committed **cost report** that compares your design-time estimate to the post-load actuals.

---

## Architecture

```
                        us-east-1 (primary)                       us-west-2 (DR)
  ┌──────────────┐     ┌───────────────────────────┐            ┌──────────────────────┐
  │  browser /   │     │   Data-Lake Bucket          │   CRR     │  Replica Bucket       │
  │  uploader    │─PUT▶│  - SSE-KMS (CMK, BucketKey) │──────────▶│  - SSE-KMS (CMK-west) │
  │ (presigned)  │     │  - versioned                │  (async,  │  - STANDARD_IA        │
  └──────────────┘     │  - lifecycle staircase      │ re-encrypt│  - versioned          │
                       │  - BPA all-on, TLS-only     │   on west)└──────────────────────┘
                       └───────────┬─────────────────┘
                                   │ GET via
                                   ▼
                       ┌───────────────────────────┐
                       │ Object Lambda Access Point │  watermark JPEGs on read
                       │   └─ WatermarkFn (Python)  │
                       └───────────────────────────┘

  Shared storage (Python stack):
    EFS ──┬── mounted by  Fargate task   (/mnt/shared, TLS+IAM via access point)
          └── mounted by  EC2 instance   (/mnt/shared, TLS+IAM via access point)
            round-trip file proves concurrent shared read/write
```

---

## Repository layout

```
c19-week6-storage/
├── README.md                       # project description + run instructions + cost report
├── cdk.json
├── package.json
├── tsconfig.json
├── bin/
│   └── app.ts                       # wires all stacks, applies tags
├── lib/
│   ├── data-lake-stack.ts           # primary bucket + KMS + lifecycle + Object Lock
│   ├── replication-stack.ts         # replica bucket + CRR + replica CMK
│   ├── object-lambda-stack.ts       # access point + Object Lambda + watermark Lambda
│   ├── presigned-stack.ts           # uploader Lambda + Function URL
│   └── observability-stack.ts       # Storage Lens config + S3 Inventory
├── lambda/
│   ├── watermark/
│   │   ├── index.py
│   │   └── requirements.txt         # Pillow
│   └── presigner/
│       └── index.py                 # generate_presigned_url
├── efs/                             # the Python CDK app (separate, from Exercise 3)
│   ├── app.py
│   └── requirements.txt
├── samples/
│   └── sample.jpg                   # a test image for the watermark path
├── docs/
│   ├── cost-estimate.md             # design-time estimate (BEFORE deploy)
│   ├── cost-actuals.md              # Storage Lens + Cost Explorer (AFTER load)
│   └── ADR-001-storage-layer.md     # architecture decision record
└── .github/
    └── workflows/ci.yml             # cdk synth + tsc on push
```

---

## Rules

- **You may** read the AWS docs, the CDK API reference, the lecture notes, and the open-source comparator docs.
- **TypeScript is primary**; the EFS stack is in **Python CDK** so both languages stay live (charter requirement).
- **Every bucket** has Block Public Access fully on, ACLs disabled, TLS enforced, SSE-KMS with a CMK, and Bucket Keys on. No exceptions. A public bucket fails the project.
- **Every resource is tagged** `team`, `service`, `environment`. Untagged resources fail the FinOps check.
- **No secrets in code.** No access keys, no hardcoded account IDs (use `Stack.of(this).account` / context).
- **Cost discipline:** replicate a handful of small test objects, not gigabytes. Tear down the EFS EC2 instance the same day. Keep the buckets — they are the data-lake foundation.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c19-week-06-storage-<yourhandle>`.
- [ ] `cdk deploy --all` deploys the entire storage layer from zero in a clean `dev` account (both regions bootstrapped).
- [ ] **Primary bucket** verifies on all of: `get-bucket-encryption` (`aws:kms` + `BucketKeyEnabled: true`), `get-bucket-versioning` (`Enabled`), `get-public-access-block` (all four `true`), `get-bucket-lifecycle-configuration` (three transitions + noncurrent expiration + abort-multipart).
- [ ] **Replication** works: an object uploaded to the primary appears in the `us-west-2` replica within a few minutes, `ReplicationStatus` is `COMPLETED` on the source version, and the replica object is encrypted under the **west** CMK (not the source key).
- [ ] **Object Lambda** works: `get-object` through the Object Lambda Access Point returns a watermarked JPEG; a `get-object` against the raw bucket returns the original; a non-image object passes through untouched.
- [ ] **Presigned upload** works: the uploader Lambda returns a presigned `PUT` URL; `curl -X PUT --upload-file sample.jpg "<url>"` succeeds; uploading with the wrong `Content-Type` is rejected.
- [ ] **Object Lock** is enabled (governance) on the WORM bucket/prefix, and a `put-object-retention` + attempted early delete demonstrates the lock holds (and that `BypassGovernanceRetention` can override it for an authorized role).
- [ ] **Shared EFS** works: a file written on EC2 is read inside the Fargate container, and a file written by Fargate is read on EC2 (the round-trip), both over TLS with IAM auth via the access point.
- [ ] **Storage Lens** is enabled and you can produce the storage-class breakdown line:
  ```
  Storage class breakdown · Standard X GiB · IA Y GiB · Glacier IR Z GiB · Deep Archive W GiB · est. $N/mo
  ```
- [ ] **`docs/cost-estimate.md`** (written *before* deploy) and **`docs/cost-actuals.md`** (after loading representative data) both exist, and the README explains any gap larger than 2x.
- [ ] **`docs/ADR-001-storage-layer.md`** records the decisions: why this lifecycle staircase, why CRR to `us-west-2`, why governance not compliance Object Lock, why EFS not FSx for the shared store, and the open-source comparator you considered (MinIO/Ceph/JuiceFS) and rejected, with one line of reasoning.
- [ ] CI (`cdk synth` + `tsc --noEmit`) is green on a fresh clone.
- [ ] `README.md` includes the run instructions, the verification commands, and the cost report.

---

## Suggested order of operations

### Phase 1 — Primary bucket + KMS (~1 h)

Lift the Exercise-1 stack into `lib/data-lake-stack.ts`. Add the `dataclass` tag and a TLS-enforcing bucket policy (CDK's `enforceSSL: true` does this; verify the generated `aws:SecureTransport: false` deny statement is present). Commit.

### Phase 2 — Replication (~1.5 h)

Lift the Exercise-2 replication into `lib/replication-stack.ts`, splitting the source and replica into clearly-named cross-region constructs. Confirm the replication role grants `kms:Decrypt` on the source key and `kms:GenerateDataKey` on the destination key — the single most common CRR-with-KMS bug is forgetting one of those. Commit.

### Phase 3 — Object Lambda (~1.5 h)

Lift the watermark Lambda and the Object Lambda Access Point into `lib/object-lambda-stack.ts`. Make the handler pass non-images through untouched (catch the decode error, return the original bytes). Add `samples/sample.jpg` and verify the watermark round-trip. Commit.

### Phase 4 — Presigned upload path (~1 h)

Write `lambda/presigner/index.py`:

```python
import json
import os
import boto3
from botocore.config import Config

s3 = boto3.client("s3", config=Config(signature_version="s3v4"))
BUCKET = os.environ["BUCKET"]

def handler(event, _ctx):
    # Expect a JSON body: {"key": "uploads/avatar.jpg", "contentType": "image/jpeg"}
    body = json.loads(event.get("body") or "{}")
    key = body["key"]
    content_type = body.get("contentType", "application/octet-stream")
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,  # 5 minutes
    )
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"uploadUrl": url, "expiresIn": 300}),
    }
```

Give the presigner Lambda only `s3:PutObject` on the bucket and `kms:GenerateDataKey` on the key — scope it tightly, because the presigned URL inherits these permissions. Expose it via a Lambda Function URL (IAM-auth) or an API Gateway HTTP API. Test that a `PUT` with the declared `Content-Type` succeeds and a mismatched one is rejected. Commit.

### Phase 5 — Object Lock / WORM (~0.5 h)

Object Lock must be set at bucket creation. Create a small dedicated `worm` bucket with `objectLockEnabled: true` and a default governance retention. Demonstrate:

```bash
aws s3api put-object --bucket "$WORM" --key audit/2026-06.log --body audit.log
aws s3api delete-object --bucket "$WORM" --key audit/2026-06.log   # blocked by retention
aws s3api delete-object --bucket "$WORM" --key audit/2026-06.log \
  --bypass-governance-retention   # succeeds for a principal with the permission
```

Document the behavior in the ADR. Commit.

### Phase 6 — Shared EFS (~1.5 h)

Bring the Exercise-3 Python stack into `efs/`. Deploy, run the round-trip verification (write on EC2, read in Fargate via CloudWatch Logs, write in Fargate, read on EC2 via SSM). Capture the log + session output. Commit.

### Phase 7 — Observability + cost report (~1.5 h)

- Enable S3 Storage Lens (account default dashboard, or a CDK `CfnStorageLens` config) and S3 Inventory on the primary bucket.
- Load **representative** data: a few hundred small objects plus a couple of larger ones, and use `aws s3api copy-object --storage-class` (or wait, in a sandbox) to put some objects in IA/Glacier IR so the breakdown is non-trivial.
- Write `docs/cost-estimate.md` (the projected monthly cost using the Lecture-2 method) **before** this, and `docs/cost-actuals.md` after, pulling numbers from Storage Lens and Cost Explorer (group by usage type).
- Produce the `Storage class breakdown` line. Commit.

### Phase 8 — ADR + README + CI (~0.5 h)

Write `docs/ADR-001-storage-layer.md` and the README run instructions. Add the CI workflow. Final commit and push.

---

## Example expected output

The verification block, run end-to-end, should produce something like:

```
$ aws s3api head-object --bucket $SRC --key photos/sample.jpg --query ReplicationStatus
"COMPLETED"

$ aws s3api head-object --bucket $DST --key photos/sample.jpg --region us-west-2 \
    --query "{enc:ServerSideEncryption,key:SSEKMSKeyId}"
{ "enc": "aws:kms", "key": "arn:aws:kms:us-west-2:...:key/<replica-cmk>" }

$ aws s3api get-object --bucket $OLAP --key photos/sample.jpg watermarked.jpg && file watermarked.jpg
watermarked.jpg: JPEG image data        # carries the CONFIDENTIAL stamp

$ # shared EFS round-trip
$ aws logs tail /ecs/efs-demo --since 10m | grep -A1 'written by EC2'
--- contents written by EC2 ---
hello from EC2 ip-10-0-3-44 at 2026-06-09T14:02:11Z

Storage class breakdown · Standard 0.6 GiB · IA 2.1 GiB · Glacier IR 5.0 GiB · Deep Archive 0.0 GiB · est. $0.17/mo
```

---

## Rubric

| Criterion | Weight | What "great" looks like |
|----------|-------:|-------------------------|
| Deploys clean | 20% | `cdk deploy --all` works from zero in both regions on a fresh clone |
| Bucket posture | 20% | KMS-CMK + Bucket Keys, versioning, BPA-all-on, TLS-only, full lifecycle staircase — all CLI-verified |
| Replication + Object Lambda | 20% | CRR completes with replica re-encryption; watermark round-trip works; non-images pass through |
| Shared EFS | 15% | Concurrent Fargate + EC2 mount with the round-trip proof, TLS + IAM auth |
| Cost engineering | 15% | Estimate and actuals both present; gaps explained; storage-class breakdown produced; everything tagged |
| ADR + README quality | 10% | A reviewer can clone, deploy, and understand every decision in under 15 minutes |

---

## What this prepares you for

- **Week 7 (CI/CD + ECR)** reuses the lifecycle-policy mental model on ECR image lifecycle rules, and your CDK monorepo gets a CodePipeline.
- **Week 11 (Data Lake & AI)** lands Firehose data into *this exact bucket*, crawls it with Glue, and queries it with Athena. The partitioning you chose for the keyspace pays off (or hurts) there.
- **Week 13 (Security & DR)** turns the CRR you built into a real multi-region DR posture, runs Macie on this bucket for PII, and proves an RTO/RPO with a failover drill against the `us-west-2` replica.
- **Week 15 (Capstone)** reuses the bucket as the lake and the EFS pattern wherever shared state is needed. By then, "production S3 bucket" is a reflex, not a research task.

---

## Submission

When done:

1. Push the repo to GitHub with a public URL.
2. Confirm `cdk deploy --all` and all verification commands are green on a fresh clone in `dev`.
3. Make sure `docs/cost-estimate.md`, `docs/cost-actuals.md`, and `docs/ADR-001-storage-layer.md` are committed.
4. **Keep the buckets deployed** — they are your data-lake foundation for Weeks 11, 13, and 15. Tear down only the EFS EC2 instance and any benchmark volumes.
5. Post the repo URL and your `Storage class breakdown` line in your cohort tracker.
