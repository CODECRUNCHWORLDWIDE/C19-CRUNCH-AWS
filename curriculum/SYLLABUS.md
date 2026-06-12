# C19 · Crunch AWS — Syllabus

> **15 weeks intensive · ~540 hours · 36 hr/wk cadence · GPL-3.0**
> Prereq: C1 + C15, or equivalent Docker / Kubernetes / Terraform / Linux fluency.
> Tier: **Crunch Labs**. Sub-brand accent `#FF9900`.

The syllabus is ordered on a single conviction: **IAM and networking come before compute, single-table DynamoDB comes before anything serverless, and observability comes before "doing more services."** Every week ends with a working artifact and a cost report.

---

## Phases

| Phase | Weeks | Theme | Output |
|---|---|---|---|
| **1 — Foundations & Identity** | 1–3 | Mental model, Organizations, IAM, billing, CDK bootstrap | Multi-account org + IAM Identity Center + first CDK app |
| **2 — Compute, Network & Storage** | 4–7 | VPC, EC2/ECS/EKS/Lambda, S3, CloudFront, ECR, CI/CD | Containerized service on EKS + serverless API on Lambda |
| **3 — Data, Events & AI** | 8–11 | RDS/Aurora, DynamoDB, Kinesis/MSK/EventBridge/SQS, S3 data lake, SageMaker, Bedrock | Event-driven pipeline + ML inference endpoint |
| **4 — Production, Security, DR & Capstone** | 12–15 | Observability, security stack, multi-region DR, FinOps, capstone build, chaos drill | Production-grade capstone + runbook + postmortem |

---

## Week-by-week

### Phase 1 — Foundations & Identity

---

#### **Week 1 — The AWS Mental Model, Accounts & Billing**

- **Topics:** History of AWS as a set of primitives. Region/AZ/edge topology. The shared responsibility model. AWS account vs Organizations vs OUs vs SCPs. Root user hygiene. Free tier mechanics. Billing alerts, Budgets, Cost Explorer, Cost & Usage Reports. CLI, profiles, named credentials, `aws sso login`. CloudShell.
- **Lecture:** "Why AWS has 200+ services and how to navigate that — the seven service families and how to ignore the rest until you need them."
- **Hands-on lab:** Create a fresh AWS account. Enable MFA on root. Lock the root credentials in a sealed envelope (literally — write the steps in your runbook). Create an Organization with three OUs: `dev`, `stage`, `prod`. Apply an SCP that denies `us-east-1` to one OU and prove the deny. Configure AWS Budgets with $5 / $25 / $80 alerts. Pull a Cost & Usage Report into S3 and open it in Athena.
- **Skills earned:** Account-level posture, Organizations, SCP authoring, billing observability, CLI fluency.

---

#### **Week 2 — IAM Done Right**

- **Topics:** IAM users vs roles vs groups vs policies vs resource policies. Policy evaluation logic — explicit deny wins. Condition keys. `aws:PrincipalOrgID`, `aws:SourceIp`, `aws:RequestedRegion`. Permission boundaries (the only safe way to delegate). Session policies. `sts:AssumeRole` chains. Cross-account trust. Service-linked roles. Access Analyzer.
- **Lecture:** "Read this policy out loud. Now break it." A live exercise — Claude-Opus-style — picking apart 12 real-world IAM policies and finding the bug in each.
- **Hands-on lab:** Build a three-account topology (`identity`, `dev`, `prod`). Stand up IAM Identity Center, a single permission set, and human users that assume roles into `dev` and `prod`. Write a permission boundary that says "developers can do anything *except* IAM writes, KMS deletes, or production S3 buckets." Prove that the boundary blocks an over-privileged inline policy. Run Access Analyzer and resolve every finding.
- **Skills earned:** Production-grade IAM. The single most important week in this course.

---

#### **Week 3 — CDK, CloudFormation & Local Tooling**

- **Topics:** Infrastructure as code on AWS — CloudFormation as the substrate, CDK (TS + Python) as the ergonomic layer, Terraform/OpenTofu for cross-cloud, Pulumi briefly. Constructs (L1/L2/L3). `cdk bootstrap` (the chicken-and-egg IAM problem). CDK pipelines. Drift detection. SAM for serverless. LocalStack, dynamodb-local, MinIO for local dev.
- **Lecture:** "Why CDK lost the open-source war but won the AWS one — and when to use OpenTofu instead."
- **Hands-on lab:** Write a CDK app in TypeScript that provisions a VPC, an S3 bucket with KMS encryption and lifecycle rules, and a Lambda function that reads from the bucket. Deploy to `dev`. Re-implement the same stack in Python CDK. Then write the equivalent in OpenTofu and diff the result. Spin up LocalStack and run the Lambda against it locally with `sam local invoke`.
- **Skills earned:** CDK TS/Py, CloudFormation literacy, local emulation, IaC cross-tool fluency.

---

### Phase 2 — Compute, Network & Storage

---

#### **Week 4 — VPC, Networking & Edge**

- **Topics:** VPC design: CIDR planning, public vs private subnets, multi-AZ, route tables, IGW, NAT Gateway (and its bill), Egress-only IGW for IPv6. Security Groups vs NACLs. VPC endpoints (Gateway: S3, DynamoDB; Interface: everything else). PrivateLink. Transit Gateway for multi-VPC. VPC peering. Route 53 — public, private hosted zones, alias records, latency/geo/failover routing. CloudFront and edge locations. ACM-managed TLS. AWS WAF basics. Shield Standard vs Advanced.
- **Lecture:** "Three NAT Gateways will cost you more than your laptop. Here's the VPC endpoint trick."
- **Hands-on lab:** Build a production-shape VPC across three AZs: public + private + isolated subnets per AZ, one NAT Gateway, S3 + DynamoDB gateway endpoints, and Interface endpoints for STS, KMS, SSM, ECR API & DKR. Deploy a private EC2 instance and prove it can talk to S3 and ECR with **zero NAT traffic**. Put a Route 53 alias in front of an ALB serving a static "hello" page on CloudFront with WAF rate-limiting.
- **Skills earned:** Production VPC design, endpoint thinking, edge routing.

---

#### **Week 5 — Compute Spectrum: EC2 → ECS Fargate → EKS**

- **Topics:** EC2 instance families (the alphabet soup — `c`/`m`/`r`/`t`/`g`/`p`/`i`) and how to pick. AMIs, EBS, instance store, placement groups. Auto Scaling Groups, launch templates, mixed-instances policies, Spot. ECS Fargate vs ECS-on-EC2 vs EKS. EKS production patterns: managed node groups, Karpenter, Fargate profiles, IRSA, ALB Controller, External DNS, EBS CSI, AWS Load Balancer Controller. AWS Batch for embarrassingly parallel workloads.
- **Lecture:** "When to pick Lambda vs Fargate vs EKS vs EC2 — a real flowchart you can defend in a design review."
- **Hands-on lab:** Containerize a small FastAPI app. Deploy it three ways: (1) ECS Fargate behind an ALB, (2) EKS with Karpenter scaling Spot nodes and IRSA-scoped S3 access, (3) Lambda + API Gateway behind CloudFront. Measure cold-start, p50/p99 latency, and per-1M-request cost on each. Write a one-page decision doc on which you'd pick for a real product and why.
- **Skills earned:** Compute-platform judgment, EKS production patterns, real cost math.

---

#### **Week 6 — Storage: S3, EBS, EFS, FSx, and the Lifecycle Game**

- **Topics:** S3 storage classes (Standard, IA, One-Zone-IA, Glacier Instant/Flexible/Deep), lifecycle rules, intelligent tiering, object lock & retention, S3 versioning, replication (SRR/CRR), Object Lambda, S3 Select, multipart upload, presigned URLs, Block Public Access. EBS volume types (gp3 default, io2 Block Express for IOPS, st1/sc1 for throughput), snapshots, KMS-encrypted volumes. EFS (NFS, multi-AZ, IA tier). FSx for Lustre / Windows / NetApp ONTAP — when each matters. Open-source comparators: MinIO, Ceph, JuiceFS.
- **Lecture:** "S3 is a database. Treat it like one."
- **Hands-on lab:** Build an S3 bucket with KMS-CMK encryption, versioning, lifecycle (Standard → IA at 30d → Glacier IR at 90d → Deep Archive at 365d), CRR to a second region, and Object Lambda that watermarks JPGs on GET. Mount EFS into an ECS Fargate task and an EC2 instance simultaneously. Benchmark gp3 vs io2 on a synthetic Postgres workload.
- **Skills earned:** S3 mastery, storage cost engineering, replication topology.

---

#### **Week 7 — CI/CD on AWS: CodeBuild, CodePipeline, CodeDeploy, ECR**

- **Topics:** CodeCommit (and why most people use GitHub instead). CodeBuild — buildspec, caching, multi-architecture (`linux/arm64` for Graviton savings). CodePipeline — sources, stages, approvals. CodeDeploy — in-place vs blue/green, ECS deployment groups, Lambda traffic shifting (canary, linear, all-at-once). ECR — lifecycle policies, image scanning (basic and enhanced via Inspector), pull-through cache. Cross-account artifact buckets. GitHub Actions OIDC into AWS as a modern alternative.
- **Lecture:** "Your pipeline IAM role is more dangerous than your prod IAM role. Here's why."
- **Hands-on lab:** Build a CodePipeline triggered by GitHub: lint → test → CodeBuild builds a multi-arch container → pushes to ECR → CodeDeploy does a blue/green deploy onto ECS Fargate with a 10% canary, automatic rollback on CloudWatch alarm, and Lambda traffic shifting for a sibling Lambda function. Replicate the same flow with GitHub Actions + OIDC and compare.
- **Skills earned:** CI/CD on AWS with safety rails, OIDC federation, blue/green discipline.

---

### Phase 3 — Data, Events & AI

---

#### **Week 8 — Relational: RDS, Aurora, Aurora Serverless v2**

- **Topics:** RDS (Postgres, MySQL, MariaDB) vs Aurora (Postgres- and MySQL-compatible) — storage architecture, read replicas, failover. Aurora Serverless v2 (ACUs, scaling math, when it's cheaper, when it's a trap). Parameter groups, option groups. Performance Insights. Proxy for connection pooling. IAM database auth. Encryption at rest and in transit. PITR, snapshots, cross-region snapshot copy. Aurora Global Database. Open-source equivalents: vanilla Postgres on EKS, Patroni HA, Citus.
- **Lecture:** "Aurora is a Postgres shell over a distributed storage engine. That matters for failover, for cost, and for the way you write migrations."
- **Hands-on lab:** Stand up an Aurora Postgres cluster (writer + 2 readers across 3 AZs) via CDK. Connect via RDS Proxy with IAM auth from an IRSA-bound EKS pod. Run pgbench against it. Force a failover and measure read/write recovery time. Convert to Aurora Serverless v2 (0.5–8 ACU) and re-benchmark cost vs provisioned at three load profiles.
- **Skills earned:** Production Postgres on AWS, failover discipline, ACU cost math.

---

#### **Week 9 — DynamoDB & Single-Table Design**

- **Topics:** DynamoDB data model: partition key, sort key, items, attributes, secondary indexes. The single-table pattern (one table per service, multiple access patterns). GSIs vs LSIs. Sparse indexes. Write-sharding for hot partitions. Time-to-live (TTL). Streams → Lambda fan-out. Conditional writes, optimistic concurrency, transactions. On-demand vs provisioned (with autoscaling). Read/write capacity unit math. Global Tables for multi-region. DAX for caching. Open-source comparators: ScyllaDB, Cassandra, FoundationDB.
- **Lecture:** "Rick Houlihan was right. Here's the single-table design for a multi-tenant CRUD app, drawn live."
- **Hands-on lab:** Implement a DynamoDB single-table design for a multi-tenant SaaS CRUD app (users, organizations, projects, comments, audit log). Benchmark hot-partition behavior by hammering one partition key. Add a GSI for a reverse lookup. Add write-sharding to defeat the hot partition. Switch from on-demand to provisioned with autoscaling and measure the cost delta at steady-state, burst, and idle.
- **Skills earned:** The single hardest mental model in the AWS catalog. Once you have it, you have it.

---

#### **Week 10 — Event-Driven: SQS, SNS, EventBridge, Step Functions, Kinesis, MSK**

- **Topics:** SQS (standard vs FIFO, DLQ, visibility timeout, long polling). SNS (topics, fan-out, message filtering). EventBridge (default bus, custom bus, partner sources, archive & replay, schema registry, pipes). Step Functions — Standard (long-running, $$ per state transition) vs Express (sub-second, $$ per execution-second). Kinesis Data Streams (shards, KCL, enhanced fan-out). Kinesis Firehose (managed delivery to S3/Redshift/OpenSearch). MSK and MSK Serverless (managed Kafka). When to pick each. Open-source comparators: NATS, RabbitMQ, Kafka, Temporal.
- **Lecture:** "SQS, SNS, Kinesis, MSK, EventBridge — five overlapping primitives. Here's the decision table you'll defend in a design review."
- **Hands-on lab:** Build an event-driven order-processing pipeline: API Gateway → Lambda → EventBridge → (SQS for retry-able work + Step Functions Express for orchestration + Kinesis Firehose for analytics-to-S3). Add DLQs everywhere. Trigger a poison-pill message and watch it land in the DLQ. Replay the event from EventBridge archive. Swap EventBridge for MSK and discuss what changed.
- **Skills earned:** Event-driven architecture you can defend, replay/idempotency thinking.

---

#### **Week 11 — Data Lake & AI: S3 + Athena + Glue, OpenSearch, SageMaker, Bedrock**

- **Topics:** S3 as a data lake. Glue Catalog, Crawlers, ETL jobs. Athena (Presto under the hood) — partitioning, projection, columnar formats (Parquet, ORC), result reuse. Lake Formation for row/column-level security. Redshift basics (RA3, Spectrum). OpenSearch managed and Serverless. SageMaker Studio. SageMaker Training Jobs (Spot, distributed). SageMaker real-time endpoints, serverless endpoints, async endpoints, batch transform. Bedrock — managed access to Claude, Llama, Mistral, Titan. SageMaker JumpStart. Inferentia/Trainium accelerator notes. Open-source comparators: DuckDB, Trino, MinIO + Iceberg, Ray, vLLM.
- **Lecture:** "The data-lake-house pattern on AWS, and why Bedrock is a router not a model."
- **Hands-on lab:** Land NDJSON event data into S3 via Firehose. Crawl with Glue. Query with Athena, partition by date, convert to Parquet, re-query, measure the cost & latency improvement. Train a tiny scikit-learn classifier in SageMaker on Spot. Deploy it to a SageMaker real-time endpoint. Call it from Lambda. Compare cost and latency against a Bedrock Claude Haiku call on the same input.
- **Skills earned:** Data lake fluency, SageMaker inference path, Bedrock vs self-hosted decision frame.

---

### Phase 4 — Production, Security, DR & Capstone

---

#### **Week 12 — Observability: CloudWatch, X-Ray, OpenTelemetry, ADOT**

- **Topics:** CloudWatch Logs (log groups, retention, metric filters, Logs Insights), Metrics (custom metrics, embedded metric format), Alarms (composite, anomaly detection), Synthetics (canaries), RUM, Evidently. X-Ray for service maps and traces. OpenTelemetry as the vendor-neutral standard. ADOT (AWS Distro for OpenTelemetry) collector on EKS and Lambda. Container Insights. Lambda Insights. CloudWatch Application Signals. SLO/SLI thinking on AWS — error budgets, burn-rate alarms.
- **Lecture:** "Trace > metric > log. The three-tier dashboard, drawn for the capstone."
- **Hands-on lab:** Add OpenTelemetry instrumentation to the Week-10 event pipeline. Run the ADOT collector as a DaemonSet on EKS and as a Lambda extension on the serverless side. Send traces to X-Ray and metrics to CloudWatch. Build a burn-rate alarm on a 99.9% availability SLO with a 1-hour and 6-hour window. Trigger a synthetic outage and watch the alarm fire at the right moment.
- **Skills earned:** Production observability with vendor-neutral instrumentation and AWS backends.

---

#### **Week 13 — Security Stack & Multi-Region DR (Capstone build begins)**

- **Topics:** KMS deep — CMK vs AWS-managed, key policies vs grants, automatic rotation, multi-region keys, envelope encryption. Secrets Manager vs SSM Parameter Store. GuardDuty (threat detection from VPC Flow Logs, DNS, CloudTrail). Security Hub for posture aggregation. Macie for S3 PII scanning. Inspector for EC2/ECR vulnerability scanning. AWS Network Firewall. WAF with managed rule groups. Shield Advanced. ACM and ACM Private CA. Multi-region DR — Aurora Global, DynamoDB Global Tables, Route 53 health-checked failover, S3 CRR, RTO/RPO budgets.
- **Lecture:** "Pick your DR posture honestly: backup/restore, pilot light, warm standby, active/active. Each has a real cost number."
- **Hands-on lab:** Capstone build begins (see spec below). In parallel: enable GuardDuty org-wide, Security Hub, Macie on the data-lake bucket, Inspector on the EKS cluster. Resolve every Critical/High finding. Stand up DynamoDB Global Tables and Aurora Global Database in a second region. Configure Route 53 health-checked failover. Run a manual failover end-to-end.
- **Skills earned:** Security baseline, multi-region DR with real RTO/RPO numbers, capstone foundation.

---

#### **Week 14 — FinOps, Edge, Capstone build continues**

- **Topics:** Savings Plans (Compute vs EC2 Instance vs SageMaker) vs Reserved Instances. Spot strategies and interruption handling. Compute Optimizer recommendations. Graviton (arm64) savings. Cost & Usage Report into S3 → Athena → QuickSight dashboards. Anomaly Detection. Per-team cost allocation with tags and cost categories. CloudFront Functions vs Lambda@Edge — what runs where, what costs what. CloudFront origin failover.
- **Lecture:** "FinOps is just SRE for the bill. Run it like a service level."
- **Hands-on lab:** Capstone build continues. Add CloudFront in front of the capstone API with WAF + a Lambda@Edge function that injects a tenant header from a signed cookie. Build a QuickSight dashboard on the Cost & Usage Report partitioned by tag. Commit to one Savings Plan recommendation for the capstone steady-state and document the break-even.
- **Skills earned:** FinOps discipline, edge logic, cost-as-a-feature mindset.

---

#### **Week 15 — Capstone Defense, Chaos Drill & Career Pack**

- **Topics:** Capstone delivery. Chaos drill — AZ failover, DynamoDB throttle, Lambda concurrency exhaustion, NAT Gateway saturation, CloudFront origin failure. Postmortem authorship (blameless, five-whys, action items with owners and dates). Cohort architectural review. AWS Solutions Architect Professional and DevOps Engineer Professional cert-prep mapping. System-design interview drills (AWS-shop variant + FAANG variant). Public engineering portfolio polish.
- **Lecture:** "What a senior reviewer is actually looking for when they read your capstone."
- **Hands-on lab:** Run the chaos drill. Write the postmortem. Defend the capstone in a 30-minute oral with two peer reviewers. Record the 10-minute public walkthrough video. Push the runbook, dashboards-as-code, and incident playbook into the repo.
- **Skills earned:** Production-grade end-to-end ownership. The credential that the rest of the course was building toward.

---

## Assessment matrix

| Weight | Component | What is graded |
|---|---|---|
| 10% | Weekly labs (14 labs, drop lowest) | Working artifact + cost report + IaC committed |
| 10% | IAM policy reviews | Peer review of two cohort members' IAM in weeks 2, 5, 13 |
| 10% | Architectural reviews | Two peer architecture reviews, written, with diagrams |
| 10% | Engineering journal | Weekly reflection — what you tried, what failed, what you learned |
| 15% | Mid-program design exam (Week 8) | 3-hour whiteboard design: multi-tenant SaaS on AWS |
| 35% | Capstone system | Working system + IaC + runbook + dashboards + postmortem |
| 10% | Capstone oral defense | 30-minute oral, two peer reviewers + one lead reviewer |

A pass is **70%**. A signed Crunch Labs completion certificate requires **80%** and a passing capstone oral.

---

## Capstone specification

### Title
**Event-Driven SaaS Backbone**

### One-line spec
> EKS + Fargate hybrid → EventBridge → Lambda + Step Functions → DynamoDB single-table + Aurora analytical → SageMaker inference, with CDK IaC, OpenTelemetry tracing, multi-AZ + cross-region read replicas, and AWS WAF/Shield protection.

### Required architecture

- **Frontend / Edge:** CloudFront + WAF + ACM TLS. CloudFront Functions for header rewrites. Lambda@Edge for tenant routing.
- **API layer:** API Gateway HTTP API in front of Lambda for read/write CRUD; ALB in front of EKS for long-lived workloads; both behind the same CloudFront distribution.
- **Compute hybrid:** EKS with Karpenter Spot nodes for batch & long-running tasks; ECS Fargate for one stateful sidecar; Lambda for the event-handler layer.
- **Eventing:** EventBridge custom bus as the spine. SQS with DLQs for retry. Step Functions Express for orchestration. Kinesis Firehose → S3 for analytics.
- **Data:** DynamoDB single-table for transactional state, with Streams → Lambda fan-out. Aurora Postgres (multi-AZ + cross-region read replica) for analytical queries. S3 + Glue + Athena for the data lake.
- **AI:** A SageMaker real-time endpoint serving a small recommendation model, called from Lambda. A parallel Bedrock-Claude call for a comparison feature. Document the cost & latency trade-off.
- **Identity:** IAM Identity Center for humans. Cognito user pools for end users. IRSA on EKS, execution roles on Lambda. Permission boundaries on all developer roles.
- **Observability:** OpenTelemetry via ADOT collector. Traces to X-Ray, metrics to CloudWatch, logs to CloudWatch Logs. Burn-rate alarms on a 99.9% SLO. A Synthetics canary against the public API.
- **Security:** GuardDuty, Security Hub, Macie on the lake bucket, Inspector on ECR & EKS. KMS-CMK encryption everywhere. Secrets Manager. WAF managed rules + a custom rate-limit rule.
- **DR:** DynamoDB Global Tables. Aurora cross-region read replica. S3 CRR on the lake bucket. Route 53 health-checked failover. **Document RTO and RPO targets and prove them.**
- **FinOps:** Tag every resource with `team`, `service`, `environment`. Cost & Usage Report → Athena → QuickSight dashboard. One Savings Plan committed for steady-state.

### Deliverables

1. **CDK monorepo** (TS primary, one stack in Python) that deploys the entire system from zero with `cdk deploy --all`. CI on GitHub Actions with OIDC federation into AWS.
2. **Runbook** (`/runbook` in the repo): architecture diagrams, on-call rotation template, alarm catalog, top-10 incident playbooks.
3. **Dashboards as code** — CloudWatch dashboards defined in CDK, QuickSight assets exported.
4. **10-minute public walkthrough video** explaining the architecture and the trade-offs.
5. **Chaos drill postmortem** covering, at minimum:
   - **AZ failover** — kill one AZ's worth of EKS nodes and Aurora writer. Measure recovery.
   - **DynamoDB throttle** — force a hot partition and watch the system degrade. Show the mitigation.
   - **Lambda concurrency exhaustion** — saturate reserved concurrency and trace the back-pressure into SQS and DLQ.
   - **Bonus drill of your choice** — NAT saturation, CloudFront origin failure, KMS throttle, etc.
6. **Cost report** — actual dollar number for one week of capstone operation, with a tagged breakdown.

---

## Career engineering pack

### AWS certification map (we map your gaps; we do not certify)

- **AWS Certified Solutions Architect — Professional (SAP-C02).** Weeks 1, 4, 5, 8, 9, 10, 11, 13, 14 map directly. We provide a per-domain readiness checklist in `/career/sap-map.md`.
- **AWS Certified DevOps Engineer — Professional (DOP-C02).** Weeks 3, 7, 12, 13, 14, 15 map directly. Checklist in `/career/dop-map.md`.
- **AWS Certified Security — Specialty (SCS-C02).** Weeks 2, 13 form the spine; a short supplementary reading list lives in `/career/scs-map.md`.

### System-design interview prep

- **FAANG-shop variant** — generic distributed-systems design with AWS as one allowed substrate. Practiced in weeks 8, 10, 15.
- **AWS-shop variant** — explicit Well-Architected framing across the five pillars. Mock interviews in week 15.

### Production runbook template

- An EKS + Lambda hybrid runbook template ships in `/runbook-template/` and is filled in during the capstone.

### Portfolio

- A public capstone repository with diagrams, postmortem, and walkthrough video.
- One peer-reviewed architectural review writeup published on the cohort blog.

---

## License

GPL-3.0. See [`LICENSE`](./LICENSE).

> Crunch AWS is an engineering course. The certs are a side effect.
