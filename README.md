# C19 · Crunch AWS — Amazon Web Services Engineering

> Crunch Labs · Sub-brand: **AWS** · Accent `#FF9900` · Length: 15 weeks intensive (~540 hours)
> Prereq: **C1** + **C15 (DevOps)** — or equivalent Docker / Kubernetes / Terraform fluency and Linux comfort from **C14**.
> License: **GPL-3.0**.

A production-engineering course on the largest public cloud. Fifteen weeks, end-to-end, with the assumption that you already write code, already deploy containers, and already know what a route table is. We do not survey AWS — we build with it. By the end you will design, ship, observe, and pay for a multi-AZ, event-driven, partly-serverless system on AWS, with IAM done right, IaC via CDK, and a chaos drill in your postmortem folder.

This is the AWS-specific sibling of **C18 · Crunch GCP** and the runway into **C22 · Crunch Mesh** (distributed systems). It is *vendor-aware, not vendor-loyal*: every AWS-native primitive we teach is shadowed by its open-source equivalent (EKS over plain k8s, S3 over MinIO, DynamoDB over ScyllaDB/Cassandra, Kinesis over Kafka/NATS, SageMaker over Ray/vLLM). You will leave knowing which trade-off you took, and why.

---

## Personas — who this track is for

1. **The Python developer moving to AWS.** You shipped FastAPI services in C1/C16. You have an EC2 instance you SSH into. You want to stop SSHing and start designing — IAM, VPCs, Lambda, EventBridge, DynamoDB single-table, CDK. Crunch AWS turns the "I clicked it in the console once" surface into a deployable, observable platform.

2. **The SRE prepping AWS Pro certs.** You know Linux, you know k8s, you have a Terraform module library. You want depth on EKS production patterns, multi-account governance with Organizations and SCPs, IAM permission boundaries, cross-region DR, and a real chaos drill. You want to walk into a **Solutions Architect Professional** or **DevOps Engineer Professional** interview and not be guessing.

3. **The cloud-curious mobile or web developer.** You ship iOS/Android/Next.js apps and use Firebase or a small backend friend. You want to own the backend — auth via Cognito, storage via S3 + CloudFront, push pipelines via SNS, a Lambda-and-DynamoDB API. C19 takes you from "consumer of a backend" to "owner of a backend that costs $40/month and survives an AZ outage".

4. **The mid backend engineer who has "used AWS" but does not really understand IAM.** You have copy-pasted IAM JSON for years. You do not understand `sts:AssumeRole` chains, permission boundaries, session policies, or why your CDK deploy needs three roles. Week 2 alone is worth the cost of admission.

---

## What you can do at the end — 12 capabilities

1. **Design a multi-account AWS Organization** with SCPs, OUs, dev/stage/prod isolation, centralized logging, and IAM Identity Center (formerly AWS SSO) for human access.
2. **Write IAM policies that pass a code review** — least-privilege, with conditions, permission boundaries, and AssumeRole chains explained on a whiteboard.
3. **Build production VPCs**: multi-AZ subnets, NAT strategy, TGW hub-and-spoke, PrivateLink, VPC endpoints to avoid egress cost, and Security Group vs NACL trade-offs.
4. **Run EKS in production** — IRSA (IAM Roles for Service Accounts), Karpenter autoscaling, ALB/NLB ingress, Container Insights, OpenTelemetry tracing, blue/green with Argo Rollouts.
5. **Design DynamoDB single-table** schemas — partition key + sort key, GSIs, sparse indexes, write sharding for hot partitions, Streams → Lambda fan-out, on-demand vs provisioned, and cost math.
6. **Compose event-driven systems** with EventBridge buses, SQS fan-out, SNS, Step Functions (Express vs Standard), Kinesis Data Streams, and MSK (managed Kafka) where ordering and replay matter.
7. **Ship serverless properly** — Lambda concurrency, reserved/provisioned, cold-start budgets, Lambda Powertools, layered code, Lambda@Edge for CDN logic, and a SAM/CDK pipeline.
8. **Run AWS as code** with CDK (TypeScript and Python), CloudFormation drift detection, Terraform/OpenTofu for cross-cloud, and a CodePipeline → CodeBuild → CodeDeploy delivery flow.
9. **Observe a system end-to-end** with CloudWatch Logs/Metrics/Alarms, X-Ray, OpenTelemetry via the ADOT collector, Synthetics for canaries, Container Insights, and a cost-aware metric budget.
10. **Harden production**: KMS keys with rotation, Secrets Manager, GuardDuty, Security Hub, Macie for S3 PII scanning, Inspector for EC2/ECR, AWS WAF + Shield, Network Firewall, ACM-managed TLS.
11. **Plan multi-region DR** — Aurora Global Database, DynamoDB Global Tables, Route 53 health-checked failover, S3 Cross-Region Replication, RPO/RTO budgets, and a runnable failover drill.
12. **Apply FinOps** — Savings Plans vs RIs, Spot for stateless workloads, Compute Optimizer, Cost Explorer cost & usage reports, anomaly detection, and a per-team unit-economics dashboard.

You will also have a **SageMaker** inference path: train or fine-tune a small model, deploy a real-time endpoint, route to it from Lambda, and benchmark cost vs Bedrock managed APIs.

---

## Prerequisites

**Required**

- **C1 — CrunchTime: The Code** (or equivalent Python fluency).
- **C15 — Crunch DevOps** (or 1+ year shipping Docker + Kubernetes + Terraform).
- **Linux fluency** — bash, systemd, networking, files vs sockets, processes vs threads (C14 covers this).
- **Git, SSH, command line** without friction.

**Helpful**

- **C16 — Crunch Pro Web Backend** if your application layer is shaky.
- Exposure to one other cloud (GCP, Azure) — comparative thinking pays off.
- An AWS account you control. We will run on free tier and Spot for most of the course and budget < $80 per student for the rest. More on cost below.

If you cannot read a `Dockerfile`, write a Terraform module, or draw a basic VPC, take **C15** first. We will not stop to re-teach it.

---

## Program at a glance — four phases

### Phase 1 — Foundations & Identity (Weeks 1–3)
AWS mental model. Accounts and Organizations. IAM in depth — users, roles, policies, conditions, permission boundaries, AssumeRole, session policies. IAM Identity Center for humans. The shared responsibility model. Region & AZ topology. Billing, budgets, and the cost-as-a-feature mindset. CLI, SDKs, and CDK bootstrap.

### Phase 2 — Compute, Network & Storage (Weeks 4–7)
VPC design. EC2 fundamentals → ECS Fargate → EKS. Lambda and serverless patterns. ALB/NLB/CloudFront/Route 53. S3 deep (storage classes, lifecycle, replication, Object Lambda). EBS/EFS/FSx. ECR. CDK and CodePipeline for shipping containers and functions.

### Phase 3 — Data, Events & AI (Weeks 8–11)
RDS and Aurora (incl. Serverless v2 and Global). DynamoDB single-table design from scratch. Kinesis, MSK, SQS, SNS, EventBridge, Step Functions. S3 + Athena + Glue + Lake Formation. OpenSearch. SageMaker Studio → Training → Endpoints; Bedrock for managed model access; Inferentia/Trainium notes.

### Phase 4 — Production, Security, DR & Capstone (Weeks 12–15)
Observability with CloudWatch + X-Ray + OpenTelemetry/ADOT. Security stack: KMS, Secrets Manager, GuardDuty, Security Hub, Macie, Inspector, WAF, Shield, Network Firewall. Multi-region DR. FinOps. Capstone build, chaos drill, postmortem, and cert/interview prep.

Full week-by-week is in [`SYLLABUS.md`](./SYLLABUS.md).

---

## Weekly cadence

Standard cadence: **36 hours per week** for 15 weeks (~540 hours total).

| Block | Hours | What happens |
|---|---|---|
| Architectural reading + reference docs (Mon) | 4 | Read the relevant AWS whitepaper / re:Invent talk / Well-Architected pillar. Annotate. |
| Lecture (Tue) | 3 | Cohort lecture with whiteboard sketch of the week's topology. |
| Build lab (Tue–Thu) | 18 | The week's hands-on. Code, IaC, deploy, break it, fix it. |
| Architectural review (Fri morning) | 3 | Cohort peer review of one another's IaC + IAM. |
| Chaos / observability drill (Fri afternoon) | 4 | Inject failure. Read your dashboards. Write what you learned. |
| Reflection + notes (Sat) | 4 | Engineering journal. Cost report. Tag what you didn't understand. |

Capstone weeks (13–15) reshape the cadence around the build.

---

## Cost expectations & free-tier guidance

AWS is *not* free, but this course is designed to keep total student spend **under $80** if you follow the rules. Budget assumptions and tactics:

- **Use the free tier** for EC2 t-class, Lambda, DynamoDB on-demand, S3, CloudWatch basics, SQS, SNS, and Cognito. Most of the first 7 weeks fits inside free tier.
- **Use Spot** for any EKS worker nodes, ECS Fargate Spot, and Batch workloads. Saves 60–85%.
- **LocalStack** for local AWS emulation of S3, DynamoDB, Lambda, SQS, SNS, Kinesis, Step Functions during development. Run iteration loops locally, deploy to real AWS only for the integration test.
- **dynamodb-local** and **MinIO** also work as drop-in dev replacements for DynamoDB and S3.
- **EKS is the most expensive single line item** ($72/mo for the control plane alone). We schedule EKS work in a single 2-week burst and tear the cluster down each night with a `cdk destroy` cron.
- **Budgets + anomaly detection** are configured **in week 1**, with $5 / $25 / $80 alert thresholds. You will get the email before you get the bill.
- **NAT Gateway** is the silent budget killer ($32/mo + data). We teach VPC endpoints and PrivateLink early so labs don't depend on NAT for egress.
- SageMaker, Bedrock, and Aurora Global incur real cost. Those weeks have **shared lab accounts** with sandboxed quotas.

If cost is a hard blocker, the entire course can be completed against **LocalStack + MinIO + dynamodb-local + KinD (EKS-equivalent)** for $0, at the price of not seeing real-AWS-only behaviors (IAM cross-account, CloudFront edge, GuardDuty findings).

---

## Recommended tracks

**Before C19**

- **C1 — CrunchTime: The Code** — Python foundation.
- **C14 — Crunch Linux** — Linux production fluency.
- **C15 — Crunch DevOps** — Docker, Kubernetes, Terraform, CI/CD. **Required.**
- **C16 — Crunch Pro Web Backend** — if your app layer is weak.

**After C19**

- **C22 — Crunch Mesh** — Distributed systems: consensus, service mesh, sagas, idempotency, multi-region active-active. The natural sequel.
- **C18 — Crunch GCP** — Sibling track. Take both and you can defend a multi-cloud architecture without flinching.
- **C23 — Crunch Agents** — If you want to pair the SageMaker/Bedrock weeks with autonomous-agent orchestration.

---

## Deliverables you walk away with

- A multi-account AWS Organization, with SCPs and IAM Identity Center, in your portfolio.
- A CDK monorepo (TypeScript primary, Python secondary) that deploys the capstone end-to-end.
- A **production runbook** for the capstone: dashboards, alarms, on-call playbook, failover drill, cost report.
- An **AWS SAP / DOP cert-prep map** keyed to each week's content (we do not certify you — we map your gaps).
- A signed **architectural review** of one cohort peer's capstone.
- A 10-minute capstone video walkthrough, public.

---

## License & maintainers

- **License:** GPL-3.0. Curriculum text and code samples are free to reuse, modify, and redistribute under GPL-3.0 terms. See [`LICENSE`](./LICENSE).
- **Maintained by:** Code Crunch Labs — Crunch AWS working group.
- **Charter:** see [`CHARTER.md`](./CHARTER.md) and the umbrella [`../CRUNCH-LABS-CHARTER.md`](../CRUNCH-LABS-CHARTER.md).
- Issues, errata, lab improvements: open a PR against this repo.

> Crunch AWS is not "AWS certification training." It is engineering training that happens to use AWS. The certs are a side effect.
