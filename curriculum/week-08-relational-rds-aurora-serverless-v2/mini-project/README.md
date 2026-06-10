# Mini-Project — The Aurora Relational Layer

> Deliver a CDK-deployed Aurora PostgreSQL cluster with **RDS Proxy + IAM auth**, a **measured failover report**, and a **provisioned-vs-Serverless-v2 cost comparison**. This is not a toy. It is the actual relational layer the capstone uses as its **analytical Aurora store (multi-AZ + cross-region read replica)**, and the cost-and-failover discipline you build here is the discipline the capstone's chaos drill will test. By the end you have a tear-downable, IAM-passwordless, failover-measured, cost-justified Aurora cluster and a report that would survive a senior review.

**Estimated time:** ~12.5 hours (split across Thursday, Friday, Saturday, Sunday in the suggested schedule).

---

## Why this project exists

Every real system eventually has a hard conversation with its relational database, and most teams lose it twice: once on **failover** (they never measured it, so the first real AZ outage is also the first time anyone learns the RTO) and once on **cost** (they clicked "Serverless because modern" and now pay 2–3× for a steady workload, or they over-provisioned a dev cluster that idles 90% of the time). This mini-project forces you to win both conversations before they happen, with artifacts:

- A **CDK stack** that stands up the cluster from zero, so the infrastructure is reviewable, diffable, and reproducible — not a console snowflake.
- A **passwordless connection path** (RDS Proxy + IAM auth + IRSA), so there is no long-lived database credential anywhere — the same posture Week 2 demanded for everything else.
- A **measured failover report**, so your RTO is a number you produced, not a number AWS marketed.
- A **cost comparison**, so the provisioned-vs-Serverless-v2 decision is defended with measured ACU math, not a vibe.

This compounds directly onto the capstone. The capstone spec calls for "Aurora Postgres (multi-AZ + cross-region read replica) for analytical queries." The cluster you build here *is* that store. The cross-region read replica you add in the stretch goal is the capstone's DR posture. The failover report you write here is the template for the capstone's "AZ failover — kill one AZ's worth of EKS nodes and Aurora writer; measure recovery" chaos drill. Build it like you will keep it, because you will.

---

## What you will build

One CDK app (TypeScript primary) named `aurora-relational-layer` with the following stacks, each deployable and tear-downable independently:

1. **`NetworkStack`** — reuse your Week-4 VPC (three AZs, isolated subnets, VPC endpoints) via lookup, or a minimal three-AZ isolated VPC fallback.
2. **`AuroraStack`** — the production cluster: writer + 2 readers across 3 AZs, KMS-encrypted at rest, `rds.force_ssl=1` in transit, a custom DB cluster parameter group (`pg_stat_statements`, `log_min_duration_statement`), Performance Insights on every instance, 7-day backup retention, and the master credential in Secrets Manager with managed rotation.
3. **`ProxyStack`** — an RDS Proxy in front of the cluster with `iamAuth: REQUIRED` and `requireTLS: true`, a read-only proxy endpoint, and the IRSA role allowing exactly `rds-db:connect` (resource-scoped to one DB user, trust-scoped to one EKS namespace + service account).
4. **`ServerlessStack`** — the same cluster shape as Serverless v2 (`0.5–8 ACU`), deployed for the cost comparison (you do not need it running simultaneously with `AuroraStack`).

Plus a `reports/` directory with three deliverable documents (below) and a `bin/` entrypoint that wires the stacks with explicit `env`.

---

## Deliverables

### Deliverable 1 — The CDK cluster (`AuroraStack` + `ProxyStack`)

A `cdk deploy AuroraStack ProxyStack` that stands up the full cluster and proxy from zero. Acceptance:

- Writer + exactly 2 readers, in **3 distinct AZs**, all `db.r7g.large`, all with Performance Insights enabled.
- `StorageEncrypted: true` with your **customer-managed KMS key** (not the default `aws/rds` key).
- `rds.force_ssl=1` proven: a `sslmode=disable` connection is rejected; `sslmode=require` succeeds.
- The master password is **only** in Secrets Manager. Grep your repo: there is no password literal anywhere.
- RDS Proxy fronts the cluster with **IAM auth required**, and you connected from the IRSA pod with **no stored password** (a `generate-db-auth-token` token), proven by a terminal transcript.
- `cdk destroy` removes everything billable with **no orphaned snapshot**.

### Deliverable 2 — The measured failover report (`reports/failover.md`)

Using the Exercise-3 harness (or your own equivalent), run a failover drill and produce a report containing:

- **Three runs minimum**, with `write_recovery_seconds` and `read_recovery_seconds` per run, plus **mean / min / max** for each.
- A **timeline** for at least one run (the harness prints it) cross-checked against the RDS `describe-events` "Started/Completed failover" events.
- A one-paragraph explanation of **why write recovery exceeds read recovery** (Lecture 1 §1.4 — writer CNAME re-point + volume open vs surviving-reader continuity).
- A stated **RTO** for the writer ("our measured RTO at `db.r7g.large` is X seconds, p-max across 3 runs Y seconds") and the **RPO** ("zero — Aurora's shared storage means the promoted reader sees all durable writes; there is no replication-lag data-loss window").
- A sentence on how this would change with **Aurora Global Database** for a *region* failure (RPO typically sub-second, RTO of a managed planned failover ~minutes; unplanned detach-and-promote larger).

### Deliverable 3 — The provisioned-vs-Serverless-v2 cost comparison (`reports/cost.md`)

The output of Challenge 1, written up as a decision document:

- The §2.4-shape table with **your measured** average-ACU numbers for steady / burst / idle.
- The **break-even average ACU** (`R_prov / R_acu`) and a one-line statement of what it means.
- A **recommendation per profile** consistent with the Lecture-2 decision tree, each with a dollar margin.
- An explicit accounting of **at least two of the five hidden costs** (the reader floors, the scale-up stall, I/O-Optimized, RDS Proxy cost, independent reader scaling).
- A final **recommendation for the capstone's analytical store**: provisioned or Serverless v2, and the one-sentence justification. (Hint: an analytical store with steady batch load looks like Profile A; a per-tenant analytical store that is mostly idle looks like Profile C. State which the capstone is and choose accordingly.)

### Deliverable 4 — The cost report (week-standard)

The recurring C19 marker. One line accounting for the week's spend:

```
Aurora cost · writer+2 readers r7g.large 3.0h × $0.276 = $2.48 · storage 12 GiB × $0.10/730 ≈ $0.02 ·
  Perf Insights free tier · RDS Proxy 0.6 vCPU-h × $0.015 ≈ $0.01 · KMS 1 key-mo prorated ≈ $0.01 · est. $2.52
```

If you cannot produce that line for your own cluster, you have not finished the week.

---

## Stretch goals (the capstone runway)

These are optional for the mini-project but **each is a piece of the capstone**, so doing them now is doing capstone work early:

1. **Cross-region read replica via Aurora Global Database.** Add a `secondary` region cluster (`addCluster` / `GlobalCluster`) with a read replica. Measure the cross-region replica lag (`AuroraGlobalDBReplicationLag` in CloudWatch — should be sub-second). This is the capstone's DR store, verbatim.
2. **PITR drill.** Restore the cluster to a point-in-time five minutes in the past (`restore-db-cluster-to-point-in-time`), confirm a row you deleted is back, then destroy the restored clone. Document the RTO of a PITR restore (minutes-to-tens-of-minutes — much larger than a failover).
3. **Cross-region snapshot copy.** Take a manual snapshot, copy it to a second region with a re-encrypt to a destination-region KMS key, and document the steps. This is the "backup/restore" DR tier from Week 13.
4. **`pg_stat_statements` vs Performance Insights.** Run a mixed workload, find the top-5 queries by total time in `pg_stat_statements`, and compare against Performance Insights' Top SQL for the same window. Note where they agree and disagree.
5. **OpenTofu parity.** Re-express `AuroraStack` in OpenTofu (`aws_rds_cluster` + `aws_rds_cluster_instance` + `aws_db_proxy`) and diff the resource graph against the CDK synth. Note where the raw resource model is more verbose than the L2 construct.

---

## Rules

- **CDK (TypeScript) is primary.** One stack may be Python if you want the practice. No console-clicking the cluster into existence — everything is code.
- **No long-lived database password reaches an application.** The proxy path uses IAM auth; the master secret is only ever read by the proxy and by you (once, to create the `rds_iam` user). If an app config has a `DB_PASSWORD`, you failed the security bar.
- **Every measurement is measured.** Failover times come from the harness, not the console clock. Average ACU comes from CloudWatch, not intuition. A claim without a number is not a deliverable.
- **It tears down clean.** `cdk destroy --all` leaves zero billable resources and zero retained snapshots you did not intend. Confirm with `aws rds describe-db-clusters` returning `[]` for your prefix.
- **Standard engine versions only** (Aurora PostgreSQL 16.x). No preview features the capstone cannot rely on.
- Tag every resource with `team`, `service=relational-layer`, `environment=dev` (the capstone FinOps requirement, rehearsed here).

---

## Suggested timeline

| Block | Hours | Work |
|---|---:|---|
| Thursday | 1h | `AuroraStack` + `ProxyStack` deploy clean; IRSA pod connects passwordless (reuse Exercises 1–2). |
| Friday | 3h | Failover drill — 3+ runs with the harness; write `reports/failover.md`; cross-check `describe-events`. |
| Saturday | 3.5h | Challenge 1 cost work folded in: deploy `ServerlessStack`, drive 3 profiles, capture ACU, write `reports/cost.md`. |
| Sunday | 2h | Polish all three reports, produce the cost-report line, `cdk destroy --all`, screenshot Cost Explorer showing spend stopped. |
| (within the above) | ~3h | A stretch goal if you are ahead — cross-region replica is the highest-value one for the capstone. |

---

## Grading rubric (100 points)

| Criterion | Points | What earns full marks |
|---|---:|---|
| **CDK cluster correctness** | 20 | Writer + 2 readers, 3 AZs, KMS-CMK, `force_ssl`, PI on, Secrets Manager master, clean synth/deploy. |
| **Passwordless proxy path** | 20 | RDS Proxy with IAM auth required, read-only endpoint, IRSA role scoped to one SA + one DB user, terminal transcript proving a no-password connect. |
| **Failover report** | 20 | 3+ runs, separate read/write recovery with mean/min/max, timeline cross-checked against RDS events, correct explanation of the read-vs-write gap, stated RTO/RPO. |
| **Cost comparison** | 20 | Three measured profiles, break-even ACU computed, per-profile recommendation matching the decision tree, ≥2 hidden costs accounted for, capstone-store recommendation. |
| **Security & teardown** | 10 | No password reaches an app; no `Resource: "*"` on `rds-db:connect`; IRSA trust pinned to one SA; `cdk destroy --all` clean; cost-report line produced. |
| **Reproducibility & hygiene** | 10 | Tags applied, README in the repo, deploy works from a fresh clone, no secrets committed, sensible commits. |

**Pass:** 70. **Excellent (capstone-ready):** 85+, which in practice means at least one stretch goal (the cross-region replica is the obvious one) is done and the cost report quantifies the scale-up stall.

---

## What you hand in

A Git repository (or a directory in your C19 monorepo) containing:

- `aurora-relational-layer/` — the CDK app (all four stacks, `bin/`, `lib/`, `cdk.json`).
- `reports/failover.md`, `reports/cost.md`, and the cost-report line in the repo `README.md`.
- `challenge-01-break-even/` artifacts (the `measurements.csv`, `breakeven.py`, and `REPORT.md` from Challenge 1) folded in or linked.
- A short top-level `README.md` explaining how to deploy, how to run the failover drill, and the final recommendation for the capstone's analytical store.

When the cluster deploys clean, the pod connects with no password, the failover report has a measured RTO, and the cost comparison names a winner per profile — you have the relational layer the capstone is built on. Tear it down, read the bill, and move to Week 9.
