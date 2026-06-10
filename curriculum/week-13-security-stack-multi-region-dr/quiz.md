# Week 13 — Quiz

Fourteen questions. Take it with your lecture notes closed. Aim for 12/14 before moving to Week 14. Answer key at the bottom — don't peek.

---

**Q1.** In KMS envelope encryption, what does a customer-managed key (CMK) actually encrypt?

- A) Your data directly, byte for byte.
- B) A data key, which in turn encrypts your data.
- C) The IAM policy attached to the resource.
- D) The S3 bucket name.

---

**Q2.** A KMS key policy contains `"Principal": {"AWS": "arn:aws:iam::1234:root"}, "Action": "kms:*"`. What does this statement do?

- A) Grants every principal in every account full control of the key.
- B) Delegates access decisions for this key to IAM within account 1234 — IAM policies can now grant on the key.
- C) Disables the key.
- D) Makes the key public.

---

**Q3.** Why can a single KMS CMK protect petabytes of data without ever becoming a bottleneck?

- A) KMS keys are infinitely large.
- B) The CMK only ever encrypts/decrypts small data keys, not the bulk data itself.
- C) KMS caches all your data in memory.
- D) Petabytes is below the KMS size limit.

---

**Q4.** You need a database password that rotates automatically and integrates with RDS. The right service is:

- A) SSM Parameter Store Standard tier.
- B) An environment variable in the Lambda config.
- C) AWS Secrets Manager.
- D) A hard-coded value in the CDK source.

---

**Q5.** GuardDuty's three **core** data sources (no agent required) are:

- A) S3 access logs, ELB logs, and WAF logs.
- B) CloudTrail, VPC Flow Logs, and DNS query logs.
- C) CloudWatch metrics, X-Ray traces, and Config rules.
- D) EBS snapshots, AMIs, and security groups.

---

**Q6.** What is Security Hub's primary job?

- A) To replace GuardDuty's threat detection.
- B) To aggregate posture — run FSBP/CIS controls and ingest GuardDuty/Inspector/Macie findings into one normalized (ASFF) view.
- C) To encrypt S3 buckets.
- D) To issue TLS certificates.

---

**Q7.** A teammate wants to point Macie at the entire 40 TB data lake for a one-time scan. Your objection is:

- A) Macie cannot scan S3.
- B) Macie bills per GB inspected, so a 40 TB scan is a real bill — scope it to a sample prefix.
- C) Macie only works on DynamoDB.
- D) Macie requires the data to be in Parquet.

---

**Q8.** For a custom WAF rule that blunts brute-force by blocking IPs that exceed a request threshold, you use a:

- A) Geo-match rule.
- B) Rate-based rule.
- C) Managed common rule set.
- D) Size-constraint rule.

---

**Q9.** Shield Advanced costs $3,000/month on a 1-year commitment. When is it worth buying?

- A) Always, for every account.
- B) When a DDoS-induced downtime or bill spike would cost more than ~$36k/year — i.e. real revenue-bearing production at scale.
- C) Never; Shield Standard covers everything.
- D) Only for non-production workloads.

---

**Q10.** RTO and RPO are, respectively:

- A) How much data you can lose; how long until you recover.
- B) How long until you recover service; how much data (in time) you can afford to lose.
- C) Two names for the same thing.
- D) Request timeout and replication timeout.

---

**Q11.** Order the four DR postures from **lowest cost / slowest recovery** to **highest cost / fastest recovery**:

- A) Active/active → warm standby → pilot light → backup & restore.
- B) Backup & restore → pilot light → warm standby → active/active.
- C) Pilot light → backup & restore → active/active → warm standby.
- D) Warm standby → active/active → backup & restore → pilot light.

---

**Q12.** You enable S3 Cross-Region Replication on a SSE-KMS-encrypted bucket, but objects in the destination Region are undecryptable. The most likely cause is:

- A) The destination bucket is in the wrong account.
- B) The source key is Region-locked, so the replica was encrypted with a key that doesn't exist in the destination — you need a multi-Region key (or a destination key) referenced as `replicaKmsKeyId`.
- C) S3 CRR does not support encryption.
- D) Versioning is too expensive.

---

**Q13.** During a Route 53 failover, why does a high DNS TTL hurt your RTO?

- A) It increases the health-check interval.
- B) Clients cache the dead primary's address for up to the TTL after the record flips, delaying when they reconnect to the DR Region.
- C) It deletes the secondary record.
- D) TTL has no effect on RTO.

---

**Q14.** DynamoDB Global Tables resolve a conflicting write to the same item key in two Regions by:

- A) Rejecting both writes.
- B) Last-writer-wins, by a reconciliation timestamp.
- C) Strong cross-Region consensus before each write.
- D) Merging the two items field by field.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Envelope encryption: the CMK encrypts a per-object data key; the data key encrypts the data. The CMK never touches the bulk data, which is why it scales and why deleting it destroys everything.
2. **B** — `:root` means "the account," and `kms:*` to it *delegates* authority to IAM for that account. Without this statement, no IAM policy can grant on the key. It is delegation, not a blanket grant — the single most misread line in KMS.
3. **B** — The CMK only crypts small (≤4 KB) data keys; the bulk encryption happens locally with the plaintext data key. One CMK → unbounded data.
4. **C** — Secrets Manager has built-in, Lambda-backed, RDS-integrated rotation. Parameter Store has no rotation; env vars and hard-coded values are not secrets.
5. **B** — CloudTrail, VPC Flow Logs, and DNS query logs, all agentless. The protection plans (EKS Runtime, S3, RDS, Lambda, Malware) add more sources but those three are the core.
6. **B** — Aggregation: continuous FSBP/CIS controls plus normalized ingestion of GuardDuty/Inspector/Macie findings into one ASFF pane. It does not replace GuardDuty's detection.
7. **B** — Macie bills per GB inspected; 40 TB is a large bill. Scope to a sample prefix (or use automated sampling) for ongoing monitoring; run full scans deliberately.
8. **B** — A rate-based rule blocks source IPs exceeding a request count in a rolling window. Geo-match, managed rules, and size constraints solve different problems.
9. **B** — Worth it when the avoided downtime/bill-spike cost exceeds the ~$36k/year premium, plus the value of the DDoS Response Team and cost protection — i.e. real production at scale. For a course capstone you reason about it and stop at Standard.
10. **B** — RTO = recovery *time* (forward from disaster: when am I back?). RPO = recovery *point* (backward from disaster: how much did I lose?). Independent numbers, both stated and proven.
11. **B** — Backup & restore (hours/hours, cheapest) → pilot light (tens of min/min) → warm standby (min/sec, high cost) → active/active (~0/~0, highest cost). Lower RTO/RPO always costs more.
12. **B** — The replica was encrypted with a Region-locked key absent in the destination. A multi-Region key (primary + replica sharing key material), referenced via `replicaKmsKeyId`, makes the replica decryptable. The most common silent DR failure.
13. **B** — After Route 53 flips the record, clients that cached the old answer keep using the dead primary until their cached TTL expires. The TTL is a floor on RTO; keep failover records at ≤60s.
14. **B** — Multi-active with last-writer-wins by reconciliation timestamp. It is eventual consistency with a defined conflict rule, not cross-Region consensus — your data model must tolerate it.

</details>

---

If you scored under 10, re-read the lecture for the questions you missed — especially the KMS key-policy delegation (Q2), the envelope-encryption mechanism (Q1/Q3), and the RTO/RPO/posture material (Q10–Q14), which the homework and the Friday drill both lean on. If you scored 13 or 14, you're ready for the [homework](./homework.md).
