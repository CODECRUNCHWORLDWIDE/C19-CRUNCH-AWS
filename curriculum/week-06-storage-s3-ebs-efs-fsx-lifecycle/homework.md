# Week 6 Homework

Six problems that revisit the week's storage topics and push them a little past where the exercises left off. The full set should take about **6 hours**. Work in your Week 6 Git repository (`c19-week-06-<yourhandle>`) so each problem produces at least one commit you can point to later. Most of this week is pennies, but two problems create resources that cost real money if you leave them running — **tear down compute and `io2`/`gp3` benchmark volumes the same day**, and watch the Cross-Region Replication line and any NAT data-processing line in Cost Explorer.

Each problem includes:

- A short **problem statement**.
- **Deliverables** — the concrete artifacts you commit.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

A grading **rubric** is at the bottom.

> Cost discipline for the week: S3 storage at these volumes is cents, and ingress is free. The things that bite are (a) **internet egress** (`~$0.09/GB`) if you serve objects directly instead of through CloudFront, (b) **cross-region transfer** from CRR (`~$0.02/GB`) if you replicate gigabytes instead of a handful of test objects, and (c) a **benchmark EBS volume** — an `io2` provisioned at tens of thousands of IOPS is not free to leave sitting attached to a stopped instance. Replicate small, benchmark fast, destroy the compute the same night.

---

## Problem 1 — The minimum-object-size trap, costed both ways

**Problem statement.** Lecture 2 warned that lifecycling a swarm of tiny objects into a cold class *loses* money because of the **128 KB minimum object size** and the **minimum storage duration** charges. Prove it with numbers. You have two candidate workloads landing in `us-east-1`, each storing **1,000,000 new objects/month**, retained 90 days:

- **Workload A:** objects average **2 MB** (think rendered media).
- **Workload B:** objects average **8 KB** (think per-request JSON event records).

For each workload, compute the monthly storage cost under two designs: (1) **S3 Standard, no lifecycle**, and (2) a **lifecycle rule that transitions to Standard-IA at 30 days**. Use 2026-approximate prices: Standard `$0.023/GB-mo`, Standard-IA `$0.0125/GB-mo`, IA billed at a **128 KB minimum per object**, IA **30-day minimum duration**. Then state, in two sentences, which workload should be lifecycled to IA and which should not, and what the right move is for the one that should not.

**Deliverables.** A file `notes/min-object-size.md` with a small table (four storage numbers: A-Standard, A-IA, B-Standard, B-IA) showing the per-object billed size used in each IA cell, plus the two-sentence verdict.

**Acceptance criteria.**

- Workload A's IA cell uses the real 2 MB object size (above the 128 KB floor, so no penalty) and comes out **cheaper** than Standard.
- Workload B's IA cell bills each 8 KB object at **128 KB** (16x its real size), making the IA design **more expensive** than just leaving B in Standard.
- The verdict says A should be lifecycled to IA and B should **not** — and that the right move for B is to **aggregate** small records into larger objects (Firehose-style batching, previewing Week 11) before any tiering.
- Committed.

**Hint.** Per-object IA storage cost = `max(actual_size, 128 KB) × $0.0125/GB-mo`. For B: `1,000,000 × 128 KB = 128 GB` *billed* (vs `8 GB` actual) → `128 × $0.0125 = $1.60/mo` in IA versus `8 × $0.023 = $0.184/mo` left in Standard. For A: `1,000,000 × 2 MB = 2,000 GB` → IA `$25/mo` vs Standard `$46/mo`. The 16x billed-size inflation on B is the whole lesson. Do not forget the 30-day IA minimum-duration penalty if you also expire objects early.

**Estimated time.** 45 minutes.

---

## Problem 2 — Harden the bucket policy: TLS-only and deny-non-CMK

**Problem statement.** The Exercise 1 bucket has Block Public Access on and SSE-KMS as the *default*, but a client can still (a) talk to it over plain HTTP and (b) override the default by `PUT`-ing an object with `x-amz-server-side-encryption: AES256` (SSE-S3) instead of your CMK. Close both holes with a **bucket policy**. Add a statement that **denies any request where `aws:SecureTransport` is `false`**, and a statement that **denies any `PutObject` that is not encrypted with your specific CMK** (deny when `s3:x-amz-server-side-encryption-aws-kms-key-id` is not your key ARN, and deny when the header is absent). Then prove both denials from the CLI.

**Deliverables.** The CDK change (a `bucket.addToResourcePolicy(...)` block, or the OpenTofu `aws_s3_bucket_policy` equivalent) under `homework/p2-bucket-policy/`, plus a file `notes/bucket-policy-proof.md` containing the two `AccessDenied` outputs and the rendered policy JSON.

**Acceptance criteria.**

- An `aws s3api get-object --endpoint-url http://...` (or any HTTP, non-TLS) call is denied by the `aws:SecureTransport: false` condition.
- A `put-object --server-side-encryption AES256` (SSE-S3) is **denied**; a `put-object --server-side-encryption aws:kms --ssekms-key-id <your-cmk>` **succeeds**.
- The deny statements use `Effect: Deny` with `"Bool": {"aws:SecureTransport": "false"}` and a `StringNotEquals` / `Null` pair on the KMS key id condition key.
- One sentence noting that **explicit deny always wins** over the bucket's default-encryption allow (the Week 2 evaluation rule, applied to storage).
- Committed.

**Hint.** Two statements. TLS: `Deny s3:* on arn:aws:s3:::<bucket> and /* when Bool aws:SecureTransport = false`. CMK enforcement: `Deny s3:PutObject when StringNotEquals s3:x-amz-server-side-encryption-aws-kms-key-id = <cmk-arn>` plus a second deny for `Null s3:x-amz-server-side-encryption-aws-kms-key-id = true` to catch the "no header at all" case. In CDK use `iam.PolicyStatement` with `effect: iam.Effect.DENY` and `conditions`. The default-encryption setting handles the *normal* path; the policy is the *guarantee* that a misbehaving client cannot opt out.

**Estimated time.** 1 hour.

---

## Problem 3 — A presigned-PUT path that constrains content-type and size

**Problem statement.** Build the presigned-upload path the mini-project will reuse. Write a small Lambda (Python, behind a Function URL is fine) that issues a **short-lived presigned `PUT` URL** for the Exercise 1 bucket, but locks it down: the URL must be valid for **300 seconds**, must require the uploader to send `Content-Type: image/jpeg`, and must constrain the object size to **at most 5 MB**. Then demonstrate that a compliant `curl --upload-file` succeeds and a non-compliant one (wrong content-type, or oversized) is rejected by S3.

**Deliverables.** The Lambda under `homework/p3-presign/` plus a file `notes/presign-proof.md` with: the generated URL (redact the signature), the successful upload's `200`, and the rejected upload's `403`.

**Acceptance criteria.**

- The presign call uses `ExpiresIn=300` and includes a `Content-Type` constraint so a mismatched upload is rejected.
- The size cap is enforced (use `generate_presigned_post` with `Conditions=[["content-length-range", 0, 5242880]]`, or document why you used a `PUT` with content-length signing).
- A compliant upload returns success and the object lands **encrypted with the bucket CMK** (verify with `head-object`).
- A non-compliant upload (wrong type or too big) is rejected by S3 with `403`, captured in the note.
- One sentence explaining why presigned URLs are safer than handing out IAM credentials *and* cheaper than proxying the bytes through your backend.
- Committed.

**Hint.** `boto3` client: `s3.generate_presigned_post(Bucket, Key, Fields={'Content-Type':'image/jpeg'}, Conditions=[{'Content-Type':'image/jpeg'}, ['content-length-range', 0, 5242880]], ExpiresIn=300)` returns a URL + form fields; upload with `curl -F` per field then `-F file=@...`. If you prefer a raw `PUT`, use `generate_presigned_url('put_object', Params={'Bucket':..,'Key':..,'ContentType':'image/jpeg','ServerSideEncryption':'aws:kms','SSEKMSKeyId':<arn>}, ExpiresIn=300)` and send the matching `Content-Type` header on the `curl --upload-file`. The signature covers exactly the params you sign, so a client that changes them breaks the signature.

**Estimated time.** 1 hour.

---

## Problem 4 — The CRR + transfer cost model for your own bucket

**Problem statement.** Using the **2026-approximate prices** from Lecture 2, build a monthly cost model for the mini-project's Cross-Region Replication at *your* projected volume. Assume the primary bucket ingests **20 GB/day** of new objects that all match the replication filter, replicated from `us-east-1` to `us-west-2`, replica stored in `STANDARD_IA`, 90-day retention on the replica. Compute each line separately: cross-region transfer, replica storage (rolling), and the incremental request cost. Then compute the **delta if you enable RTC** (assume RTC adds `$0.015/GB` replicated) and state, in one paragraph, the DR posture (backup/restore, pilot light, warm standby, active/active — Week 13 vocabulary) at which RTC's 15-minute SLA is worth paying for and at which it is waste.

**Deliverables.** A file `notes/crr-cost.md` with a line-itemized table (transfer / replica storage / requests / optional RTC) and the one-paragraph RTC verdict.

**Acceptance criteria.**

- Cross-region transfer computed as `20 GB/day × 30 × $0.02` = `$12/month` (show the arithmetic).
- Replica storage computed at the `STANDARD_IA` rate on the **rolling 90-day** volume (`~600 GB × $0.0125 ≈ $7.50/mo`), not the cumulative-forever volume.
- The RTC line is computed separately (`20 × 30 × $0.015 = $9/mo`) and labeled as *optional*.
- The verdict ties RTC's value to RPO: it is waste for backup/restore and pilot-light postures that tolerate minutes of lag, and earns its cost only when a tight, bounded RPO (warm standby / near-active-active) actually requires the 15-minute guarantee.
- Committed.

**Hint.** Reuse the worked transfer estimate in Lecture 2 §10 and scale it from 10 GB/day to 20. The replica in `STANDARD_IA` is cheaper than Standard precisely because it is a *recovery* asset you only read during a failover — never pay Standard prices twice for a copy. RTC is a per-GB charge on the replicated bytes; the SLA you buy is "99.99% of objects replicated within 15 minutes" plus the CloudWatch metrics to prove it.

**Estimated time.** 45 minutes.

---

## Problem 5 — gp3 right-sizing and the gp2 migration win

**Problem statement.** A teammate provisioned a **500 GB `gp2`** data volume to "get enough IOPS" for a Postgres instance that actually needs only **120 GB of capacity** but a sustained **9,000 IOPS** and **400 MB/s** throughput. Show, with numbers, that this is the classic `gp2` over-provisioning mistake and that **`gp3` decouples the three dimensions** to fix it. Compute the monthly cost of: (a) the existing `gp2` 500 GB volume, and (b) a right-sized `gp3` volume at **120 GB + 9,000 provisioned IOPS + 400 MB/s** provisioned throughput. Then write the one-command-conceptually `modify-volume` migration and note that it is **zero-downtime**.

**Deliverables.** A file `notes/gp3-rightsizing.md` with the two cost computations (capacity, IOPS, throughput lines shown separately for `gp3`), the dollar delta, and the migration command.

**Acceptance criteria.**

- `gp2` cost computed as `500 GB × $0.10/GB-mo = $50/mo`, with a note that on `gp2` the 500 GB was chosen to *buy IOPS* (3 IOPS/GB → 1,500 baseline), not capacity — and that it still does not reach 9,000 IOPS.
- `gp3` cost computed with the three lines: capacity `120 GB × $0.08 = $9.60`; IOPS — first 3,000 free, then `(9,000 − 3,000) × $0.005 = $30`; throughput — first 125 MB/s free, then `(400 − 125) × $0.040 = $11`. Total `≈ $50.60/mo`, **and it actually delivers the 9,000 IOPS / 400 MB/s the workload needs**, which the `gp2` volume never did.
- The note states the real lesson: on `gp2` you could not have bought 9,000 IOPS at 120 GB at all (you would need a 3,000 GB volume), so the right framing is "`gp3` makes the workload *possible and predictable*," and for workloads that fit inside the `gp3` free baselines the migration is a flat cost cut.
- The migration command is shown: `aws ec2 modify-volume --volume-id vol-xxxx --volume-type gp3 --iops 9000 --throughput 400` with a note that it applies online.
- Committed.

**Hint.** `gp3` 2026-approximate rates: `$0.08/GB-mo`, `$0.005/provisioned-IOPS-mo` above the free 3,000, `$0.040/provisioned-MB/s-mo` above the free 125 MB/s. The headline FinOps win that Lecture 2 calls "one of the most reliable on AWS" is that any `gp2` volume sitting at or below the `gp3` baselines becomes ~20% cheaper for free; the *bigger* win here is correctness — `gp2` literally cannot serve 9,000 IOPS at 120 GB. If you still need more than 16,000 IOPS or sub-millisecond consistency, that is the `io2` Block Express conversation from the Friday challenge.

**Estimated time.** 1 hour.

---

## Problem 6 — EFS lifecycle + the storage decision table, applied

**Problem statement.** Two parts. **(a)** On the Exercise 3 EFS file system, enable **EFS lifecycle management** so files not accessed in **30 days** move to **Infrequent Access** and files not accessed in **90 days** move to **Archive**, and confirm the setting via the CLI. **(b)** Apply the storage decision table from Lecture 2 §7 to four workloads, picking the single best primitive for each and justifying it in one sentence. The four workloads:

1. A GPU training job that must chew through a 4 TB dataset currently sitting in an S3 lake, at hundreds of GB/s, with results flushed back to S3.
2. A fleet of 12 Linux web servers that all need to read and write a shared `/uploads` directory with POSIX semantics.
3. A single self-managed transactional Postgres needing sustained 80,000 IOPS at sub-millisecond, consistent latency.
4. A pair of legacy Windows applications that need an SMB share joined to Active Directory.

**Deliverables.** A file `notes/efs-and-decisions.md` containing: the `describe-lifecycle-configuration` output proving IA-at-30d and Archive-at-90d, and one section per workload with the chosen primitive and a one-sentence justification.

**Acceptance criteria.**

- The EFS lifecycle is set and verified: `TransitionToIA = AFTER_30_DAYS` and `TransitionToArchive = AFTER_90_DAYS`, with the CLI output pasted in.
- Workload 1 → **FSx for Lustre** (S3-linked, hundreds of GB/s for HPC/ML scratch).
- Workload 2 → **EFS** (multi-AZ NFS, mounts on all 12 instances at once, POSIX).
- Workload 3 → **EBS `io2` Block Express** (sub-ms, up to 256k IOPS, 99.999% durability — `gp3` caps at 16,000 IOPS).
- Workload 4 → **FSx for Windows File Server** (managed SMB + AD; do not fake it with EFS).
- Committed.

**Hint.** Set EFS lifecycle in CDK with `fileSystem.lifecyclePolicy`-style props or via `aws efs put-lifecycle-configuration --file-system-id fs-xxxx --lifecycle-policies '[{"TransitionToIA":"AFTER_30_DAYS"},{"TransitionToArchive":"AFTER_90_DAYS"}]'`, then read it back with `aws efs describe-lifecycle-configuration --file-system-id fs-xxxx`. For the decision table, the compressed tree from Lecture 2 §6 answers all four directly: block-for-one-DB → EBS (io2 when IOPS-hungry), shared-POSIX-across-instances → EFS, HPC/ML-scratch-over-a-lake → FSx Lustre, Windows/SMB+AD → FSx Windows.

**Estimated time.** 45 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 45 min |
| 2 | 1 h 0 min |
| 3 | 1 h 0 min |
| 4 | 45 min |
| 5 | 1 h 0 min |
| 6 | 45 min |
| **Total** | **~5 h 15 min** |

(The remaining ~45 minutes of the 6-hour budget is for committing, reconciling your numbers against the Lecture 2 worked examples, and writing your engineering-journal entry for the week.)

---

## Grading rubric

Total **100 points**. A pass is 70.

| Criterion | Points | What earns full marks |
|-----------|-------:|-----------------------|
| **Minimum-object-size trap** (P1) | 15 | Four storage numbers correct; B's IA cell billed at 128 KB/object; verdict lifecycles A, leaves/aggregates B. |
| **Hardened bucket policy** (P2) | 20 | TLS-only and deny-non-CMK statements proven with two real `AccessDenied` outputs; "explicit deny wins" noted. |
| **Constrained presigned PUT** (P3) | 15 | 300s expiry, content-type and 5 MB size constraints enforced; compliant upload lands CMK-encrypted, non-compliant returns 403. |
| **CRR + transfer cost model** (P4) | 15 | Transfer, replica-IA storage, requests, and optional RTC line-itemized; RTC verdict tied to RPO/DR posture. |
| **gp3 right-sizing** (P5) | 15 | Both costs computed with gp3's three lines split; the "gp2 cannot reach 9,000 IOPS at 120 GB" correctness point made; online `modify-volume` shown. |
| **EFS lifecycle + decision table** (P6) | 15 | IA-at-30d/Archive-at-90d verified via CLI; all four workloads mapped to the correct primitive with sound one-liners. |
| **Hygiene (all)** | 5 | Every billable resource torn down; clean commits; no real account IDs, key ARNs with account context, or presigned signatures leaked in notes. |

**Automatic deductions.**

- −15 if a benchmark `io2`/`gp3` volume or its EC2 instance is left running after submission (a flat EBS line in Cost Explorer is the tell).
- −10 if the Exercise 3 EFS mount targets are left attached to a running EC2 instance, or any Fargate task / NAT-dependent compute is left up.
- −10 if any real account ID, full CMK ARN with account context, IAM access key, or un-redacted presigned signature is committed in plaintext.
- −5 if any CDK stack fails `cdk synth` or any OpenTofu config fails `tofu plan`.
- −5 if you replicated gigabytes (not a handful of small test objects) and the cross-region transfer line spiked — the point was to model the cost, not to incur it.

When you've finished all six, push your repo and open the [mini-project](./mini-project/README.md) — it fuses Exercises 1–3 into the fully lifecycled, CRR-replicated, KMS-encrypted, Object-Lambda-fronted storage layer with a shared-EFS demonstration. That bucket is the **data-lake foundation** reused in Week 11 and the multi-region DR week, so build it like you mean it.
