# Week 6 — Quiz

Fourteen questions. Take it with your lecture notes closed. Aim for 12/14 before moving to Week 7. Answer key at the bottom — don't peek.

---

**Q1.** Since December 2020, what consistency does Amazon S3 provide for a `GET` issued immediately after a successful `PUT` of a new object?

- A) Eventual consistency — you may need to retry until the object appears.
- B) Strong read-after-write consistency — the `GET` reflects the `PUT` immediately, at no extra cost.
- C) Strong consistency only within the same Availability Zone.
- D) Strong consistency only if you enable a "Strong Consistency" bucket setting.

---

**Q2.** You have a workload writing one million 4 KB objects per day. Which statement is most accurate about cost?

- A) Storage will dominate the bill; move the objects to Standard-IA immediately.
- B) This is primarily a *request* cost problem, and Standard-IA would make it worse because of the 128 KB minimum-object-size charge.
- C) Glacier Deep Archive is the cheapest option and has no downside for tiny objects.
- D) Object count has no effect on cost; only total bytes matter.

---

**Q3.** What does enabling **S3 Bucket Keys** primarily reduce?

- A) S3 storage cost per GB.
- B) The number of KMS API calls (and thus KMS request cost) for SSE-KMS objects.
- C) Cross-region replication transfer cost.
- D) The minimum storage duration for IA objects.

---

**Q4.** A principal has `s3:GetObject` on a bucket whose objects are encrypted with SSE-KMS using a customer-managed key, but its `GET` requests fail with `AccessDenied`. Block Public Access and the bucket policy are not the issue. What is the most likely cause?

- A) The object is in Glacier Deep Archive and must be restored first.
- B) The KMS key policy does not grant the principal `kms:Decrypt`.
- C) The bucket has versioning disabled.
- D) The principal is missing `s3:ListBucket`.

---

**Q5.** Which lifecycle action should you set on essentially every production bucket to avoid silently paying for storage you cannot see in a normal `ListObjects`?

- A) `NoncurrentVersionTransition` to Glacier.
- B) `Expiration` after 1 day.
- C) `AbortIncompleteMultipartUpload` after N days.
- D) Transition to One-Zone-IA at 30 days.

---

**Q6.** You need millisecond retrieval but archive-tier storage pricing for compliance data you might occasionally read fast. Which storage class fits?

- A) Glacier Flexible Retrieval.
- B) Glacier Deep Archive.
- C) Glacier Instant Retrieval.
- D) One-Zone-IA.

---

**Q7.** What is the correct way to serve specific objects from a private bucket to the public internet in 2026?

- A) Set the four Block Public Access toggles to `false` and add a public-read bucket policy.
- B) Enable a public ACL on each object.
- C) Keep the bucket private and front it with CloudFront using Origin Access Control (or hand out presigned URLs).
- D) Move the objects to a separate "public" bucket with `RestrictPublicBuckets=false`.

---

**Q8.** What is the key difference between Object Lock **governance** mode and **compliance** mode?

- A) Governance encrypts; compliance does not.
- B) In governance mode a principal with `s3:BypassGovernanceRetention` can shorten/remove the lock; in compliance mode *no one*, including root, can until the retention expires.
- C) Compliance mode works only in `us-gov` regions.
- D) Governance mode requires versioning; compliance mode does not.

---

**Q9.** For Cross-Region Replication of SSE-KMS objects, which permission must the replication role have on the **destination** side?

- A) `kms:Decrypt` on the source key.
- B) `kms:Encrypt` / `kms:GenerateDataKey` on the destination region's key.
- C) `s3:GetObject` on the source bucket only.
- D) No KMS permission is needed; S3 handles replica encryption automatically.

---

**Q10.** When does **S3 Object Lambda** (transform-on-read) beat a pre-transform pipeline (transform-on-write)?

- A) When the output is reused many times and the transform is expensive.
- B) When you need per-requester variation, the transform is cheap, or the output is not worth persisting.
- C) Always — Object Lambda is strictly cheaper.
- D) Only for objects larger than 5 GB.

---

**Q11.** Compared to the old `gp2`, what is the defining advantage of `gp3` EBS volumes?

- A) `gp3` is HDD-backed and cheaper per GB for sequential workloads.
- B) `gp3` provides 99.999% durability like `io2`.
- C) `gp3` decouples IOPS and throughput from volume size, so you tune them independently instead of over-provisioning capacity to get IOPS.
- D) `gp3` supports Multi-Attach across many instances by default.

---

**Q12.** A workload needs one filesystem mounted concurrently, read/write, by both an ECS Fargate task and several EC2 instances across multiple AZs. Which AWS storage primitive fits?

- A) EBS `io2` with Multi-Attach.
- B) Amazon EFS.
- C) Amazon S3 mounted with `s3fs`.
- D) FSx for Windows File Server.

---

**Q13.** Which open-source project gives you EFS-like **POSIX** filesystem semantics while storing the actual data in an **object store** (like S3) and metadata in a fast database?

- A) MinIO.
- B) Ceph RBD.
- C) JuiceFS.
- D) SeaweedFS volume server.

---

**Q14.** You estimated a storage design at ~$215/month, but after a month the actual S3 bill is ~$470. Cost Explorer, grouped by usage type, shows the gap is almost entirely in `Requests-Tier1`. What most likely happened?

- A) The objects were larger than expected, so storage cost more.
- B) The workload is making far more `PUT`/`LIST`/transition requests than the estimate assumed — a request-cost miss, not a storage-cost miss. Aggregating small objects or reducing lifecycle transitions would help.
- C) Cross-region replication transfer was undercounted.
- D) KMS request cost; enable Bucket Keys to fix it.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — S3 has been strongly read-after-write consistent for all operations, in all regions, since December 2020, at no extra cost. Delete the old retry-until-it-appears hacks.
2. **B** — A million tiny objects is a request-cost problem. Standard-IA bills a 128 KB minimum per object, so 4 KB objects would be charged as 128 KB — 32x the bytes. IA is for big cold objects, not small ones.
3. **B** — Bucket Keys let S3 reuse a bucket-level data key instead of calling KMS per object, cutting KMS request cost ~99%. It does not change storage, replication, or duration pricing.
4. **B** — A principal needs *both* `s3:GetObject` (S3) and `kms:Decrypt` (KMS key policy) to read an SSE-KMS object. The classic bug is S3 permission granted, key permission forgotten.
5. **C** — `AbortIncompleteMultipartUpload`. Orphaned multipart parts accrue storage cost and do not appear in a normal `ListObjects`. Set it on every bucket.
6. **C** — Glacier Instant Retrieval: archive-tier storage price with millisecond retrieval. It is the `Glacier IR at 90d` step in the staircase.
7. **C** — Keep the bucket private; front it with CloudFront + Origin Access Control, or hand out presigned URLs. Public buckets are how data leaks happen; the 2026 default (BPA all-on, ACLs disabled) is correct.
8. **B** — Governance mode is bypassable by a privileged principal; compliance mode is immutable until the retention period expires, for everyone including root. Compliance mode is a one-way door — treat it like `rm -rf /`.
9. **B** — The replication role needs `kms:Encrypt`/`kms:GenerateDataKey` on the destination key (and `kms:Decrypt` on the source key). A `us-east-1` CMK cannot decrypt in `us-west-2`, so the replica must re-encrypt under a regional key.
10. **B** — Transform-on-read wins when output is not worth persisting, the transform is cheap, or you need per-requester variation (redact for one role, not another). Transform-on-write wins when expensive output is reused. It is the lazy-vs-eager read:write trade-off.
11. **C** — `gp3` decouples IOPS, throughput, and size; on `gp2` you had to over-provision capacity to get IOPS (3 IOPS/GB). Migrating `gp2` → `gp3` is a reliable FinOps win.
12. **B** — EFS is managed multi-AZ NFSv4.1 that mounts concurrently on many instances and on Fargate. `io2` Multi-Attach is limited and needs a cluster-aware filesystem; `s3fs` is not a real POSIX filesystem; FSx for Windows is SMB.
13. **C** — JuiceFS: POSIX/HDFS/S3 filesystem with data in an object store and metadata in Redis/TiKV/SQL. MinIO and SeaweedFS are object stores; Ceph RBD is block.
14. **B** — The gap is in request cost (`Requests-Tier1` = `PUT`/`LIST`/transition-class requests), so the estimate missed the request dimension, not storage. Aggregating small objects (à la Firehose) or reducing lifecycle transitions addresses it. (D is wrong because KMS request cost shows under a KMS usage type, not S3 Tier1 requests.)

</details>

---

If you scored under 10, re-read the lecture sections for the questions you missed (cost model and encryption are the two that trip people). If you scored 12+, you're ready for the [homework](./homework.md).
