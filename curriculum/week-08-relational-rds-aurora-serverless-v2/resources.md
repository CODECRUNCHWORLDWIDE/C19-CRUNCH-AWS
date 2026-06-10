# Week 8 — Resources

Every AWS doc here is free and current as of 2026. The open-source projects are public on GitHub. No paywalled material is linked. AWS pricing pages change weekly; **always re-check the dollar figure before you put it in a design doc** — the URLs below are stable, the numbers are not. Aurora is the first service in this course that bills while you sleep, so the pricing links matter more here than in any prior week.

## Required reading (work it into your week)

- **Amazon Aurora — "How Aurora storage works"** — the official description of the log-structured, six-way-replicated, three-AZ storage fleet. Read this before Lecture 1:
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.StorageReliability.html>
- **"Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases" (SIGMOD 2017)** — the paper. Every claim in Lecture 1 traces back to this. Read sections 2–4 at minimum:
  <https://www.amazon.science/publications/amazon-aurora-design-considerations-for-high-throughput-cloud-native-relational-databases>
- **Aurora Serverless v2 — capacity and scaling** — the ACU definition, the min/max range, scale-to-zero/auto-pause, and the scaling behavior:
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.setting-capacity.html>
- **Using Amazon RDS Proxy** — connection pooling, pinning, IAM auth through the proxy, read/write endpoints:
  <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html>
- **IAM database authentication for PostgreSQL** — the `rds-db:connect` action, the `rds_iam` role grant, and the 15-minute auth token:
  <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html>
- **Aurora high availability and failover** — what actually happens on `failover-db-cluster`, reader promotion, and the failover-tier priority:
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.AuroraHighAvailability.html>

## RDS vs Aurora depth

- **Amazon RDS Multi-AZ deployments** (one-standby vs the three-instance Multi-AZ DB cluster):
  <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html>
- **Working with Aurora read replicas** (shared-storage readers, up to 15, reader endpoint round-robin):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Replication.html>
- **Aurora I/O-Optimized vs Standard** (the storage/IO pricing model decision):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-storage-billing.html>
- **Aurora Global Database** (sub-second cross-region physical replication, managed planned failover, detach-and-promote):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html>

## Parameter groups, Performance Insights, encryption, backup

- **Working with DB cluster and DB instance parameter groups** (static vs dynamic, reboot semantics):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_WorkingWithDBClusterParamGroups.html>
- **Performance Insights — concepts** (DB load, average active sessions, wait events, top SQL):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_PerfInsights.html>
- **Encrypting Aurora resources with KMS** (cluster-level, immutable after creation):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Overview.Encryption.html>
- **Using TLS to encrypt connections** (the `rds.force_ssl` parameter, the `rds-ca-rsa2048-g1` CA bundle, rotation):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/UsingWithRDS.SSL.html>
- **Backing up and restoring an Aurora cluster** (automated backups, PITR, manual snapshots, cross-region copy):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Managing.Backups.html>

## Benchmarking

- **`pgbench` — the canonical PostgreSQL benchmark** (TPC-B-like default, custom scripts, scale factor, the `-c`/`-j`/`-T` flags):
  <https://www.postgresql.org/docs/current/pgbench.html>
- **`pg_stat_statements`** (per-statement aggregate timing; the open-source comparator to Performance Insights' Top SQL):
  <https://www.postgresql.org/docs/current/pgstatstatements.html>

## Pricing (re-check the dollars before quoting them)

- **Amazon Aurora pricing** (per-instance-hour by class, Serverless v2 per-ACU-hour, storage and I/O, I/O-Optimized): <https://aws.amazon.com/rds/aurora/pricing/>
- **Amazon RDS for PostgreSQL pricing** (the non-Aurora comparator): <https://aws.amazon.com/rds/postgresql/pricing/>
- **RDS Proxy pricing** (per-vCPU-hour of the underlying instance the proxy fronts): <https://aws.amazon.com/rds/proxy/pricing/>
- **AWS KMS pricing** (per-key-month + per-10k-requests; envelope-encryption request counts matter at scale): <https://aws.amazon.com/kms/pricing/>
- **AWS Pricing Calculator** — build the provisioned-vs-Serverless-v2 estimate before you deploy: <https://calculator.aws/>

## IaC references

- **AWS CDK v2 API — `aws-cdk-lib/aws-rds`** (`DatabaseCluster`, `ClusterInstance.provisioned` / `.serverlessV2`, `DatabaseProxy`, `ParameterGroup`):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_rds-readme.html>
- **AWS CDK v2 API — `aws-cdk-lib/aws-rds` `DatabaseCluster` construct reference** (the `serverlessV2MinCapacity` / `serverlessV2MaxCapacity` props):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_rds.DatabaseCluster.html>
- **CloudFormation `AWS::RDS::DBCluster` reference** (what CDK synthesizes; read it to debug a deploy):
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-rds-dbcluster.html>
- **CloudFormation `AWS::RDS::DBProxy` reference**:
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-rds-dbproxy.html>
- **OpenTofu / Terraform AWS provider — `aws_rds_cluster`, `aws_rds_cluster_instance`, `aws_db_proxy`** (the stretch-goal comparator):
  <https://search.opentofu.org/provider/hashicorp/aws/latest/docs/resources/rds_cluster>
- **`aws rds` CLI reference** (`create-db-cluster`, `failover-db-cluster`, `generate-db-auth-token`, `describe-db-clusters`):
  <https://docs.aws.amazon.com/cli/latest/reference/rds/>

## Talks (free, no signup)

- **re:Invent — "Deep dive on Amazon Aurora"** — the storage-architecture talk, refreshed most years; search the AWS Events channel for the latest:
  <https://www.youtube.com/@AWSEventsChannel>
- **re:Invent — "Amazon Aurora Serverless v2"** — the ACU-scaling and cost talk:
  <https://www.youtube.com/@AWSEventsChannel>
- **AWS re:Post — Aurora / RDS / RDS Proxy tags** — real operator questions, including pinning and failover-time threads:
  <https://repost.aws/tags/questions>

## Open-source comparators (read these to stay vendor-aware, not vendor-loyal)

- **PostgreSQL — high availability, load balancing, and replication** (streaming replication, the WAL, hot standby — the thing Aurora replaces with shared storage):
  <https://www.postgresql.org/docs/current/high-availability.html>
- **Patroni** — the de facto template for PostgreSQL HA: leader election over etcd/Consul/Kubernetes, automatic failover, `pg_rewind` reattach. This is what you run when you self-manage HA Postgres on EKS:
  <https://github.com/patroni/patroni>
- **CloudNativePG** — the Kubernetes operator most teams reach for in 2026 to run Postgres-on-EKS without hand-rolling Patroni manifests:
  <https://github.com/cloudnative-pg/cloudnative-pg>
- **Citus** — the open-source PostgreSQL extension that shards a logical database across worker nodes for write/horizontal scale-out — the thing Aurora does **not** do:
  <https://github.com/citusdata/citus>
- **PgBouncer** — the open-source connection pooler that RDS Proxy competes with; understand transaction-mode pooling and you understand RDS Proxy's pinning rules:
  <https://github.com/pgbouncer/pgbouncer>
- **`pgbench`** (ships with PostgreSQL) — the load generator you use in every exercise this week:
  <https://www.postgresql.org/docs/current/pgbench.html>

## Tools you'll use this week

- **`aws` CLI v2** — `aws rds`, `aws kms`, `aws secretsmanager`. Verify with `aws --version`.
- **AWS CDK v2** — `npm i -g aws-cdk`; `cdk --version` should report 2.150+.
- **`psql` and `pgbench`** — PostgreSQL 16+ client tools. macOS: `brew install libpq`. Debian/Ubuntu: `apt-get install postgresql-client postgresql-contrib`.
- **`kubectl`** — pointed at your Week-5 EKS cluster with IRSA configured.
- **`jq`** — for slicing CLI JSON (cluster members, failover events, auth tokens).
- **OpenTofu** — `tofu version` should report 1.8+ (stretch goal and homework).

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **ACU** | Aurora Capacity Unit. ~2 GiB RAM plus associated CPU/network, billed per second. The Serverless v2 scaling unit. |
| **Quorum (4/6, 3/6)** | Aurora storage acks a write when 4 of 6 segments confirm, and reads when 3 of 6 confirm. Survives an AZ + 1 node loss for writes. |
| **Redo log records** | The only thing an Aurora writer ships to storage. The storage fleet materializes pages from them — "the log is the database." |
| **Reader endpoint** | A single DNS name that round-robins across the cluster's reader instances. Connections, not queries, are balanced. |
| **Cluster endpoint (writer)** | The DNS name that always points at the current writer. Failover re-points it; the name does not change. |
| **RDS Proxy** | A managed connection pooler/multiplexer in front of RDS/Aurora. Defeats `max_connections` exhaustion from Lambda/EKS fleets. |
| **Pinning** | When RDS Proxy is forced to dedicate a backend connection to a client session (e.g., after `SET`, advisory locks, temp tables), losing the multiplexing benefit. |
| **IAM database auth** | Connecting with a short-lived (15 min) IAM-signed token instead of a password. `rds-db:connect` + the `rds_iam` Postgres role. |
| **IRSA** | IAM Roles for Service Accounts. An EKS pod assumes an IAM role via its service account's OIDC token — no node-level credentials. |
| **PITR** | Point-in-time recovery. Restore the cluster to any second within the backup retention window. |
| **Aurora Global Database** | Storage-layer physical replication to a secondary region with typically sub-second lag and a dedicated replication channel. |
| **Failover tier** | The promotion priority (0–15) on each reader. Lower tier promotes first when the writer fails. |
| **`rds.force_ssl`** | The cluster parameter that rejects non-TLS connections. Set to `1` in production. |

---

*If a link 404s, please open an issue so we can replace it.*
