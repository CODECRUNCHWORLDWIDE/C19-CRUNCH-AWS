# C19 · Crunch AWS — Charter

> Crunch Labs tier. Sub-brand **AWS**. Accent `#FF9900`. License GPL-3.0.
> Charter parent: [`../CRUNCH-LABS-CHARTER.md`](../CRUNCH-LABS-CHARTER.md).

This document explains why Crunch AWS exists, why it is shaped the way it is, and what we will and will not do inside it. It is the editorial constitution of the course. If a future maintainer wants to add, remove, or reorder content, they should be able to defend the change against the principles below.

---

## Why AWS as a discipline

AWS is the largest public cloud, the cloud with the most service primitives, and — by a wide margin — the cloud with the deepest **IAM model**. Those three facts are the reason this course exists and the reason it takes 15 weeks.

- **Largest** means most production systems you will encounter — at hyperscalers, startups, government, finance, defense — run at least partly on AWS. A senior engineer who cannot read an AWS architecture diagram is professionally narrow in 2026, regardless of what they personally prefer.
- **Most primitives** means AWS rewards depth, not breadth. A surface-level "I used Lambda once" engineer is dangerous on AWS in a way they are not on a smaller, more opinionated platform. We choose depth.
- **Deepest IAM** means the failure modes of AWS systems are concentrated in identity. Most public AWS incidents — leaked credentials, over-permissive S3 buckets, escalation through assumed roles — are IAM failures. We teach IAM in Week 2, *before compute*, on purpose.

AWS is also where the **biggest cost mistakes** in modern engineering happen. A misplaced NAT Gateway, an idle Aurora cluster, a runaway Kinesis shard, a SageMaker endpoint someone forgot to delete — these are not theoretical. Cost is a first-class topic, not an appendix.

---

## Why 15 weeks intensive

A 5-day "AWS bootcamp" produces engineers who can click around the console. A 15-week intensive at 36 hours per week produces engineers who can:

- Defend an architecture in front of a senior reviewer.
- Stand up a production-shape VPC + EKS + DynamoDB stack from scratch with CDK.
- Read a 40-line IAM policy and find the bug.
- Run a chaos drill, fail, write a postmortem, and ship the fix.
- Have a numerate conversation about cost.

The math: roughly 540 hours. That is the floor for production-grade competence on a platform this large. We have piloted 12-week and 18-week variants. 12 weeks is the **survey course we did not want to write**. 18 weeks loses focus. 15 is the right number.

The Mastery semester variant (a 24-week version with three additional capstones — security, ML platform, multi-region active-active) is reserved for a future cohort. Crunch AWS as documented here is the **intensive** edition.

---

## Topic ordering — the three deliberate inversions

This course's order of operations is deliberately *not* the order most AWS curricula use. Three inversions are load-bearing:

1. **IAM and networking come before compute.** Most AWS tutorials open with "launch an EC2 instance." We open with Organizations, Identity Center, IAM policy semantics, and VPC design. The reason: every production AWS outage with a name attached to it is an IAM or networking failure, not a compute failure. If you cannot reason about `sts:AssumeRole`, you cannot ship safely, no matter how many EC2 commands you know.

2. **Single-table DynamoDB comes before anything serverless.** The Lambda + DynamoDB pattern is the dominant serverless shape on AWS, and the place most engineers fail it is the data model. They reach for DynamoDB, try to use it like a relational database, hit a hot partition, blame the database, and migrate to Aurora at 4x the cost. We teach the single-table pattern *before* we let students build serverless systems, so the serverless lessons land on a correct foundation.

3. **Observability comes before "doing more services."** It is tempting to march through the AWS catalog — SageMaker, Bedrock, OpenSearch, Glue — before stopping to instrument. We resist that. The Week 12 observability week sits before the security/DR/capstone weeks because a system you cannot see is a system you cannot harden. Tracing first, then hardening.

---

## Open-source-first stance, in an AWS-dominant ecosystem

Crunch Labs is open-source-first. AWS is, by design, not. That tension is the editorial spine of this course.

We resolve it as follows:

- **Default to the open standard.** We teach Kubernetes (the API), not "EKS as a thing." We teach OpenTelemetry, not the proprietary X-Ray SDK. We teach OpenTofu/Terraform alongside CDK, so students leave with a portable IaC skill.
- **Use the AWS-native primitive where it is genuinely best-in-class.** Lambda, DynamoDB, SQS, S3, and Aurora Serverless v2 are extraordinary engineering products with no fully equivalent open-source replacement. We use them, name them, and teach them honestly.
- **Always cite the open-source comparator.** Every week's lecture names the alternatives: ScyllaDB/Cassandra for DynamoDB, MinIO/Ceph for S3, NATS/Kafka for Kinesis/SNS, Patroni for Aurora, Ray/vLLM for SageMaker, Trino/DuckDB for Athena. A Crunch AWS graduate should be able to migrate off AWS if business requirements demand it, and to argue against the migration when they do not.
- **Refuse the lock-in trap when it is gratuitous.** We do not teach Amplify as the way to build apps. We do not teach AWS-specific frameworks where a portable one exists. We do not let the course become an AWS marketing funnel.

The phrase that captures this is **vendor-aware, not vendor-loyal**. We will use AWS without endorsing AWS.

---

## Relationship to neighboring tracks

- **C15 — Crunch DevOps** is the **prerequisite**. C15 teaches Docker, Kubernetes, Terraform, and CI/CD as portable disciplines. Crunch AWS is the cloud-specific specialization that lands on top of that foundation. We will not re-teach Docker or `kubectl`.
- **C18 — Crunch GCP** is the **sibling**. The two courses share a pedagogical spine (IAM-first, IaC-first, observability-before-services, vendor-aware framing) and a comparable depth. Students who take both end up able to defend multi-cloud architectures honestly. We deliberately keep the two syllabi parallel so cross-listing is easy.
- **C22 — Crunch Mesh** is the **sequel**. Mesh covers distributed systems primitives that span clouds — consensus, service mesh, sagas, idempotency, active/active multi-region. Crunch AWS is the natural runway into Mesh because the capstone already lives across two regions.
- **C23 — Crunch Agents** is an **optional companion**. The Bedrock and SageMaker weeks of Crunch AWS are a foundation; Crunch Agents builds the orchestration layer on top.
- **C16 — Crunch Pro Web Backend** is **helpful, not required**. Students with weak application-layer fundamentals should take C16 before C19.

---

## What we will not do

- We will not teach to the certification exams as the primary objective. The certs are tracked in the Career Pack and are a side effect of doing the engineering well. We map your gaps; we do not coach to the test.
- We will not survey 200 services. We teach ~40 services to production depth. Every other service is reachable from the documentation once the fundamentals land.
- We will not pretend AWS is free. The cost framing is honest from Week 1.
- We will not let students ship a capstone without a chaos drill and a postmortem. That is the line between "I built it" and "I run it."
- We will not endorse AWS. We use it.

---

## Editorial conventions

- **Active verbs, restrained tone.** No marketing words. No emojis in lecture or syllabus body.
- **One signal-orange accent.** `#FF9900` is the AWS sub-brand color. It is used sparingly — for headers, callouts, and the repo nameplate. Body copy stays neutral.
- **Cite real services.** Every claim names the AWS service it touches.
- **Cost is a feature, not an appendix.** Every lab ends with a cost report.

---

## Maintenance

- **Maintainer:** Crunch AWS working group, Code Crunch Labs.
- **Cadence:** Major review once per AWS re:Invent cycle (December → February rewrite window). Minor patches as services change.
- **Deprecations:** When a covered service is deprecated by AWS (e.g., Cloud9, CodeCommit), the syllabus is patched within 60 days.
- **Contributions:** PRs welcome. Substantive curriculum changes require sign-off from two working-group members.

---

## Signature

> *Crunch AWS is the engineering academy's answer to the largest, most primitive-dense, most identity-deep cloud in production. It is taught in 15 weeks because that is what the material requires, with open-source comparators because that is what intellectual honesty requires, and with a chaos drill in the capstone because that is what the production world requires.*

— Code Crunch Labs · Crunch AWS Working Group · 2026.
