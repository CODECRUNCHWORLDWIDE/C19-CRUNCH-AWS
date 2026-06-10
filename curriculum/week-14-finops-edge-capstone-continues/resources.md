# Week 14 — Resources

Everything here is free to read. AWS documentation is open. The re:Invent talks are on YouTube. The open-source projects are public on GitHub. The FinOps Foundation's framework and the FOCUS billing spec are open standards. We link a few paid books at the chapter level only where the free docs genuinely fall short.

Two scheduling notes that will save you a day:

1. **Enable the Cost & Usage Report on Monday.** A CUR (CUR 2.0 / Data Exports) takes **up to 24 hours** to deliver its first file to S3 after you create the export. If you create it Thursday afternoon, you have no data to query for Exercise 1. Create it Monday so the bucket is populated by Tuesday.
2. **Activate your cost allocation tags on Monday, too.** A user-defined tag only becomes a *cost allocation* dimension after you activate it in the Billing console, and activation is **not retroactive** — it begins allocating from activation forward. If `team`/`service`/`environment` are not already activated from earlier weeks, activate them now and accept that older line items will show as untagged.

## Required reading (work it into your week)

- **AWS Well-Architected — Cost Optimization Pillar** — the canonical framing for everything FinOps this week:
  <https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html>
- **FinOps Foundation — the FinOps Framework** — the vendor-neutral discipline AWS's tools implement (Inform → Optimize → Operate):
  <https://www.finops.org/framework/>
- **AWS Cost & Usage Report (CUR 2.0 via Data Exports)** — the line-item source of truth:
  <https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html>
  <https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create-standard.html>
- **Querying the CUR with Athena** — the Glue/Athena path you build in Exercise 1:
  <https://docs.aws.amazon.com/cur/latest/userguide/cur-query-athena.html>
- **Savings Plans — what they are and the three types** — Compute vs EC2 Instance vs SageMaker:
  <https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html>
- **Reserved Instances vs Savings Plans** — the decision the lecture turns into arithmetic:
  <https://docs.aws.amazon.com/cost-management/latest/userguide/ce-purchase-recommendations.html>
- **Compute Optimizer — rightsizing recommendations** for EC2, ASG, EBS, and Lambda:
  <https://docs.aws.amazon.com/compute-optimizer/latest/ug/what-is-compute-optimizer.html>
- **CloudFront Functions vs Lambda@Edge — choosing** (the single most important edge decision):
  <https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/edge-functions-choosing.html>
- **Lambda@Edge — restrictions and the four trigger points** (viewer/origin × request/response):
  <https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/lambda-at-the-edge.html>
- **CloudFront origin failover (origin groups)**:
  <https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/high_availability_origin_failover.html>

## Pricing pages (read these as dollars, not docs)

You cannot do this week's break-even and cost-as-a-feature work without the numbers. Open these and write the figures into your cost report — **with the date you pulled them**, because rates change:

- **Savings Plans pricing** — the per-type discount rates and the commitment matrix:
  <https://aws.amazon.com/savingsplans/pricing/>
- **EC2 On-Demand & Spot pricing** — the baseline you discount against; Spot's 60–90% off:
  <https://aws.amazon.com/ec2/pricing/on-demand/>
  <https://aws.amazon.com/ec2/spot/pricing/>
- **EC2 Graviton (arm64) instances** — the price/performance comparator (e.g. `m7g` vs `m7i`):
  <https://aws.amazon.com/ec2/graviton/>
- **CloudFront pricing** — data-transfer-out tiers, requests, **CloudFront Functions** (per 1M invocations) and **Lambda@Edge** (per 1M requests + GB-seconds):
  <https://aws.amazon.com/cloudfront/pricing/>
- **AWS WAF pricing** — per web ACL, per rule, per 1M requests inspected:
  <https://aws.amazon.com/waf/pricing/>
- **Global Accelerator pricing** — the fixed hourly accelerator charge plus data transfer premium:
  <https://aws.amazon.com/global-accelerator/pricing/>
- **Athena & QuickSight pricing** — per-TB-scanned (the CUR query cost) and per-user/per-session QuickSight:
  <https://aws.amazon.com/athena/pricing/>
  <https://aws.amazon.com/quicksight/pricing/>

## AWS docs you will reach for during the build

- **Cost Explorer — the console and the `ce` API**: <https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html>
- **AWS Budgets — budgets, actions, and forecast alerts**: <https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html>
- **Cost Anomaly Detection — monitors and ML baselines**: <https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html>
- **Cost categories — rule-based rollups of spend**: <https://docs.aws.amazon.com/cost-management/latest/userguide/manage-cost-categories.html>
- **Activating cost allocation tags** (the precondition for per-team allocation):
  <https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/activating-tags.html>
- **EC2 Spot — interruption notices & rebalance recommendations** (the 2-minute warning you handle gracefully):
  <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html>
- **Karpenter — consolidation & Spot interruption handling on EKS** (your capstone's node story):
  <https://karpenter.sh/docs/concepts/disruption/>
- **CloudFront Functions — the JavaScript runtime, KeyValueStore, and limits**:
  <https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cloudfront-functions.html>
  <https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/kvs-with-functions.html>
- **CloudFront signed cookies** (the tenant-cookie mechanism Exercise 3 and the capstone use):
  <https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-signed-cookies.html>
- **AWS WAF — rate-based rules & managed rule groups**:
  <https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html>

## CDK / IaC reference

- **AWS CDK — `aws-cloudfront`** (Distribution, behaviors, origin groups, function associations):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudfront-readme.html>
- **AWS CDK — `experimental.EdgeFunction`** (the construct that handles the `us-east-1`-only Lambda@Edge deploy):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudfront.experimental.EdgeFunction.html>
- **AWS CDK — `aws-wafv2`** (web ACLs, rate-based rules — L1 `CfnWebACL`, still no stable L2 in 2026):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_wafv2-readme.html>
- **AWS CDK — `aws-cur`** (`CfnReportDefinition`) and **Data Exports** (`aws-bcmdataexports`):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cur-readme.html>
- **OpenTofu / Terraform AWS provider** — `aws_cur_report_definition`, `aws_cloudfront_distribution`, `aws_wafv2_web_acl`, `aws_ce_anomaly_monitor`:
  <https://search.opentofu.org/provider/hashicorp/aws/latest>

## re:Invent and AWS talks (free, on YouTube)

- **"FinOps on AWS: optimize cost and improve efficiency"** — the annual COP-track FinOps session (Inform/Optimize/Operate). Search the AWS Events channel for the latest year's COP3xx FinOps talk:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Reduce costs with Savings Plans and Reserved Instances"** — the commitment-discount deep dive:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Optimizing performance and cost at the edge with CloudFront"** — CF Functions vs Lambda@Edge, drawn out:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Building serverless applications at the edge"** — the edge-functions architecture patterns:
  <https://www.youtube.com/@AWSEventsChannel>

*(re:Invent session IDs change yearly; the channel is stable. Filter by the most recent year and the COP / NET / SVS tracks.)*

## Open-source & multi-cloud comparators (know what you traded away)

- **FOCUS (FinOps Open Cost & Usage Specification)** — the open, vendor-neutral billing schema. AWS's CUR 2.0 can export FOCUS columns; learn it and your FinOps queries port to GCP/Azure unchanged:
  <https://focus.finops.org/>
- **OpenCost** — the CNCF spec and reference implementation for Kubernetes cost allocation; the open answer to "what does each namespace/team cost on EKS":
  <https://www.opencost.io/docs/>
- **Kubecost** — the productized OpenCost; per-namespace, per-workload cost on your cluster:
  <https://docs.kubecost.com/>
- **Infracost** — estimates the monthly cost of a Terraform/CDK change *in the pull request*; FinOps shifted left into CI:
  <https://www.infracost.io/docs/>
- **Cloudflare Workers** — the edge-compute comparator to CloudFront Functions/Lambda@Edge; V8 isolates at the edge, a different cold-start and pricing story:
  <https://developers.cloudflare.com/workers/>
- **Fastly Compute** — WebAssembly at the edge; the other serious edge-compute platform, with a compile-to-Wasm model:
  <https://www.fastly.com/documentation/guides/compute/>

## Books (chapter-level)

- **"Cloud FinOps" (Storment & Fuller, O'Reilly)** — the canonical FinOps book; the chapters on the FinOps lifecycle and on showback/chargeback are the best plain-English explanation of *why* tag hygiene is the whole game. Borrow it; read two chapters.
- **AWS Prescriptive Guidance — Cost optimization patterns** — free, fast, and concrete:
  <https://docs.aws.amazon.com/prescriptive-guidance/latest/cost-optimization-automating-instance-scheduling/welcome.html>

## A note on the capstone

This week's artifacts plug directly into the capstone spec (see `SYLLABUS.md` → *Capstone specification*). The spec mandates, verbatim: a **Frontend/Edge** layer of "CloudFront + WAF + ACM TLS, CloudFront Functions for header rewrites, Lambda@Edge for tenant routing"; and a **FinOps** requirement of "tag every resource with `team`, `service`, `environment`; Cost & Usage Report → Athena → QuickSight dashboard; one Savings Plan committed for steady-state." Everything you build this week is that, in miniature, built to be imported into the capstone monorepo. Keep the repo.

## Tools you'll use this week

- **AWS CLI v2** — `aws ce get-cost-and-usage`, `aws savingsplans describe-...`, `aws compute-optimizer get-recommendation-...`, `aws cloudfront create-distribution`, `aws wafv2 ...`. Verify with `aws --version` (want `aws-cli/2.x`).
- **Python 3.12+** with `boto3`. A `requirements.txt` ships with each exercise.
- **AWS CDK v2** (TypeScript) — `npx cdk deploy`. The mini-project's infra is CDK; note the `us-east-1`-only constraint for Lambda@Edge.
- **`jq`** — for slicing the JSON the Cost Explorer and Savings Plans CLIs return.
- **A QuickSight account** — the standard edition is enough for the dashboard; the first author/admin sign-up has a free trial window. (Optional alternative: Grafana with the Athena data source if you don't want QuickSight.)

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **FinOps** | The discipline of running cloud spend like an engineered service: instrument, allocate, optimize, review. SRE for the bill. |
| **CUR** | Cost & Usage Report — the most granular billing export (line-item, hourly, per-resource) delivered to S3. The source of truth. |
| **FOCUS** | An open, cross-cloud billing schema. CUR 2.0 can emit it; your queries then port to other clouds. |
| **Cost allocation tag** | A resource tag *activated* in Billing so spend can be grouped by it. Activation is not retroactive. |
| **Cost category** | A rule-based rollup that buckets spend (e.g. "all `prod` accounts" → "Production") independent of tags. |
| **Savings Plan** | A commitment to spend `$X/hr` for 1 or 3 years in exchange for a discount. Compute (flexible) / EC2-Instance (deeper) / SageMaker. |
| **Reserved Instance** | An older commitment model tied to instance attributes; Standard (cheapest, rigid) vs Convertible (flexible, less off). |
| **Break-even (commitment)** | The utilization at which a commitment's discount has paid back its risk vs paying on-demand. |
| **Spot** | Spare capacity at 60–90% off, reclaimable on a 2-minute notice. For stateless, interruptible work only. |
| **Rightsizing** | Matching instance size to actual utilization; Compute Optimizer recommends it from observed metrics. |
| **Graviton** | AWS's arm64 CPUs; better price/performance than x86 for most workloads, needs a multi-arch build. |
| **CloudFront Function** | Tiny JS that runs at the viewer tier, sub-ms, no network, cheap (~$0.10/1M). Header & cache-key rewrites. |
| **Lambda@Edge** | A full Lambda (Node/Python) at the origin tier; can call the network, larger code, costlier (~$0.60/1M + duration). Tenant routing. |
| **Global Accelerator** | Anycast static IPs at the AWS edge for TCP/UDP; fixed hourly + premium transfer. For non-HTTP or static-IP needs. |
| **Origin group** | A primary + failover origin pair; CloudFront fails over on configured status codes. The edge's HA. |
| **WAF rate-based rule** | A rule that counts requests per source over a window and blocks above a threshold. The edge's rate limit. |

---

*If a link 404s, please open an issue so we can replace it.*
