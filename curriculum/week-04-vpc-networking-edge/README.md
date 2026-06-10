# Week 4 — VPC, Networking & Edge

Welcome to Phase 2 of **C19 · Crunch AWS**. Phase 1 gave you accounts, an Organization, IAM that actually holds, and a CDK app that bootstraps cleanly. This week you build the thing every compute, data, and capstone lab from here on will sit inside: a **production-shape VPC**. Get the network right once and you stop thinking about it. Get it wrong and you will pay for it — literally, on the NAT Gateway line of your bill, every hour, forever.

The conviction this week runs on: **networking comes before compute, and egress is a cost decision, not a default.** A junior engineer reaches for a NAT Gateway because the wizard offered one. A senior engineer asks "does this subnet need to reach the public internet at all, or does it just need to reach S3, ECR, and SSM?" — and then routes that traffic through VPC endpoints so it never touches NAT. The difference between those two engineers is about $100/month per environment and a meaningfully smaller attack surface.

By Friday you will have a three-AZ VPC with public, private, and isolated subnets per AZ; exactly **one** NAT Gateway (not three); gateway endpoints for S3 and DynamoDB; interface endpoints for STS, KMS, SSM, ECR API, and ECR DKR; and a private EC2 instance that pulls a container image and reads an S3 object with **zero bytes** crossing the NAT Gateway. Then you reach the edge: a Route 53 alias in front of an ALB, fronted by CloudFront with ACM-managed TLS and a WAF rate-limiting rule you can trip under load.

We write everything in **AWS CDK** (TypeScript as the primary, Python shown alongside), drop to **AWS CLI** to inspect and prove, read the generated **CloudFormation** so you know what the L2 constructs actually emit, and re-implement the core VPC in **OpenTofu** so you are never locked into one tool's mental model.

## Learning objectives

By the end of this week, you will be able to:

- **Plan** a non-overlapping CIDR scheme for a multi-account, multi-region estate — and explain why `10.0.0.0/16` per VPC with `/20` subnets is a defensible default.
- **Design** a three-AZ VPC with public, private (egress), and isolated (no-egress) subnet tiers, and articulate which workload belongs in which tier.
- **Distinguish** Internet Gateways, NAT Gateways, and egress-only IGWs, and **quantify** what each costs per hour and per GB.
- **Route** traffic correctly with route tables, and read a route table to predict where a packet goes.
- **Compare** Security Groups (stateful, instance-level, allow-only) against Network ACLs (stateless, subnet-level, allow+deny) and pick the right tool.
- **Provision** S3 and DynamoDB **gateway** endpoints and STS/KMS/SSM/ECR **interface** endpoints, and prove they carry AWS-service traffic off the NAT path.
- **Measure** NAT Gateway `BytesOutToDestination` in CloudWatch and demonstrate it stays flat while a private host talks to S3 and ECR.
- **Explain** PrivateLink, Transit Gateway, and VPC peering, and choose between them for a given multi-VPC topology.
- **Configure** Route 53 routing policies — simple, weighted, latency, failover, geolocation — and alias records to AWS resources.
- **Deliver** an HTTPS site through CloudFront with an ACM certificate in `us-east-1`, and attach an AWS WAF web ACL with a rate-based rule.
- **Distinguish** Shield Standard (free, always on) from Shield Advanced ($3,000/mo) and know when the second is justified.

## Prerequisites

This week assumes you have completed **C19 Weeks 1–3**, or have equivalent AWS fluency. Specifically:

- A working AWS account with **Budgets** configured (Week 1). You will create billable resources this week. A single NAT Gateway plus a few interface endpoints runs roughly **$0.05–0.08/hour** while up. Tear everything down each night with `cdk destroy`.
- **IAM** you trust (Week 2). You deploy with an assumed role, not root, not a long-lived user.
- A bootstrapped **CDK** environment (Week 3): `cdk bootstrap` has run in your target account/region, and `cdk deploy` of a trivial stack works.
- **Node.js 20+** and the AWS CDK v2 CLI (`npm i -g aws-cdk`), plus **Python 3.12+** if you want to run the Python samples. **OpenTofu 1.8+** for the IaC cross-check. The **AWS CLI v2** on your `PATH`.
- Comfort reading a `Dockerfile`, a Terraform module, and a basic network diagram. If you cannot draw a VPC with subnets and a route table from memory by the end of the week, re-do the exercises.

You do **not** need prior AWS networking depth. We start at CIDR math. If you have only ever clicked "Create VPC" in the console and accepted the defaults, this week will feel like the first time someone explained what those defaults actually did.

## Topics covered

- **CIDR planning**: RFC 1918 ranges, why `/16` per VPC, carving `/20` subnets, leaving room for growth, avoiding overlap across accounts and regions (the Transit Gateway tax of bad planning).
- **Subnet tiers**: public (route to IGW), private with egress (route to NAT), isolated (no default route off-VPC). Why three AZs and not two.
- **Internet Gateway** — the horizontally-scaled, free, region-level door to the public internet.
- **NAT Gateway** — what it costs (`~$0.045/hr` + `~$0.045/GB` processed in most regions), why three of them is the classic budget mistake, and the single-NAT and zero-NAT patterns.
- **Egress-only Internet Gateway** for IPv6 outbound-only.
- **Route tables** — main vs custom, subnet associations, route priority (longest-prefix match), the `0.0.0.0/0` default route.
- **Security Groups vs NACLs** — stateful vs stateless, allow-only vs allow+deny, instance vs subnet scope, the ephemeral-port gotcha with NACLs.
- **VPC endpoints** — **gateway** endpoints (S3, DynamoDB; free; route-table based) vs **interface** endpoints (everything else; PrivateLink ENIs; ~$0.01/hr each + data). Endpoint policies.
- **PrivateLink** — exposing and consuming a service privately via an NLB + endpoint service.
- **Transit Gateway** vs **VPC peering** — hub-and-spoke at scale vs simple one-to-one, transitivity, cost, and route propagation.
- **Route 53** — public vs private hosted zones, alias vs CNAME, and routing policies: simple, weighted, latency, failover (with health checks), geolocation, geoproximity.
- **CloudFront** — distributions, origins, OAC (Origin Access Control), cache behaviors, edge locations.
- **ACM** — managed TLS, DNS validation, and the `us-east-1` requirement for CloudFront certs.
- **AWS WAF** — web ACLs, managed rule groups, and **rate-based rules**.
- **Shield Standard vs Advanced** — what's free and automatic, and what $3,000/month buys you.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                      | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Read VPC + Well-Architected; CIDR planning; subnet tiers   |   1h     |   1h      |    0h      |   0.5h    |   1h     |    0h        |   1h       |   4.5h      |
| Tuesday   | Lecture 1 (NAT vs endpoints); build the 3-AZ VPC (ex. 1)   |   2h     |   2h      |    0h      |   0.5h    |   1h     |    0h        |   0.5h     |   6h        |
| Wednesday | Endpoints (ex. 2); prove zero-NAT (ex. 3); SG vs NACL      |   1h     |   2.5h    |    0h      |   0.5h    |   1h     |    1h        |   0.5h     |   6.5h      |
| Thursday  | Lecture 2 (Route 53 / CloudFront / ACM / WAF); challenge   |   2h     |   0h      |    2h      |   0.5h    |   1h     |    1h        |   0.5h     |   7h        |
| Friday    | Mini-project build: VPC + edge wiring                       |   0h     |   0h      |    1h      |   0.5h    |   1h     |    3h        |   0.5h     |   6h        |
| Saturday  | Mini-project deep work; cost report; teardown drill         |   0h     |   0h      |    0h      |   0h      |   1h     |    3h        |   0.5h     |   4.5h      |
| Sunday    | Quiz, architectural review, notes                           |   0h     |   0h      |    0h      |   1h     |   0h     |    0.5h      |   0h       |   1.5h      |
| **Total** |                                                            | **6h**   | **5.5h**  | **3h**     | **3.5h**  | **6h**   | **11.5h**    | **3.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Current (2026) AWS docs, Well-Architected pillars, re:Invent talks, and tools |
| [lecture-notes/01-nat-gateway-vs-vpc-endpoints.md](./lecture-notes/01-nat-gateway-vs-vpc-endpoints.md) | "Three NAT Gateways Will Cost You More Than Your Laptop — Here's the VPC Endpoint Trick" |
| [lecture-notes/02-edge-routing-route53-cloudfront-acm-waf.md](./lecture-notes/02-edge-routing-route53-cloudfront-acm-waf.md) | "Edge Routing Done Right: Route 53 Policies, CloudFront, ACM TLS, and WAF Rate-Limiting" |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-three-az-vpc.md](./exercises/exercise-01-three-az-vpc.md) | Build a 3-AZ VPC with public/private/isolated subnets and a single NAT Gateway |
| [exercises/exercise-02-vpc-endpoints.ts](./exercises/exercise-02-vpc-endpoints.ts) | Add S3 + DynamoDB gateway endpoints and interface endpoints for STS/KMS/SSM/ECR |
| [exercises/exercise-03-prove-zero-nat.ts](./exercises/exercise-03-prove-zero-nat.ts) | Deploy a private EC2 instance and prove zero NAT data-processing for AWS-service traffic |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-edge-rate-limit.md](./challenges/challenge-01-edge-rate-limit.md) | Route 53 → CloudFront → ALB with a WAF rate-limit rule, tripped under load |
| [quiz.md](./quiz.md) | 14 questions with an answer key |
| [homework.md](./homework.md) | Six problems with deliverables and a rubric |
| [mini-project/README.md](./mini-project/README.md) | The production VPC + edge foundation reused by every later lab |

## The "zero-NAT" promise

C19 uses a recurring marker this week. Every endpoint exercise ends with a CloudWatch query that should show a flat line:

```
NatGateway BytesOutToDestination (sum, 5-min): 0
```

If your private host is talking to S3 or ECR and that metric is climbing, your traffic is going out the expensive door. You are not done until it's flat. The entire point of Week 4 is to make that flat line ordinary.

## Stretch goals

If you finish the regular work early and want to push further:

- Re-implement the full VPC in **OpenTofu** and `tofu plan` against the deployed CDK stack to compare resource graphs. Starter HCL ships in the mini-project folder.
- Add **IPv6** to the VPC and an egress-only Internet Gateway, then give the isolated tier IPv6-only outbound to S3.
- Stand up a **second VPC** and connect it to the first with VPC peering, then re-do it with a Transit Gateway and compare the route tables.
- Read the CloudFormation that `ec2.Vpc` emits (`cdk synth`) and count the resources. Guess the number before you look.
- Turn on **VPC Flow Logs** to CloudWatch Logs and write a Logs Insights query that finds rejected traffic.

## Up next

**Week 5 — Compute Spectrum: EC2 → ECS Fargate → EKS.** Every workload you run there lands in *this* VPC, in the private or isolated tier, pulling images through the ECR endpoints you build this week. Push the mini-project to GitHub before you start.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
