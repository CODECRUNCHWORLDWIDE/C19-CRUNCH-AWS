# Week 8 — Relational: RDS, Aurora, and Aurora Serverless v2

Welcome to **C19 · Crunch AWS**, Week 8. Phase 2 made you fluent in the moving parts: VPCs (Week 4), the compute spectrum (Week 5), storage and the lifecycle game (Week 6), and a delivery pipeline that builds and deploys without you touching a console (Week 7). This week opens Phase 3 — **Data, Events & AI** — and it starts where every real system eventually has a hard conversation: the relational database. By Friday you should be able to stand up a production-shaped Aurora PostgreSQL cluster from a blank CDK app, put RDS Proxy in front of it with IAM authentication, connect to it from an IRSA-bound pod on the EKS cluster you built in Week 5, run `pgbench` against the writer and the readers, force a failover and measure the recovery time with a stopwatch you wrote yourself, and then do the single most commercially important thing in this entire week: run the **ACU cost math** that tells you whether Aurora Serverless v2 saves you money or quietly sets fire to your budget.

This is also the **mid-program design-exam week**. The 3-hour multi-tenant-SaaS whiteboard sits at the center of the schedule on purpose. Eight weeks in, you have enough primitives — Organizations, IAM, VPC, EKS, S3, CI/CD, and now a relational layer — to defend a real architecture under questioning. The exam is not a quiz on Aurora; it is a test of whether you can stand at a whiteboard and design a multi-tenant SaaS backend on AWS while a reviewer probes your isolation model, your failure modes, and your bill. We treat Week 8 as the hinge of the course.

The first thing to internalize is that **Aurora is not "managed Postgres." It is a PostgreSQL query engine bolted onto a purpose-built distributed storage service, and the storage layer is where all the interesting behavior lives.** A community PostgreSQL instance writes 8 KB pages to a local disk and ships a write-ahead log to its replicas, which replay it. Aurora does not do that. Aurora's compute node ships only the *redo log records* to a fleet of six storage nodes spread across three Availability Zones, and the storage fleet materializes pages on demand. That one architectural decision is the reason Aurora failover is measured in seconds instead of minutes, the reason read replicas share storage with the writer instead of replaying a log, the reason a 64 TiB volume "just grows," and the reason your migration scripts behave subtly differently than they do on RDS. If you do not understand the storage layer, you will mis-predict failover time, over-provision replicas, and write migrations that lock tables you did not expect to lock. Lecture 1 is entirely about this.

The second thing to internalize is that **Aurora Serverless v2 is a billing mode, not a different database, and its economics are a step function disguised as a smooth curve.** Serverless v2 scales capacity in **ACUs** (Aurora Capacity Units — roughly 2 GiB of RAM plus associated CPU and network, billed per second). The marketing says "it scales to match your load and you only pay for what you use." That is true and also a trap. An ACU is billed at roughly **double the equivalent provisioned vCPU/RAM rate**, the floor you set (`minCapacity`) is billed even at 3am when nobody is awake, and the scale-up is fast but not instant — a spiky workload that touches 16 ACU for ten minutes an hour can cost *more* than a provisioned `db.r7g.xlarge` that runs flat all day. Lecture 2 is the spreadsheet: when Serverless v2 is genuinely cheaper (idle-heavy dev/test, unpredictable early-stage traffic, per-tenant micro-clusters), when it is a trap (steady production load, large floors, latency-sensitive workloads that cannot tolerate a scale-up stall), and how to compute the break-even point yourself instead of trusting a sales deck.

The third thing to internalize is that **everything you learn here has an open-source shadow, and you should know which trade-off you took.** Aurora's storage trick is genuinely hard to replicate; the closest open-source analog is running community PostgreSQL on EKS with **Patroni** for leader election and failover, plus streaming replicas — which gives you HA but not the shared-storage magic, so your failover is a log-replay catch-up and your replicas cost full storage each. For horizontal scale-out beyond a single writer, **Citus** (now an open-source PostgreSQL extension) shards a logical database across worker nodes, which Aurora does *not* do — Aurora scales reads, not writes. We will keep these comparators in view all week, because the senior move is never "Aurora because AWS"; it is "Aurora because we need second-class failover and read scale-out without operating Patroni, and we accept the 2× storage premium and the vendor lock-in, here is the number."

## Learning objectives

By the end of this week, you will be able to:

- **Explain** Aurora's log-as-the-database storage architecture — the six-way replicated, three-AZ storage fleet, quorum writes (4/6) and reads (3/6), and why this makes failover, read replicas, and volume growth behave differently than community PostgreSQL or RDS.
- **Compare** RDS Multi-AZ (synchronous standby, ~60–120s DNS failover) against Aurora (shared storage, ~10–30s failover, up to 15 reader replicas that promote without a log catch-up) and state, with numbers, when each is the right choice.
- **Provision** an Aurora PostgreSQL cluster — writer plus two readers across three AZs — from a clean AWS CDK (TypeScript) app, with a custom DB cluster parameter group, KMS encryption at rest, TLS enforced in transit, and Performance Insights enabled.
- **Stand up** RDS Proxy in front of the cluster with **IAM database authentication**, and connect to it from an **IRSA-bound EKS pod** that holds zero long-lived database passwords — the token is minted from the pod's IAM role at connect time.
- **Run** `pgbench` against the writer and the reader endpoint, read the TPS and latency numbers correctly, and explain why the reader endpoint round-robins across replicas.
- **Force** a failover (`failover-db-cluster`), measure **read recovery time** and **write recovery time** separately with a polling harness you wrote, and explain why they differ.
- **Compute** the Aurora Serverless v2 ACU cost for a given load profile by hand — floor cost, scale-up cost, the per-ACU-hour rate, the I/O-Optimized vs Standard decision — and find the **break-even point** against a provisioned instance.
- **Decide** between provisioned Aurora, Aurora Serverless v2, RDS Multi-AZ, and self-managed PostgreSQL-on-EKS-with-Patroni for a given workload, and defend the choice with a cost and an RTO/RPO number.
- **Configure** the production data-protection surface: automated backups and PITR (point-in-time recovery), manual snapshots, cross-region snapshot copy, and Aurora Global Database for sub-second cross-region replication.
- **Design**, at a whiteboard, the data layer of a multi-tenant SaaS — pool vs silo vs bridge isolation, connection-pool math under tenant fan-out, and the failure modes — and defend it for the full 3-hour mid-program design exam.

## Prerequisites

- **Weeks 1–7 of C19 complete.** You have a multi-account Organization, you can read and write IAM policies and `sts:AssumeRole` chains (Week 2), you have a production-shaped VPC with private and isolated subnets and VPC endpoints (Week 4), you have a running EKS cluster with IRSA wired up (Week 5), and you can deploy a CDK stack without thinking about the bootstrap dance (Week 3, Week 7).
- **A working CDK toolchain.** `node --version` ≥ 20, `cdk --version` ≥ 2.150.0, `aws --version` ≥ 2.17, and a `cdk bootstrap`-ed `dev` account. Python 3.12+ if you want to follow the Python-CDK asides.
- **`psql` and `pgbench` on your PATH.** `psql --version` ≥ 16 and `pgbench --version` ≥ 16. On macOS: `brew install libpq` (then add it to PATH) gives you `psql` and `pgbench` without a full server. On Debian/Ubuntu: `apt-get install postgresql-client postgresql-contrib`.
- **`kubectl` pointed at your Week-5 EKS cluster**, with the AWS Load Balancer Controller and the IRSA OIDC provider already installed. We reuse that cluster as the application tier this week.
- **A budget alarm you trust.** Aurora is the first service this course touches that bills *while you sleep*. A provisioned `db.r7g.large` writer plus two readers is roughly **$0.78/hour ≈ $19/day** in `us-east-1`. Set a budget, and **run `cdk destroy` every evening** unless you are mid-failover-test. The exercises are written so the whole cluster tears down cleanly.
- **PostgreSQL fluency at the `psql` prompt.** You can `CREATE TABLE`, write a `JOIN`, read an `EXPLAIN ANALYZE`, and you know what a transaction and an index are. We do not re-teach SQL. If `EXPLAIN (ANALYZE, BUFFERS)` is unfamiliar, skim a Postgres tutorial before Tuesday.

## Topics covered

- **Aurora storage architecture.** The log-structured, six-way replicated, three-AZ storage fleet. Quorum math: 4-of-6 writes, 3-of-6 reads, tolerating an AZ + 1 node failure for writes and an AZ failure for reads. Why "the redo log is the database." Protection groups, 10 GiB segments, continuous backup to S3.
- **RDS vs Aurora.** Engine differences (RDS runs the community engine on EBS; Aurora runs a forked engine on the storage service). Multi-AZ deployments (one-standby vs Multi-AZ-cluster three-instance). Read replicas: RDS async log-shipping replicas vs Aurora shared-storage replicas. Failover mechanics and timing for each.
- **Aurora Serverless v2.** ACUs and the scaling unit (~2 GiB RAM per ACU). The `minCapacity`/`maxCapacity` range (0.5–256 ACU, with a true scale-to-zero "auto-pause" available since the 2024–2025 updates). Per-second billing. The ACU price relative to provisioned. Scale-up latency and the cold-buffer problem. When it is cheaper; when it is a trap.
- **Parameter groups and option groups.** DB cluster parameter groups vs DB instance parameter groups. Static vs dynamic parameters and which require a reboot. `rds.force_ssl`, `shared_preload_libraries`, `max_connections`, `log_min_duration_statement`, `pg_stat_statements`. Why option groups are an RDS (not Aurora-Postgres) concern.
- **Performance Insights.** The `db.load` metric, average active sessions (AAS), wait-event analysis, top SQL, and the free 7-day vs paid long-term retention. Reading a Performance Insights dashboard the way an on-call engineer reads it.
- **RDS Proxy.** Connection pooling and multiplexing in front of Aurora. Why a Lambda fleet or a large EKS deployment exhausts `max_connections` without it. Pinning, and how to avoid it. IAM authentication through the proxy. Read/write splitting (proxy endpoints).
- **IAM database authentication.** The 15-minute auth token minted by `rds generate-db-auth-token` (or the SDK), the `rds_iam` role grant inside Postgres, the `rds-db:connect` IAM action, and how IRSA on EKS makes this passwordless end-to-end.
- **Encryption.** At rest with KMS (cluster-level, immutable after creation), in transit with TLS and `rds.force_ssl=1`, the RDS CA bundle (`rds-ca-rsa2048-g1`), and certificate rotation.
- **Backup and recovery.** Automated backups, the backup retention window, PITR to any second in the window, manual snapshots, snapshot sharing, cross-region snapshot copy (with a re-encrypt to a destination-region KMS key), and the RPO/RTO each gives you.
- **Aurora Global Database.** Sub-second cross-region physical replication via the storage layer (not logical replication), the secondary-region read replica, managed planned failover and unplanned "detach and promote," and the RPO/RTO budget it buys you. This is the capstone's cross-region analytical store.
- **Open-source comparators.** Community PostgreSQL on EKS with **Patroni** (etcd/Consul-backed leader election, streaming replication, `pg_rewind` reattach) for HA. **Citus** for write/horizontal scale-out (sharding) that Aurora does not provide. The honest trade-off table: control and portability vs operational burden.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. Note that **Wednesday is the 3-hour mid-program design exam** — block it, and do not run a benchmark in the last 30 minutes of an evening because Aurora bills while it idles.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Aurora storage architecture; RDS vs Aurora; provision via CDK |   2h     |   2h      |    0h      |   0.5h    |   1h     |     0h       |    0.5h    |    6h       |
| Tuesday   | RDS Proxy + IAM auth from IRSA; pgbench; parameter groups   |   2h     |   2h      |    0h      |   0.5h    |   1h     |     0h       |    0h      |    5.5h     |
| Wednesday | **Mid-program design exam (3h whiteboard)**; failover drill |   0.5h   |   1h      |    0h      |   0.5h    |   0h     |     0h       |    0.5h    |    5.5h     |
| Thursday  | Serverless v2 ACU cost math; the break-even challenge       |   1.5h   |   0h      |    2h      |   0.5h    |   1h     |     1h       |    0.5h    |    6.5h     |
| Friday    | Backups/PITR/cross-region/Global DB; mini-project work      |   0h     |   0h      |    0h      |   0.5h    |   1h     |     3h       |    0.5h    |    5h       |
| Saturday  | Mini-project deep work — failover report + cost comparison  |   0h     |   0h      |    0h      |   0h      |   0h     |     3.5h     |    0h      |    3.5h     |
| Sunday    | Quiz, review, polish                                        |   0h     |   0h      |    0h      |   1h      |   0h     |     2h       |    0h      |    3h       |
| **Total** |                                                             | **6h**   | **5h**    | **2h**     | **3.5h**  | **4h**   | **12.5h**    | **2h**     | **35h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The Aurora storage whitepaper, RDS/Aurora docs, pricing pages, Patroni/Citus docs, and the talks worth watching |
| [lecture-notes/01-aurora-storage-architecture.md](./lecture-notes/01-aurora-storage-architecture.md) | Aurora is a Postgres shell over a distributed storage engine — and why that matters for failover, cost, and migrations |
| [lecture-notes/02-acu-cost-math-serverless-v2.md](./lecture-notes/02-acu-cost-math-serverless-v2.md) | ACU cost math: when Aurora Serverless v2 is cheaper and when it is a trap |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-aurora-cluster-cdk.md](./exercises/exercise-01-aurora-cluster-cdk.md) | Stand up an Aurora Postgres cluster (writer + 2 readers across 3 AZs) via CDK |
| [exercises/exercise-02-rds-proxy-iam-pgbench.ts](./exercises/exercise-02-rds-proxy-iam-pgbench.ts) | Add RDS Proxy + IAM auth, connect from an IRSA pod, run pgbench |
| [exercises/exercise-03-failover-timer.py](./exercises/exercise-03-failover-timer.py) | Force a failover and measure read/write recovery time with a polling harness |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-serverless-v2-break-even.md](./challenges/challenge-01-serverless-v2-break-even.md) | Convert to Serverless v2, re-benchmark cost across three load profiles, produce the break-even analysis |
| [quiz.md](./quiz.md) | 13 questions on storage, failover, proxy, IAM auth, and ACU math, with an answer key |
| [homework.md](./homework.md) | Five practice problems with deliverables and a rubric |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the "Aurora Relational Layer" — CDK cluster, failover report, cost comparison; feeds the capstone |

## The "it tears down clean" promise

C19 has a recurring marker for any week that provisions billable infrastructure:

```
$ cdk destroy AuroraStack
✅  AuroraStack: destroyed
```

If your `cdk destroy` leaves an orphaned cluster, a retained snapshot you forgot about, or a NAT Gateway nobody is using, you are not done. We treat a dangling Aurora cluster the way Week 7 treated a compiler warning: a bug. Every exercise this week ends with a teardown step, and the mini-project rubric awards points for a clean `cdk destroy --all` followed by a `Cost Explorer` screenshot showing the spend stopped. The point of Week 8 is to make "spin it up, measure it, tear it down, read the bill" an ordinary Tuesday.

## A note on what's not here

Week 8 is the relational layer. It does **not** cover:

- **DynamoDB and single-table design.** That is Week 9 — the other half of the data story, and the harder mental model. Aurora is for relational, transactional, and analytical workloads with joins; DynamoDB is for known-access-pattern, single-digit-millisecond key-value and document workloads. We will draw the decision boundary explicitly in the design exam.
- **Redshift and the analytical data warehouse.** Aurora can serve analytical queries (the capstone uses it as the "analytical Aurora store"), but a petabyte-scale columnar warehouse is Week 11 material.
- **RDS for MySQL/MariaDB/Oracle/SQL Server deep dives.** We standardize on PostgreSQL — it is the engine the capstone uses and the one most worth knowing in 2026. The Aurora MySQL storage story is nearly identical; the engine-specific bits (option groups, `innodb_*` parameters) we mention but do not drill.
- **Database migration with DMS and SCT.** Moving an existing on-prem Oracle/MySQL database to Aurora is a real and large topic. We provision greenfield Aurora here; DMS is an elective.
- **Schema migration tooling (Flyway, Liquibase, `migrate`, Alembic).** You should use one. We assume you bring your own from C16; we focus on the AWS-specific behavior (Aurora DDL latency, the shared-storage implications for `ALTER TABLE`).

## Stretch goals

If you finish the regular work early and want to push further:

- Read the original **"Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases"** paper (SIGMOD 2017) end-to-end: <https://www.amazon.science/publications/amazon-aurora-design-considerations-for-high-throughput-cloud-native-relational-databases>. It is the source of every claim in Lecture 1.
- Stand up **Patroni** on your Week-5 EKS cluster with three PostgreSQL replicas and an etcd quorum, force a leader kill, and measure failover time. Compare the number to your Aurora failover from Exercise 3.
- Convert your Exercise-1 stack to **OpenTofu** and diff the plan against the CDK-synthesized CloudFormation. Note where the resource model differs (CDK's `DatabaseCluster` L2 construct vs the raw `aws_rds_cluster` + `aws_rds_cluster_instance` resources).
- Enable **Aurora I/O-Optimized** on a test cluster and re-run the Lecture-2 cost model to find the I/O-per-second break-even where I/O-Optimized beats Standard.
- Wire **`pg_stat_statements`** into the cluster parameter group, run a mixed workload, and find the top-5 queries by total time. Compare what `pg_stat_statements` shows against what Performance Insights shows for the same window.

## Up next

Continue to **Week 9 — DynamoDB & Single-Table Design** once you have shipped the mini-project with a measured failover report and a defensible cost comparison, and once you have survived the design exam. Week 9 is the other pole of the data story: where Aurora gives you joins, transactions, and SQL at the cost of a single writer and a 2× storage premium, DynamoDB gives you unbounded horizontal scale and single-digit-millisecond latency at the cost of modeling every access pattern up front. The capstone uses both — DynamoDB for transactional state, Aurora for the analytical store — so the decision frame you build this week is the one you will defend at the capstone oral.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
