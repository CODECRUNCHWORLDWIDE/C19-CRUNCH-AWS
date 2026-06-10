# Week 5 — Resources

Every resource here is free to read. AWS documentation is free without an account. The Karpenter, AWS Load Balancer Controller, and External DNS projects are open source on GitHub. re:Invent talks are free on YouTube. No paywalled books are linked; where a book is genuinely the best source we name the relevant free chapter or the publisher's open preview.

Pricing changes. Every dollar figure in the lecture notes is dated to **2026** and to a named region (almost always `us-east-1` / `eu-west-1`). Always re-check the live pricing page before you commit a number to a design review.

## Required reading (work it into your week)

- **EC2 instance types** — the canonical family/size reference, kept current:
  <https://aws.amazon.com/ec2/instance-types/>
- **Amazon EBS volume types** — gp3 vs io2 Block Express vs st1/sc1, IOPS/throughput math:
  <https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html>
- **Auto Scaling Groups with multiple instance types and Spot** — the mixed-instances policy doc:
  <https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-mixed-instances-groups.html>
- **AWS Fargate pricing & the Fargate user guide for ECS**:
  <https://aws.amazon.com/fargate/pricing/> and <https://docs.aws.amazon.com/AmazonECS/latest/userguide/what-is-fargate.html>
- **Amazon EKS best practices guide** — the single most useful EKS document AWS publishes:
  <https://docs.aws.amazon.com/eks/latest/best-practices/introduction.html>
- **IAM roles for service accounts (IRSA)** — the trust-policy mechanics you must understand:
  <https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html>
- **AWS Lambda quotas & pricing** — the limits and the per-ms billing model:
  <https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html> and <https://aws.amazon.com/lambda/pricing/>

## EKS production patterns

- **Karpenter docs** — the modern node autoscaler; read NodePool, EC2NodeClass, consolidation, disruption:
  <https://karpenter.sh/docs/>
- **Karpenter on GitHub** — read the controller and the disruption logic if you want depth:
  <https://github.com/aws/karpenter-provider-aws>
- **AWS Load Balancer Controller** — provisions ALB/NLB from Ingress and Service objects:
  <https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/>
- **External DNS** — syncs Route 53 records from Ingress/Service:
  <https://kubernetes-sigs.github.io/external-dns/latest/>
- **EBS CSI driver** — the managed add-on for dynamic EBS provisioning on EKS:
  <https://docs.aws.amazon.com/eks/latest/userguide/ebs-csi.html>
- **EKS Pod Identity** — the newer alternative to IRSA, no OIDC provider per cluster:
  <https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html>
- **EKS managed node groups**:
  <https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html>
- **Bottlerocket** — the minimal container-optimized OS AWS recommends for EKS nodes:
  <https://aws.amazon.com/bottlerocket/>

## Spot & cost

- **Amazon EC2 Spot Instances** — interruption model, the 2-minute notice, rebalance recommendations:
  <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances.html>
- **Spot Instance Advisor** — interruption frequency and savings by instance type:
  <https://aws.amazon.com/ec2/spot/instance-advisor/>
- **AWS Pricing Calculator** — build a per-platform cost estimate you can paste into the decision doc:
  <https://calculator.aws/>
- **AWS Graviton** — the arm64 family and the price/perf story:
  <https://aws.amazon.com/ec2/graviton/>
- **Compute Optimizer** — right-sizing recommendations for EC2/ASG/Lambda/ECS:
  <https://docs.aws.amazon.com/compute-optimizer/latest/ug/what-is-compute-optimizer.html>

## CDK & IaC

- **AWS CDK v2 API reference** (TypeScript & Python) — `aws-ec2`, `aws-ecs`, `aws-ecs-patterns`, `aws-eks`, `aws-lambda`:
  <https://docs.aws.amazon.com/cdk/api/v2/>
- **`aws-cdk-lib/aws-ecs-patterns` `ApplicationLoadBalancedFargateService`** — the L3 that wires Fargate + ALB:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs_patterns-readme.html>
- **CDK EKS module** (`aws-eks-v2-alpha` / `aws-eks`) — clusters, managed node groups, Helm charts, IRSA:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_eks-readme.html>
- **`eksctl`** — the fastest path to a correct EKS cluster, and what most teams still use for bootstrap:
  <https://eksctl.io/>
- **OpenTofu** (the open-source Terraform fork) — for the cross-cloud comparison:
  <https://opentofu.org/docs/>
- **`terraform-aws-modules/eks`** — the reference EKS module for OpenTofu/Terraform shops:
  <https://github.com/terraform-aws-modules/terraform-aws-eks>

## The application layer

- **FastAPI** — the service we deploy three ways:
  <https://fastapi.tiangolo.com/>
- **AWS Lambda Web Adapter** — run FastAPI/Flask/Express unchanged on Lambda behind a function URL or API Gateway:
  <https://github.com/awslabs/aws-lambda-web-adapter>
- **Mangum** — the ASGI adapter for Lambda if you prefer it over the Web Adapter:
  <https://github.com/jordaneremieff/mangum>
- **Uvicorn** — the ASGI server we run inside the container:
  <https://www.uvicorn.org/>

## re:Invent & conference talks (free, no signup)

- **"Karpenter: Amazon EKS node autoscaling"** — search the AWS Events YouTube channel for the latest Karpenter deep-dive; the model has stabilized since the `v1` API:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Advanced Amazon EKS networking and the AWS Load Balancer Controller"** — re:Invent networking track, same channel.
- **"Optimizing Amazon EC2 Spot Instances"** — the capacity-optimized allocation strategy explained by the team that built it.
- **"AWS Lambda under the hood"** — Firecracker microVMs, the cold-start lifecycle, SnapStart.
- **AWS Containers from the Couch** — the EKS/ECS team's ongoing show, deep and practical:
  <https://www.youtube.com/@containersfromthecouch>

## Benchmarking tools

- **`hey`** — the simple HTTP load generator we use for p50/p99:
  <https://github.com/rakyll/hey>
- **`wrk`** — when you need more throughput than `hey` can push:
  <https://github.com/wg/wrk>
- **`oha`** — a modern `hey` alternative with a live TUI histogram:
  <https://github.com/hatoo/oha>
- **CloudWatch Logs Insights** — query Lambda `REPORT` lines for `Init Duration` (cold start) and `Billed Duration`:
  <https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html>

## Open-source comparators (vendor-aware, not vendor-loyal)

You should know what AWS is wrapping. Read at least one.

- **Kubernetes** — EKS is managed upstream k8s; the upstream docs are the source of truth for the API:
  <https://kubernetes.io/docs/>
- **KEDA** — event-driven pod autoscaling, the open-source piece Karpenter does not replace:
  <https://keda.sh/>
- **Knative** — the open-source "scale-to-zero containers" model that Lambda productizes:
  <https://knative.dev/docs/>
- **Firecracker** — the microVM that powers both Lambda and Fargate; read the design doc:
  <https://github.com/firecracker-microvm/firecracker>

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **ASG** | Auto Scaling Group — a managed fleet of EC2 instances with min/desired/max. |
| **Launch template** | The versioned spec (AMI, type, SG, user-data) an ASG launches instances from. Replaced launch configurations. |
| **Mixed-instances policy** | An ASG setting that lets one group span many instance types and mix On-Demand + Spot. |
| **Spot** | Spare EC2 capacity at 60–90% off, reclaimable with a 2-minute notice. |
| **Fargate** | Serverless containers — you give AWS a task definition, it runs it; no nodes to patch. |
| **EKS** | Elastic Kubernetes Service — AWS-managed upstream Kubernetes control plane. |
| **Managed node group** | EKS-managed EC2 worker nodes (an ASG under the hood) with lifecycle automation. |
| **Karpenter** | A node autoscaler that provisions right-sized EC2 directly from pending pods, faster than Cluster Autoscaler. |
| **IRSA** | IAM Roles for Service Accounts — a pod assumes an IAM role via an OIDC web-identity token. |
| **Pod Identity** | The newer IRSA alternative; an EKS agent injects credentials, no per-cluster OIDC provider. |
| **ALB Controller** | The AWS Load Balancer Controller; turns Ingress/Service objects into real ALBs/NLBs. |
| **External DNS** | Controller that writes Route 53 records from Ingress/Service annotations. |
| **EBS CSI driver** | Container Storage Interface driver that provisions EBS volumes for PersistentVolumeClaims. |
| **LCU** | Load Balancer Capacity Unit — the metered unit ALB/NLB bills on (new conns, active conns, bandwidth, rule evals). |
| **Cold start** | The first-invocation latency of a Lambda (or scaled-from-zero container) while the runtime initializes. |
| **Provisioned concurrency** | Pre-warmed Lambda execution environments that eliminate cold starts, billed by the GB-second. |
| **Graviton** | AWS's arm64 CPUs; ~20% better price/perf for arm64-clean workloads. |

---

*If a link 404s, please open an issue so we can replace it. Pricing figures are dated 2026 — verify live before quoting them in a review.*
