# Week 5 — Compute Spectrum: EC2 → ECS Fargate → EKS

Welcome to the week where you stop having opinions about compute and start having *numbers*. By Friday you will have taken one small FastAPI service and deployed it three different ways — ECS Fargate behind an ALB, EKS with Karpenter scaling Spot nodes, and Lambda behind API Gateway and CloudFront — and you will have a benchmark table that tells you, in dollars and milliseconds, what each choice actually costs. Anyone can recite "Lambda is serverless, EKS is Kubernetes." This week is about being able to walk into a design review, draw the flowchart, and defend the pick when a principal engineer pokes at it.

The prerequisite mindset: **the compute decision is a cost decision, a latency decision, and an operational-burden decision — in that order, usually.** We assume you already have the VPC from Week 4 (three AZs, private + public subnets, S3/DynamoDB gateway endpoints, interface endpoints for ECR/STS/KMS/SSM). We assume you can read a Dockerfile and a Kubernetes manifest. We assume IAM from Week 2 is in your bones, because IRSA — IAM Roles for Service Accounts — is the single most-botched thing in EKS production, and you cannot fix it if you do not already understand `sts:AssumeRoleWithWebIdentity` and trust policies.

The one conviction that orders this week: **most teams reach for EKS too early and Lambda too late.** EKS is a $73/month control plane before you run a single pod, plus the standing cost of nodes you have to patch, plus a Karpenter/ALB-Controller/IRSA/CSI operational surface that needs an owner. Lambda is $0 when idle and bills per millisecond. Fargate sits in the middle: no node patching, no cluster fee on ECS, but you pay for vCPU-seconds whether the container is busy or not. The right answer is almost never "the platform I already know." By the end of this week you will be able to say *why* — with a table.

## Learning objectives

By the end of this week, you will be able to:

- **Choose** the right EC2 instance family (`c`/`m`/`r`/`t`/`g`/`p`/`i`/Graviton) for a workload from its CPU:memory:network:storage profile, and justify the size.
- **Distinguish** AMIs, EBS volume types (gp3/io2 Block Express/st1/sc1), and instance store, and pick the right durability/throughput trade-off.
- **Build** an Auto Scaling Group with a launch template and a mixed-instances policy that blends On-Demand and Spot across instance types without a single point of capacity failure.
- **Compare** ECS Fargate, ECS-on-EC2, and EKS on cost, blast radius, and operational burden — not on vibes.
- **Deploy** a containerized FastAPI service on ECS Fargate behind an Application Load Balancer with health checks, autoscaling, and a task execution role scoped to least privilege.
- **Stand up** an EKS cluster with managed node groups, Karpenter for Spot autoscaling, the AWS Load Balancer Controller, External DNS, the EBS CSI driver, and IRSA-scoped S3 access — all via CDK and `eksctl`/Helm.
- **Wire** IRSA correctly so a single pod's service account assumes exactly one IAM role and can read exactly one S3 prefix — and prove the negative (it cannot read anything else).
- **Deploy** the same service as Lambda + API Gateway HTTP API behind CloudFront, and reason about cold starts, provisioned concurrency, and the 15-minute / 10 GB / 6 MB-payload limits.
- **Compute** per-1M-request cost for each platform from the published 2026 pricing, including the parts people forget (NAT data, ALB LCUs, the EKS control-plane fee, CloudWatch logs).
- **Write** a one-page compute decision document that a senior reviewer would sign off on.

## Prerequisites

This week assumes you have completed Weeks 1–4 of C19, or have equivalent fluency. Specifically:

- **Week 2 IAM in your bones.** You can read a trust policy, explain `sts:AssumeRole` vs `sts:AssumeRoleWithWebIdentity`, and write a least-privilege policy with a `Condition`. IRSA is unforgiving here.
- **Week 3 CDK.** You can write a CDK stack in TypeScript, run `cdk synth`/`cdk deploy`, and read the generated CloudFormation. We use CDK (TS primary, one Python stack) and OpenTofu this week.
- **Week 4 VPC.** You have a multi-AZ VPC with private subnets, NAT, S3/DynamoDB gateway endpoints, and interface endpoints for ECR. Every deployment this week lands in private subnets.
- **Docker fluency** (from C15). You can write a multi-stage Dockerfile, build for `linux/arm64`, and read `docker inspect`.
- **Kubernetes basics** (from C15). Deployment, Service, Ingress, ServiceAccount, and `kubectl` are not new to you. We teach the *AWS-specific* parts: IRSA, Karpenter, the LB Controller.
- An AWS account you control, with the Week-4 VPC deployed. **EKS is the expensive week** — budget the control-plane fee and tear the cluster down each night with `cdk destroy` (we give you a cron pattern).

If you cannot read an IAM trust policy or write a multi-stage Dockerfile, stop and go back. We will not re-teach it, and IRSA will eat you alive.

## Topics covered

- **EC2 instance families** — the alphabet soup decoded: `t` (burstable), `m` (balanced), `c` (compute), `r` (memory), `i` (storage/NVMe), `g`/`p` (GPU), `inf`/`trn` (accelerators). Graviton (`g`-suffix, e.g. `m7g`, `c7g`) and the ~20% price/perf win for arm64-clean workloads.
- **AMIs** — what's baked in, golden AMIs vs bootstrap-at-boot, the Bottlerocket and AL2023 EKS-optimized AMIs.
- **Storage attached to compute** — EBS gp3 (the default you should pick), io2 Block Express (when you genuinely need >64k IOPS), st1/sc1 (throughput/cold), and instance store (ephemeral NVMe — fast, free with the instance, gone on stop).
- **Placement groups** — cluster (low-latency), spread (anti-affinity), partition (big distributed systems).
- **Auto Scaling Groups** — launch templates (not launch configurations, which are deprecated), desired/min/max, target-tracking vs step scaling, health checks, lifecycle hooks.
- **Mixed-instances policy & Spot** — diversify across instance types and AZs, `capacity-optimized` allocation, On-Demand base + Spot on top, interruption handling with the 2-minute notice and rebalance recommendations.
- **ECS Fargate vs ECS-on-EC2 vs EKS** — the three-way comparison on cost, cold-start, blast radius, and operational surface. When ECS Fargate is the boring-correct answer.
- **EKS production patterns** — managed node groups, Karpenter (the modern node autoscaler that replaced Cluster Autoscaler for most shops), Fargate profiles, IRSA, the AWS Load Balancer Controller, External DNS, the EBS CSI driver, Pod Identity (the newer IRSA alternative).
- **Lambda** — the serverless end of the spectrum: cold starts, SnapStart, provisioned concurrency, the limits (15 min, 10 GB RAM, 6 MB sync payload, 250 MB unzipped package or 10 GB container image), and Lambda Web Adapter for running FastAPI unchanged.
- **AWS Batch** — for embarrassingly parallel jobs, briefly: managed compute environments over Spot, array jobs, when it beats hand-rolled ASGs.
- **Real cost math** — per-1M-request cost on each platform, including NAT data processing, ALB LCUs, the EKS control-plane fee, and CloudWatch log ingestion.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | EC2 families, AMIs/EBS, ASGs, Spot; read pricing docs  |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Lambda vs Fargate vs EKS vs EC2 flowchart; ECS Fargate |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Wednesday | EKS production patterns: Karpenter, IRSA, LB Controller|    2h    |    2h     |     1h     |    0.5h   |   0.5h   |     0h       |    0.5h    |     6.5h    |
| Thursday  | Lambda + API Gateway + CloudFront; benchmark harness   |    0h    |    2h     |     1h     |    0.5h   |   1h     |     1.5h     |    0.5h    |     6.5h    |
| Friday    | Three-way benchmark; cost math; decision doc           |    0h    |    0h     |     1h     |    0.5h   |   0.5h   |     3h       |    0.5h    |     5.5h    |
| Saturday  | Mini-project: decision doc + benchmark write-up        |    0h    |    0h     |     0h     |    0h     |   0.5h   |     3h       |    0h      |     3.5h    |
| Sunday    | Quiz, review, tear-down cron, cost report              |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                        | **8h**   | **9.5h**  | **4h**     | **4h**    | **5h**   | **12h**      | **3.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated 2026 AWS docs, Karpenter/EKS guides, re:Invent talks, cost tools |
| [lecture-notes/01-when-to-pick-lambda-fargate-eks-ec2.md](./lecture-notes/01-when-to-pick-lambda-fargate-eks-ec2.md) | The defensible flowchart: cost, latency, operational burden, with real numbers |
| [lecture-notes/02-eks-production-patterns.md](./lecture-notes/02-eks-production-patterns.md) | Karpenter, IRSA, the AWS Load Balancer Controller, Spot node economics |
| [exercises/README.md](./exercises/README.md) | Index of the three deployment exercises |
| [exercises/exercise-01-fargate-alb.md](./exercises/exercise-01-fargate-alb.md) | Containerize FastAPI, deploy on ECS Fargate behind an ALB (CDK) |
| [exercises/exercise-02-eks-karpenter-irsa.py](./exercises/exercise-02-eks-karpenter-irsa.py) | Deploy the same app on EKS with Karpenter Spot nodes + IRSA-scoped S3 (Python CDK) |
| [exercises/exercise-03-lambda-apigw-cloudfront.ts](./exercises/exercise-03-lambda-apigw-cloudfront.ts) | Deploy the same app as Lambda + API Gateway behind CloudFront (TS CDK) |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-three-way-benchmark.md](./challenges/challenge-01-three-way-benchmark.md) | Measure cold-start, p50/p99, and per-1M-request cost across all three |
| [mini-project/README.md](./mini-project/README.md) | The one-page compute decision doc, backed by your benchmark |
| [quiz.md](./quiz.md) | 13 questions with an answer key |
| [homework.md](./homework.md) | Concrete homework with deliverables and a rubric |

## The "one workload, three platforms" promise

The spine of this week is a single FastAPI service — a `/healthz`, a `/compute` endpoint that does a little CPU work, and a `/read` endpoint that reads an object from S3. You will deploy that *same code* three ways. The discipline is that the application never changes: only the platform around it does. When your benchmark table shows Lambda at $0.42 per 1M requests idle-friendly but with a 380 ms cold-start p99, Fargate at a flat $X/month regardless of traffic, and EKS-on-Spot at the lowest cost-per-request at scale but with a control-plane floor — *that* is the artifact. The table is the deliverable. The opinions follow from it.

## A note on cost and tear-down

EKS bills the control plane at $0.10/hour (~$73/month) the moment the cluster exists, idle or not. Leaving a cluster up over a weekend is a $5 mistake; leaving it up for the month is a $73 one. We give you a `cdk destroy` cron pattern in the EKS exercise. **Run the EKS work in a single focused burst, tear it down nightly, and re-deploy in the morning.** Tag everything with `team`, `service`, `environment` so your Week-1 budget alerts and Cost Explorer can attribute the spend. The mini-project requires a cost report; if you have not tagged, you cannot produce it.

## Stretch goals

If you finish early and want to push further:

- Add **AWS Batch** as a fourth platform for the `/compute` endpoint reframed as a batch array job, and add it to the benchmark.
- Convert the Fargate task and the EKS nodes to **Graviton (`arm64`)** and re-measure cost — you should see ~20% off compute.
- Add **SnapStart** to the Lambda (now supported for Python and Java in 2026) and re-measure the cold-start p99.
- Replace **IRSA with EKS Pod Identity** in the EKS exercise and write two paragraphs on why you would (or would not) migrate a real cluster.

## Up next

Continue to **Week 6 — Storage: S3, EBS, EFS, FSx, and the Lifecycle Game** once you have pushed the mini-project decision doc and your benchmark table. The IRSA/Karpenter EKS setup and the decision frame you build this week feed directly into the **capstone's compute-hybrid layer** (EKS + Fargate + Lambda behind one CloudFront distribution).

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
