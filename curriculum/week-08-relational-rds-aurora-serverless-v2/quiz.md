# Week 8 — Quiz

Thirteen questions on Aurora storage, RDS vs Aurora, failover, RDS Proxy, IAM auth, encryption, backups, and ACU cost math. Take it with your lecture notes closed. Aim for **11/13** before moving to Week 9. Answer key at the bottom — don't peek.

---

**Q1.** What does an Aurora writer ship to its storage fleet on a commit?

- A) Full 8 KiB data pages, mirrored to six nodes.
- B) Only the redo log records; the storage fleet materializes pages on demand.
- C) The entire WAL plus a checkpointed copy of every dirty page.
- D) A logical-replication change stream consumed by each reader.

---

**Q2.** Aurora's storage volume is six-way replicated across three AZs. What are the write and read quorums?

- A) Write 3/6, read 4/6.
- B) Write 6/6, read 1/6.
- C) Write 4/6, read 3/6.
- D) Write 5/6, read 2/6.

---

**Q3.** Which failure does Aurora's quorum tolerate **for writes** without a write outage?

- A) The loss of one entire AZ (2 of 6 nodes).
- B) The loss of two entire AZs (4 of 6 nodes).
- C) The loss of an AZ plus one more node (3 of 6 nodes).
- D) No failure — any node loss blocks writes until repair.

---

**Q4.** Why can an Aurora read replica be promoted to writer in 10–30 seconds, far faster than an RDS Multi-AZ failover?

- A) Aurora pre-copies the WAL to all readers, so they are always fully replayed.
- B) Aurora readers share the writer's storage volume, so there is no private copy to catch up — promotion is mostly a DNS re-point plus opening the volume for writes.
- C) Aurora keeps a hot spare instance running in every AZ.
- D) RDS Multi-AZ failover is artificially throttled; the mechanisms are identical.

---

**Q5.** Your application's write connection string points at an Aurora **instance endpoint** (e.g. `mycluster-instance-1...`). What breaks on failover?

- A) Nothing — instance endpoints follow the writer automatically.
- B) The app keeps writing to an instance that may have been demoted to a reader (writes fail) or replaced; it should point at the **cluster (writer) endpoint** CNAME instead.
- C) Reads break but writes are fine.
- D) TLS validation fails because the certificate changes.

---

**Q6.** A team puts a steady production workload (~6 ACU of load, 24/7) on Aurora Serverless v2 `0.5–8 ACU` "to save money." Using `R_acu ≈ $0.12`/ACU-hr and a `db.r7g.large` at `$0.276`/hr, what is true?

- A) Serverless v2 is cheaper because it only bills for what you use.
- B) They cost the same; ACU pricing matches provisioned pricing.
- C) Serverless v2 costs roughly 2.6× more (~$525 vs ~$201/mo per node); steady load belongs on provisioned.
- D) Serverless v2 is cheaper only if they enable I/O-Optimized.

---

**Q7.** For a `db.r7g.large`-shaped workload, what is the approximate **break-even average ACU** below which Aurora Serverless v2 is cheaper than the provisioned instance?

- A) ~0.5 ACU.
- B) ~2.3 ACU (`R_prov / R_acu = 0.276 / 0.12`).
- C) ~8 ACU.
- D) There is no break-even; Serverless v2 is always cheaper.

---

**Q8.** Which workload is the **best** fit for Aurora Serverless v2 with `minCapacity = 0`?

- A) A latency-sensitive checkout path with a strict p99 SLO and spiky traffic.
- B) A steady analytical batch job that runs flat 24/7.
- C) A dev/test cluster used ~2 hours on weekdays and idle nights and weekends.
- D) A multi-region active-active write tier.

---

**Q9.** What is RDS Proxy's primary job in front of a large EKS/Lambda fleet?

- A) To encrypt data at rest.
- B) To multiplex many client connections onto a small pool of backend connections, preventing `max_connections` exhaustion.
- C) To shard writes across multiple writer instances.
- D) To replace the cluster's read replicas.

---

**Q10.** In the IAM-database-auth path from an IRSA-bound EKS pod, where does the connection credential come from?

- A) A long-lived password stored in a Kubernetes Secret.
- B) A 15-minute IAM auth token minted from the pod's IRSA role via `generate-db-auth-token`; the DB user was GRANTed `rds_iam`; no password is stored.
- C) The pod's node IAM role, shared by every pod on the node.
- D) The RDS master password, fetched from Secrets Manager at connect time.

---

**Q11.** Which statement about Aurora encryption is correct?

- A) You can enable storage encryption on an existing unencrypted cluster with a parameter change.
- B) Storage encryption is set at cluster creation with a KMS key and is **immutable** afterward; `rds.force_ssl=1` separately enforces TLS in transit.
- C) Aurora encrypts in transit by default and at rest only if you install an extension.
- D) The KMS key can be rotated to a different key in place at any time.

---

**Q12.** What does **point-in-time recovery (PITR)** give you that a manual snapshot does not?

- A) Cross-region durability.
- B) The ability to restore to **any second** within the backup retention window, not just the moments you happened to snapshot.
- C) Faster recovery than a failover.
- D) Encryption of the backup.

---

**Q13.** Aurora scales **reads** to 15 replicas but has exactly one writer. Which open-source option addresses **write/horizontal scale-out** that Aurora does not?

- A) Patroni.
- B) PgBouncer.
- C) Citus (sharding across worker nodes).
- D) CloudNativePG.

---
---

## Answer key

> Stop. Take the quiz first.

**A1 — B.** The defining fact of Aurora: the writer ships **only redo log records** to the six-node, three-AZ storage fleet, which materializes pages on demand. "The log is the database." (Lecture 1 §1.2.) This is what cuts write traffic ~7.7× vs mirrored-Postgres-on-EBS.

**A2 — C.** Write quorum **4/6**, read quorum **3/6**. The constraints `Vw + Vr > V` (4+3 > 6) and `Vw > V/2` (4 > 3) guarantee reads see the latest write and no split-brain. (Lecture 1 §1.3.)

**A3 — A.** Losing one AZ removes 2 of 6 nodes, leaving 4 — exactly the write quorum, so writes continue. Aurora survives an AZ loss for writes and **AZ + 1** (3 nodes) for reads. (Lecture 1 §1.3.)

**A4 — B.** Readers share the single shared-storage volume; there is no private per-replica copy to finish replaying, so promotion is a DNS re-point plus opening the volume for writes. RDS Multi-AZ must finish recovery on a private copy, hence 60–120s. (Lecture 1 §1.4.)

**A5 — B.** Instance endpoints pin to a specific instance, which may be demoted or replaced on failover. The **cluster (writer) endpoint** is a CNAME Aurora re-points at the promoted instance — the app's DSN never changes. (Lecture 1 §1.7.)

**A6 — C.** `6 ACU × $0.12 × 730 ≈ $525/mo` vs provisioned `$0.276 × 730 ≈ $201/mo` per node — roughly **2.6× more**. Steady load is the canonical Serverless-v2 trap. (Lecture 2 §2.4 Profile A.)

**A7 — B.** Break-even average ACU = `R_prov / R_acu = 0.276 / 0.12 ≈ 2.3 ACU`. The window length cancels; it is rate-only. Below it, Serverless v2 wins; above it, provisioned. (Lecture 2 §2.3.)

**A8 — C.** Idle-heavy dev/test with scale-to-zero is the slam dunk (5–20× cheaper). A and B are traps (latency-sensitive-spiky forces a high floor; steady belongs on provisioned). D is not a Serverless-v2 use case at all. (Lecture 2 §2.4 Profile C, §2.8.)

**A9 — B.** RDS Proxy multiplexes many client connections onto a small backend pool, preventing `max_connections` exhaustion from large fleets. It does not shard writes (C) or replace readers (D). (Lecture 1; resources.md "Using Amazon RDS Proxy.")

**A10 — B.** The pod's IRSA role mints a **15-minute** IAM token via `generate-db-auth-token`; the DB user is GRANTed `rds_iam`; **no password** is stored anywhere. (Exercise 2 Steps A–C.)

**A11 — B.** Storage encryption is chosen at creation with a KMS key and is **immutable** thereafter (to encrypt an existing unencrypted cluster you restore a snapshot into a new encrypted cluster). TLS in transit is enforced separately via `rds.force_ssl=1`. (resources.md; Lecture 1 §1.8.)

**A12 — B.** PITR restores to **any second** in the retention window using continuous backup, not just discrete snapshot points. (resources.md "Backing up and restoring.")

**A13 — C.** **Citus** shards a logical database across worker nodes for write/horizontal scale-out — the one thing Aurora's single writer cannot do. Patroni/CloudNativePG provide HA (still single writer); PgBouncer is a pooler. (Lecture 1 §1.9.)

---

**Scoring:** 11–13 correct, you are ready for Week 9. 8–10, re-read the lecture sections cited above. Below 8, re-read both lecture notes before the design exam — these are exactly the questions a reviewer asks at the whiteboard.
