# Week 14 — FinOps & Edge: Capstone Continues

Welcome to the week where the bill becomes a feature and the edge becomes part of the architecture. By Friday you will have two things the capstone could not ship without: a **FinOps practice** — a Cost & Usage Report landing in S3, queried in Athena, surfaced in a QuickSight dashboard partitioned by your `team`/`service`/`environment` tags, with a committed Savings Plan recommendation and a documented break-even — and an **edge layer** — CloudFront in front of the capstone API, a CloudFront Function rewriting headers at the millisecond tier, a Lambda@Edge function injecting a tenant header from a signed cookie, WAF rate-limiting, and origin failover proven by killing the primary origin.

This is the second of the three capstone-build weeks (13 began it, 15 defends it). It is two disciplines in a trench coat, and they share one spine: **cost.** FinOps is the explicit study of the bill — Savings Plans vs Reserved Instances, Spot, rightsizing, Compute Optimizer, Graviton, tag-based allocation, anomaly detection. Edge is, among other things, a *cost* decision dressed as a latency decision — a CloudFront Function costs a fraction of a Lambda@Edge invocation, and knowing which logic runs where is the difference between a $3/month edge layer and a $300 one. We teach them together because a senior engineer reads both through the same lens: every architectural choice has a dollar attached, and the job is to know the number before the design review, not after the invoice.

The lecture's thesis is the one to carry all week: **FinOps is just SRE for the bill. Run it like a service level.** You do not "save money" as a one-time heroic act; you set a target, instrument against it, alarm on the burn rate, and review it weekly — exactly the SLO discipline you built in Week 12, pointed at dollars instead of availability.

We are vendor-aware, not vendor-loyal. The FinOps muscle transfers to any cloud — GCP's committed-use discounts, Azure's reservations, and the open **FOCUS** billing schema all rhyme with what you learn here. The edge muscle transfers too: CloudFront/Lambda@Edge map onto Fastly Compute, Cloudflare Workers, and the open WebAssembly-at-the-edge story. We name the comparators so you know what you traded away when you reached for the AWS-native thing.

The artifacts you build this week are **not throwaway.** The cost dashboard becomes the capstone's FinOps deliverable. The CloudFront + WAF + Lambda@Edge layer becomes the capstone's frontend/edge tier — the exact one the capstone spec mandates. Both sit on top of the capstone API you have been assembling since Week 13. Build them to keep.

## Learning objectives

By the end of this week, you will be able to:

- **Operate** Cost Explorer and AWS Budgets as a daily instrument, not a once-a-quarter panic, and read a cost trend as an SRE reads a latency graph.
- **Land** a Cost & Usage Report (CUR 2.0, in the open FOCUS-aligned schema) into S3, **catalogue** it with Glue, and **query** it in Athena partitioned by your allocation tags.
- **Build** a QuickSight dashboard over the CUR that breaks cost down by `team`, `service`, and `environment`, and explain why tag hygiene is the precondition for every number on it.
- **Choose** correctly between **Savings Plans** (Compute vs EC2 Instance vs SageMaker) and **Reserved Instances**, and compute the **break-even** and the commitment risk for a steady-state workload.
- **Apply** Spot strategies with graceful interruption handling, and explain the Spot-for-stateless / on-demand-for-stateful rule with a real interruption notice.
- **Read** Compute Optimizer and Cost Anomaly Detection findings, act on a rightsizing recommendation, and quantify the **Graviton (arm64)** savings.
- **Design** per-team cost allocation with **cost allocation tags** and **cost categories**, and prove a single team's spend is isolable from the rest.
- **Place** edge logic correctly: decide what runs in a **CloudFront Function** (viewer request/response, sub-millisecond, cache-key and header rewrites) vs **Lambda@Edge** (origin request/response, full runtime, network access) vs **Global Accelerator** (anycast TCP/UDP at the edge), with the cost of each.
- **Inject** a tenant header from a signed cookie at the edge with Lambda@Edge, in front of the capstone API, and **rate-limit** with AWS WAF.
- **Configure** CloudFront **origin failover** (origin groups) and prove it by killing the primary origin while traffic flows.

## Prerequisites

This week assumes you have completed Weeks 1–13 of C19, or have equivalent AWS fluency, and that **the capstone build is underway** (it began in Week 13). Specifically:

- You have a **capstone API behind a CloudFront-able origin** — an API Gateway HTTP API and/or an ALB in front of EKS, from the capstone work in Week 13. This week puts CloudFront, WAF, and edge functions in front of it. If your capstone is behind schedule, the exercises include a minimal origin (an API Gateway returning a JSON echo) so you are not blocked.
- You configured **AWS Budgets and Cost Anomaly Detection in Week 1**, with `$5 / $25 / $80` thresholds. This week you graduate from "alert me before the bill" to "allocate and forecast the bill."
- You **tagged every resource** `team`, `service`, `environment` in the capstone and in the Week 11 mini-project. Those tags are the precondition for this week's allocation work; if they are missing, the dashboard has nothing to group by.
- You can deploy a CDK stack (TypeScript) from zero and read the synthesized CloudFormation. (Week 3.) Lambda@Edge has a CDK wrinkle — it must be deployed in `us-east-1` — that we walk through.
- You can write a Lambda in Python or Node and scope an execution role to least privilege. (Weeks 2, 7.) Lambda@Edge is Node/Python only and has its own size and runtime limits we cover.
- Comfort reading a number off a pricing page and turning it into a per-1M-requests or per-month figure. The whole week is that skill pointed at the bill.

You do **not** need prior FinOps or accounting experience. We build the practice from the AWS primitives up. If you can read a CloudWatch dashboard, you can read a cost dashboard.

## Topics covered

- **Cost Explorer & Budgets as instruments:** the daily/monthly granularity views, grouping by tag/service/account, forecasting, and Budgets with actuals-and-forecast alerts plus budget actions (auto-attach a deny policy on breach).
- **Cost & Usage Report (CUR 2.0):** the line-item-level export to S3, the FOCUS-aligned schema, hourly/daily/resource granularity, Parquet delivery, and why CUR (not Cost Explorer) is the source of truth for per-resource allocation.
- **CUR → Athena → QuickSight:** Glue-catalogued CUR, partition-by-`billing_period`, the queries that compute per-tag spend, and a QuickSight dashboard as the FinOps deliverable.
- **Savings Plans vs Reserved Instances:** Compute Savings Plans (most flexible) vs EC2 Instance Savings Plans (deeper discount, less flexible) vs SageMaker Savings Plans; RIs (Standard vs Convertible) and when they still beat SPs; the 1-yr/3-yr, no-/partial-/all-upfront matrix; break-even and commitment risk.
- **Spot strategies:** capacity-optimized allocation, mixed-instances policies, the 2-minute interruption notice and rebalance recommendation, graceful drain, and the stateless-only rule.
- **Rightsizing & Compute Optimizer:** reading recommendations for EC2/ASG/EBS/Lambda, the over-provisioning tax, and acting on one recommendation with a measured before/after.
- **Graviton (arm64):** the price/performance win, the multi-arch build path (Week 7's `linux/arm64`), and the migration checklist.
- **Cost allocation & cost categories:** activating cost allocation tags, the tag-hygiene problem (untagged spend), cost categories as rule-based rollups, and splitting shared cost.
- **Cost Anomaly Detection:** monitors, the ML baseline, and routing anomalies to the team that owns the spike.
- **The edge tier:** CloudFront caching and behaviors; **CloudFront Functions** (viewer-side, JS, sub-ms, no network) vs **Lambda@Edge** (origin-side, full runtime, network/larger code) — what runs where and what each costs; **Global Accelerator** (anycast at the edge for non-HTTP and static-IP needs).
- **Edge logic in practice:** header/cache-key rewrites in a CloudFront Function; tenant-header injection from a signed cookie in Lambda@Edge; WAF managed rules + a custom rate-limit rule; CloudFront **origin failover** with origin groups.
- **Open-source / multi-cloud comparators:** the FOCUS billing schema, OpenCost/Kubecost for k8s cost, Infracost for IaC cost-in-CI; Cloudflare Workers / Fastly Compute for edge.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target. Capstone-build weeks reshape the cadence around the build, so the mini-project (the capstone-feeder) carries more weight than in a normal week.

| Day       | Focus                                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | FinOps-as-SRE; Cost Explorer/Budgets; SP vs RI math               |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | CUR → S3 → Glue → Athena → QuickSight by tag (Exercise 1)          |    1h    |    2.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Wednesday | Savings Plan break-even; Compute Optimizer; Graviton (Exercise 2) |    1h    |    2.5h   |     1h     |    0.5h   |   0.5h   |     0h       |    0.5h    |     6h      |
| Thursday  | Edge: CloudFront + CF Function + Lambda@Edge tenant header (Ex. 3) |    2h    |    2h     |     0h     |    0.5h   |   0.5h   |     1h       |    0h      |     6h      |
| Friday    | WAF + origin failover; the cost-as-a-feature decision (Challenge 1)|    0h    |    0h     |     2.5h   |    0.5h   |   0.5h   |     2h       |    0h      |     5.5h    |
| Saturday  | Mini-project deep work (capstone edge + FinOps layer)             |    0h    |    0h     |     0h     |    0h     |   0.5h   |     3.5h     |    0h      |     4h      |
| Sunday    | Quiz, cost report, capstone-progress review                       |    0h    |    0h     |     0h     |    1h     |   1h     |     0.5h     |    0h      |     2.5h    |
| **Total** |                                                                   | **6h**   | **8.5h**  | **3.5h**   | **3.5h**  | **5h**   | **7.5h**     | **1.5h**   | **35.5h**   |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated AWS docs, talks, pricing pages, and open-source/multi-cloud comparators, current to 2026 |
| [lecture-notes/01-finops-as-sre-cost-allocation-savings.md](./lecture-notes/01-finops-as-sre-cost-allocation-savings.md) | FinOps as SRE for the bill; CUR→Athena→QuickSight; Savings Plans vs RIs; Spot; rightsizing; Compute Optimizer; Graviton; tags & cost categories |
| [lecture-notes/02-edge-cloudfront-functions-lambda-edge-global-accelerator.md](./lecture-notes/02-edge-cloudfront-functions-lambda-edge-global-accelerator.md) | What runs where at the edge: CloudFront Functions vs Lambda@Edge vs Global Accelerator; tenant routing from a signed cookie; WAF; origin failover; the cost of each |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-cur-athena-quicksight-by-tag.md](./exercises/exercise-01-cur-athena-quicksight-by-tag.md) | Land a CUR into S3, catalogue with Glue, query per-tag spend in Athena, build the QuickSight dashboard |
| [exercises/exercise-02-savings-plan-rightsizing-graviton.py](./exercises/exercise-02-savings-plan-rightsizing-graviton.py) | Pull Savings Plan & Compute Optimizer recommendations via the API, compute break-even, quantify Graviton savings |
| [exercises/exercise-03-cloudfront-edge-tenant-header.py](./exercises/exercise-03-cloudfront-edge-tenant-header.py) | Stand up CloudFront with a CloudFront Function and a Lambda@Edge tenant-header injector in front of an API origin |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-edge-waf-origin-failover-cost.md](./challenges/challenge-01-edge-waf-origin-failover-cost.md) | Add WAF + origin failover to the edge, prove failover by killing the origin, and write the cost-as-a-feature decision doc |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the "Capstone Edge + FinOps Layer" — continues the capstone |
| [quiz.md](./quiz.md) | 14 questions with an answer key |
| [homework.md](./homework.md) | Concrete homework with deliverables and a rubric |

## The "every choice has a dollar" promise

C19's recurring marker this week is the cost annotation. Just as Week 11 demanded you point at the Athena **bytes-scanned** footer after every query, this week demands you point at the dollar behind every architectural choice. When you add a Lambda@Edge function, you should be able to say "that is `$0.60 per 1M requests + duration`, versus a CloudFront Function at `$0.10 per 1M requests` — I put the cache-key rewrite in the CloudFront Function and only the cookie-verify in Lambda@Edge, for that reason." When you commit a Savings Plan, you should be able to say "this commits `$X/hr` for one year, breaks even at `Y%` utilization, and the risk if our steady-state drops is `$Z`." If you cannot attach a number to a design choice, you are not done. Cost is a feature. Internalize it.

## Stretch goals

If you finish the regular work early and want to push further:

- Add **Infracost** to your capstone's GitHub Actions pipeline so every PR comments the *estimated* monthly cost delta of the infrastructure change — FinOps shifted left into code review.
- Stand up **OpenCost** (or Kubecost) on your EKS capstone cluster and reconcile its per-namespace cost against the CUR's per-tag cost — two views of the same dollars.
- Re-do Exercise 2's rightsizing on a **Graviton** target: rebuild one capstone service `linux/arm64` (Week 7's multi-arch path), deploy it, and measure the real price/performance delta against the x86 baseline.
- Switch the edge tenant logic from **Lambda@Edge** to **CloudFront KeyValueStore + a CloudFront Function** where the lookup is simple enough, and document the latency and cost difference (CF Functions can't make network calls, but a KeyValueStore lookup is in-process).
- Add a **Budgets action** that auto-attaches a restrictive SCP/IAM policy when a team's monthly budget is breached — the "circuit breaker" for runaway spend.
- Front a non-HTTP capstone component (say a gRPC or game-style UDP service) with **Global Accelerator** and compare its anycast latency against CloudFront for that workload.

## Up next

Week 15 — Capstone Defense, Chaos Drill & Career Pack. You will run the chaos drill (AZ failover, DynamoDB throttle, Lambda concurrency exhaustion, and a bonus drill — **CloudFront origin failure** is a natural pick, and you will have built exactly the origin-failover machinery to exercise it), write the blameless postmortem, and defend the capstone in a 30-minute oral. Push your edge layer and your FinOps dashboard before you move on; Week 15's cost report and chaos drill both assume they exist.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
