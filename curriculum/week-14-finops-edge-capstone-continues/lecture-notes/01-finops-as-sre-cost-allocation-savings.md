# Lecture 1 — FinOps Is SRE for the Bill: Allocation, Savings Plans, and Rightsizing

> **Reading time:** ~80 minutes. **Hands-on time:** ~60 minutes (you create a CUR, run your first Cost Explorer and Athena cost queries, and read a Savings Plan recommendation).

This is the lecture that turns "the AWS bill is a mystery that shows up on the 3rd of the month" into "the AWS bill is a metric I instrument, allocate, forecast, and review on a service-level cadence." The difference is not a spreadsheet. The difference is a **practice** — the same Inform → Optimize → Operate loop the FinOps Foundation codified, implemented with AWS-native primitives: Cost Explorer and Budgets to inform, the Cost & Usage Report to allocate, Savings Plans / rightsizing / Spot / Graviton to optimize, and anomaly detection plus a weekly review to operate. By the end you will be able to land a CUR in S3, query per-team spend in Athena, choose between a Savings Plan and a Reserved Instance with a break-even number, read a Compute Optimizer recommendation, and quantify a Graviton migration — and you will understand why **tag hygiene is the precondition for every one of those numbers.**

## 1.1 — The thesis: FinOps is SRE for the bill

A junior engineer treats cost as someone else's job — finance's, the platform team's, "the cloud lead's." A senior engineer treats cost the way they treat availability: as a measurable property of the system that has an owner, a target, an instrument, an alarm, and a review. That is the entire reframe, and it maps one-to-one onto the SRE discipline you built in Week 12:

| SRE concept (Week 12) | FinOps equivalent (this week) |
|---|---|
| SLI — a measured signal (latency, error rate) | Cost per unit (per team, per service, per request, per tenant) |
| SLO — a target on the SLI (99.9% available) | A budget — a target on spend ($X/month for `team=checkout`) |
| Error budget | The room between actual spend and the budget |
| Burn-rate alarm | A Budgets *forecast* alert + Cost Anomaly Detection firing on an unexpected spike |
| Dashboards (Week 12) | The CUR → Athena → QuickSight cost dashboard you build Tuesday |
| Blameless postmortem | The anomaly review: *why* did `team=ml` spend 3× last week, and what do we change? |

The FinOps Foundation calls the loop **Inform, Optimize, Operate**, and it is worth saying out loud because the AWS console scatters the tools and the framework gives them an order:

- **Inform** — make the spend *visible and allocated*. You cannot optimize what you cannot see, and you cannot allocate what you have not tagged. Cost Explorer, Budgets, and the CUR live here. *This is where most teams are weakest, and it is the precondition for everything else.*
- **Optimize** — reduce the spend without reducing the value. Savings Plans/RIs (commit for a discount), Spot (use spare capacity), rightsizing (stop over-provisioning), Graviton (cheaper silicon). These are the levers, and they only pay off if Inform told you where to pull them.
- **Operate** — make it a habit. Anomaly detection, a weekly cost review, budget *actions* that take automated steps on breach. This is the "run it like a service" part — the practice, not the one-time cleanup.

The single most common FinOps failure is doing Optimize before Inform — buying Savings Plans on a hunch, or "turning off dev at night" without knowing dev is 4% of the bill while an untagged data-transfer line is 30%. **Allocate first. Optimize the big numbers. Operate forever.**

## 1.2 — Inform, tier one: Cost Explorer and Budgets as daily instruments

Cost Explorer is the interactive cost graph. You configured Budgets in Week 1 to *alert*; now you use Cost Explorer to *investigate*. The three views that matter:

1. **Trend by service, monthly.** The "what is the bill, and what's growing" view. Group by *Service*. The line that's climbing is your next investigation.
2. **Group by tag, daily.** The allocation view in miniature — group by your `team` (or `service`) cost allocation tag at daily granularity to see *who* is spending and *when* a spike started.
3. **Forecast.** Cost Explorer projects month-end spend from the trend. This is your "burn-rate" signal: if the forecast crosses the budget mid-month, you are burning too fast.

Cost Explorer is also an API, which matters because a senior FinOps practice is *automated*, not a human clicking the console. Here is the daily per-service spend for the current month via `boto3` — the shape Exercise 2 builds on:

```python
import boto3
import datetime as dt

ce = boto3.client("ce", region_name="us-east-1")  # Cost Explorer is a global service, us-east-1 endpoint

today = dt.date.today()
start = today.replace(day=1).isoformat()
end = (today + dt.timedelta(days=1)).isoformat()  # End is exclusive in the CE API

resp = ce.get_cost_and_usage(
    TimePeriod={"Start": start, "End": end},
    Granularity="DAILY",
    Metrics=["UnblendedCost"],
    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
)

for day in resp["ResultsByTime"]:
    date = day["TimePeriod"]["Start"]
    for group in day["Groups"]:
        service = group["Keys"][0]
        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
        if amount > 0.01:  # ignore the noise
            print(f"{date}  {service:<40}  ${amount:.2f}")
```

Two vocabulary notes that trip people up. **UnblendedCost** is the rate you actually paid for each line item (use this for most analysis); *BlendedCost* averages rates across a consolidated-billing family and is rarely what you want. And the CE API's `End` is **exclusive** — to get "through today" you pass tomorrow's date.

**Budgets** is the alarm. You set it in Week 1; this week add the two grown-up features:

- **Forecast-based alerts.** Alert when *forecasted* month-end spend exceeds the budget, not only when *actual* does — the burn-rate equivalent. You get the email on the 8th, not the 28th.
- **Budget actions.** A budget can *do* something on breach: attach a restrictive IAM/SCP policy, stop EC2/RDS instances, or target a specific OU. This is the circuit breaker. The stretch goal and the homework both touch it.

Cost Explorer and Budgets are tier-one Inform: fast, visual, good enough for "is the bill OK and who's growing." But they top out at the *service/tag aggregate* level and they have a small per-request charge on the API. For per-*resource*, per-line-item allocation — "exactly which NAT gateway, which Lambda, which S3 bucket cost what, by the hour" — you need the CUR.

## 1.3 — Inform, tier two: the Cost & Usage Report (CUR) is the source of truth

The **Cost & Usage Report** is the most granular billing data AWS produces: every line item, optionally hourly, optionally with the resource ID, delivered as files to an S3 bucket you own. Cost Explorer is a *view*; the CUR is the *ledger*. When finance asks "prove that `team=checkout` spent $4,210.88 last month," you answer from the CUR, not from a Cost Explorer screenshot.

In 2026 you create a CUR through **AWS Data Exports** as **CUR 2.0**, which improves on the legacy CUR in two ways that matter to you:

1. **A stable, documented schema** (you can also request the **FOCUS** columns — the open cross-cloud billing schema — so your queries port to GCP/Azure later).
2. **Parquet delivery and overwrite mode**, so Athena queries are cheap (columnar) and you are not re-scanning duplicate monthly snapshots.

The catch you must plan around: **the first CUR file can take up to 24 hours to appear**, and the report only describes usage *from creation forward*. Create it Monday. Here is the export as CDK (the legacy `CfnReportDefinition`, which is still the simplest L1 and what most codebases use; `aws-bcmdataexports` is the newer CUR-2.0 path):

```typescript
import { Stack, StackProps, RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cur from 'aws-cdk-lib/aws-cur';
import * as iam from 'aws-cdk-lib/aws-iam';

export class CurStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    // NOTE: CUR report definitions are a us-east-1-only API. Deploy this stack there.
    super(scope, id, props);

    const curBucket = new s3.Bucket(this, 'CurBucket', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.RETAIN, // billing history — never auto-delete in prod
    });

    // The billing service principal must be allowed to write the report objects.
    curBucket.addToResourcePolicy(new iam.PolicyStatement({
      principals: [new iam.ServicePrincipal('billingreports.amazonaws.com')],
      actions: ['s3:PutObject', 's3:GetBucketAcl', 's3:GetBucketPolicy'],
      resources: [curBucket.bucketArn, curBucket.arnForObjects('*')],
    }));

    new cur.CfnReportDefinition(this, 'Cur', {
      reportName: 'c19-capstone-cur',
      timeUnit: 'HOURLY',                 // hourly granularity for Spot/right-sizing analysis
      format: 'Parquet',                  // columnar -> cheap Athena scans
      compression: 'Parquet',
      s3Bucket: curBucket.bucketName,
      s3Prefix: 'cur/',
      s3Region: 'us-east-1',
      additionalSchemaElements: ['RESOURCES'], // include the per-resource ID column
      refreshClosedReports: true,
      reportVersioning: 'OVERWRITE_REPORT', // overwrite the month-to-date snapshot, don't pile up copies
    });
  }
}
```

`additionalSchemaElements: ['RESOURCES']` is the line that adds the per-resource-ID column — without it you cannot attribute spend to a *specific* Lambda or bucket. `reportVersioning: 'OVERWRITE_REPORT'` keeps the bucket from accumulating a fresh full-month copy on every refresh, which is the difference between a few cents of S3 and a slow, expensive bloat.

## 1.4 — CUR → Glue → Athena → QuickSight: cost as a queryable table

Once the CUR is in S3 as Parquet, it is just another data lake — and you already know how to query a data lake from Week 11. Glue catalogues it; Athena queries it; QuickSight visualizes it. The CUR is partitioned by **billing period**, so your queries filter `WHERE billing_period = '2026-06'` and scan only the month you care about (bytes scanned is dollars — Week 11's footer applies here too).

The one query that earns the whole exercise — **spend by team** — looks like this against the CUR 2.0 schema (column names vary slightly between legacy CUR and CUR 2.0/FOCUS; confirm yours with `SHOW COLUMNS`):

```sql
SELECT
    resource_tags['user_team']            AS team,           -- your activated 'team' tag, prefixed user_
    product['product_name']               AS service,
    SUM(line_item_unblended_cost)         AS cost_usd
FROM   cur2.c19_capstone_cur
WHERE  billing_period = '2026-06'
  AND  line_item_line_item_type = 'Usage'                    -- exclude tax, credits, refunds for a clean number
GROUP BY 1, 2
ORDER BY cost_usd DESC;
```

Three things to internalize from this query:

- **`resource_tags['user_team']`** — a user-defined tag `team` shows up in the CUR as `user_team` (the `user_` prefix marks it user-defined vs an AWS-generated tag). It is `NULL` for any resource you forgot to tag. The volume of `NULL`-team spend is your **tag-hygiene debt**, and it is usually shockingly large the first time you look. *That untagged number is the single most important output of this exercise* — it tells you how much of your bill you currently cannot allocate.
- **`line_item_line_item_type = 'Usage'`** — the CUR includes tax, credits, RIs/SP fees, and refunds as their own line types. Filter to `Usage` for "what did running things cost," or you get a number that doesn't reconcile with anyone's mental model.
- **`SUM`** — the CUR is line items; you always aggregate. One row per resource-per-hour is a lot of rows.

You then point **QuickSight** at this Athena table (or, better, at a curated view) and build the dashboard: a bar chart of cost by `team`, a stacked area of cost by `service` over time, and a single big number for "untagged spend." That dashboard is the FinOps deliverable for the capstone. AWS even ships a prebuilt QuickSight dashboard for the CUR — the **Cloud Intelligence Dashboards (CID)** — which you can deploy and then customize; the exercise builds a small one by hand first so you understand what's under it.

**Why CUR and not just QuickSight-on-Cost-Explorer?** Because Cost Explorer cannot show you *per-resource* cost, cannot be partitioned and joined arbitrarily, and cannot be version-controlled as SQL. The CUR is the lake; you own the queries. That ownership is the point.

## 1.5 — Optimize, lever one: Savings Plans vs Reserved Instances

Now we move from Inform to Optimize, and the first lever is **commitment discounts**: you promise AWS a baseline of spend or usage for 1 or 3 years, and AWS gives you a discount (up to ~72% vs on-demand) in return. There are two product families and they confuse everyone, so here is the decision cleanly.

### Savings Plans — commit to a dollar-per-hour of compute

A **Savings Plan** commits you to spend `$X/hour` on compute for 1 or 3 years; usage up to that commitment is discounted, usage above it is on-demand. Three flavors, in order of flexibility:

- **Compute Savings Plans** — the most flexible. The discount applies across **EC2, Fargate, and Lambda**, across **any instance family, size, OS, tenancy, and Region**. You can change everything about your fleet and keep the discount, as long as you keep spending the committed dollars/hour. Discount: up to ~66%. **This is the default recommendation for most teams** because it survives architectural change.
- **EC2 Instance Savings Plans** — a **deeper** discount (up to ~72%) in exchange for locking to a specific **instance family in a specific Region** (e.g. "`m7` in `us-east-1`"). You can still change size, OS, and tenancy within that family/Region. Pick this only for a workload you are confident will stay on that family — a steady, well-understood baseline.
- **SageMaker Savings Plans** — the same idea scoped to SageMaker ML instance usage (training jobs, endpoints, notebooks). Relevant to the capstone because of the Week-11 recommendation endpoint.

### Reserved Instances — the older model, still occasionally right

**Reserved Instances (RIs)** predate Savings Plans and commit to specific *instance attributes* rather than a dollar amount:

- **Standard RIs** — the cheapest, but rigid: locked to instance type/Region; you can only modify within limits.
- **Convertible RIs** — more flexible (you can exchange for a different family), at a smaller discount.

In 2026, **Savings Plans are the default and RIs are the exception.** RIs still win in two cases: (1) services that Savings Plans **don't cover** — notably **RDS, ElastiCache, Redshift, and OpenSearch** reserved capacity is still RI-style, not Savings-Plan-style; and (2) when you want a **capacity reservation** guarantee in a specific AZ (a zonal RI reserves capacity; a regional Savings Plan does not). For pure EC2/Fargate/Lambda compute, reach for a Compute Savings Plan first.

### The break-even, made into arithmetic

This is the part you must be able to defend in a design review. A commitment is a bet: you trade flexibility for a discount, and the bet pays off only if you actually use the committed capacity. The two numbers are the **discount** and the **utilization**.

Say your capstone's steady-state compute (EKS nodes, the recommendation endpoint, the Lambda baseline) runs at a floor of **$1.00/hour on-demand, 24/7**. A 1-year, no-upfront Compute Savings Plan offers, say, a **40% discount**, so committing $0.60/hour covers that $1.00/hour of on-demand usage.

```
On-demand cost of the steady-state baseline, 1 year:
    $1.00/hr × 730 hr/mo × 12 mo            = $8,760/year

With a 1-yr Compute SP covering it (40% off the covered usage):
    $0.60/hr × 730 × 12                      = $5,256/year

Annual saving if fully utilized:             $8,760 − $5,256 = $3,504  (40%)
```

The risk is **under-utilization**. A Savings Plan bills you the committed `$0.60/hr` *whether or not you use it*. If your steady-state drops below the commitment — you rearchitect, traffic falls, you migrate to Graviton and shrink the fleet — you pay for capacity you no longer consume. So the rule:

> **Commit only to the part of the workload you are certain is permanent.** Look at the CUR/Cost Explorer "Savings Plans coverage and utilization" report, find the *floor* of your compute usage over the last 30–60 days (the amount that is *always* running), and commit to ~80–90% of that floor — not the average, not the peak. The 10–20% headroom absorbs normal variance so you never pay for idle commitment.

The break-even on *commitment risk* is then: the discount (40%) must more than cover the fraction of committed capacity you might waste. If you are 95% confident the baseline persists, a 40% discount is an easy yes. If the workload is six months from a rewrite, commit nothing, or commit only the 1-year no-upfront (lowest discount, lowest risk) rather than the 3-year all-upfront (highest discount, highest lock-in). **No-upfront / 1-year is the conservative default; 3-year / all-upfront is for the workload you'd bet your job on.**

AWS will *recommend* a Savings Plan for you — Cost Explorer → Savings Plans → Recommendations analyzes your history and proposes a commitment. **Read it, don't obey it.** The recommendation optimizes for the past 7/30/60 days assuming the future looks identical. You know whether it will. Exercise 2 pulls this recommendation via the API and has you sanity-check it against your own knowledge of the roadmap.

## 1.6 — Optimize, lever two: Spot for the stateless floor

**Spot** is spare AWS capacity sold at **60–90% off** on-demand, with one catch: AWS can reclaim it on a **2-minute notice** when it needs the capacity back. That makes Spot perfect for anything **stateless and interruptible** and wrong for anything that must not be killed mid-flight.

The rule you have carried since Week 5 holds: **Spot for stateless, on-demand (or a Savings Plan) for stateful.** Your capstone's Karpenter-managed EKS batch nodes, your CI runners, and your Fargate Spot tasks should ride Spot; your Aurora writer, your stateful sidecar, and your customer-facing recommendation endpoint should not.

The engineering is in handling the interruption gracefully. AWS gives you two warnings:

- The **rebalance recommendation** — an *early* heads-up that this Spot instance is at elevated risk of reclamation. Use it to proactively drain before the hard notice.
- The **2-minute interruption notice** — delivered via instance metadata (and an EventBridge event). When you see it, you have 120 seconds to drain connections, checkpoint work, and let the scheduler reschedule the pod elsewhere.

On EKS, **Karpenter handles this for you**: it watches the interruption queue, cordons and drains the node on a notice, and provisions replacement capacity (Spot again, or on-demand fallback) before the pod is evicted. The capstone uses exactly this. The thing you must be able to articulate: *Spot is not "cheap EC2"; it is "cheap EC2 that you have architected to survive losing."* If losing an instance would lose data or fail a request, it is not a Spot workload.

## 1.7 — Optimize, lever three: rightsizing and Compute Optimizer

The quietest line on most bills is **over-provisioning** — the `m5.2xlarge` running at 4% CPU because someone guessed big "to be safe." You pay for the whole instance regardless of utilization. Rightsizing is matching the instance to the observed load, and **AWS Compute Optimizer** does the observing for you.

Compute Optimizer ingests CloudWatch metrics (CPU, memory if the agent is installed, network, disk) over a trailing window and emits recommendations for **EC2 instances, Auto Scaling Groups, EBS volumes, Lambda functions, and ECS-on-Fargate**. Each recommendation classifies the resource as *Under-provisioned*, *Over-provisioned*, or *Optimized*, and proposes a target with a projected cost and performance impact. Pulling them via the API:

```python
import boto3

co = boto3.client("compute-optimizer", region_name="us-east-1")

resp = co.get_ec2_instance_recommendations(
    filters=[{"name": "Finding", "values": ["Overprovisioned"]}],
)

for rec in resp.get("instanceRecommendations", []):
    arn = rec["instanceArn"]
    current = rec["currentInstanceType"]
    # Recommendations are ranked; option[0] is the top suggestion.
    options = rec.get("recommendationOptions", [])
    if not options:
        continue
    best = options[0]
    target = best["instanceType"]
    # savingsOpportunity gives the estimated monthly $ and % saved.
    savings = best.get("savingsOpportunity", {}).get("estimatedMonthlySavings", {})
    pct = best.get("savingsOpportunity", {}).get("savingsOpportunityPercentage", 0)
    print(f"{arn}\n  {current} -> {target}  "
          f"(~{pct:.0f}% / ${savings.get('value', 0):.2f}/mo)")
```

Two cautions a senior engineer carries into rightsizing:

1. **Memory is invisible without the agent.** Compute Optimizer sees CPU and network from the hypervisor for free, but it cannot see *memory* utilization unless the CloudWatch agent is reporting it. A recommendation that ignores memory can downsize you into an OOM. Install the agent (or enable Memory in the recommendation preferences) before trusting a memory-sensitive recommendation.
2. **Rightsize before you commit.** If you buy a Savings Plan for your *current* (over-provisioned) fleet and then rightsize, you've committed to capacity you no longer need. **Optimize size first, then commit to the smaller baseline.** Order matters: rightsize, observe the new floor for a few weeks, *then* buy the Savings Plan.

## 1.8 — Optimize, lever four: Graviton (arm64)

AWS's **Graviton** processors are arm64 chips AWS designed in-house, and for most general-purpose and many compute/memory workloads they deliver **better price/performance than the equivalent x86 instance** — often ~20% cheaper for comparable or better throughput (e.g. an `m7g` vs an `m7i`). For a steady-state fleet, moving to Graviton is one of the largest single cost wins available, and it stacks with Savings Plans (a Compute Savings Plan covers Graviton instances too).

The catch is the **build**. Your containers and binaries must be `linux/arm64`. You already learned the multi-arch build path in Week 7 (`docker buildx`, CodeBuild's arm64 fleets). The migration checklist:

1. **Build multi-arch images** (`linux/amd64,linux/arm64`) and push both to ECR — your Week-7 pipeline already can.
2. **Check your dependencies.** Most managed runtimes (Python, Node, Java, Go) are arm64-native. The risk is a native extension or a vendored binary with no arm64 build. Test, don't assume.
3. **Move the stateless, easy-to-test workloads first** — the recommendation Lambda, the API handlers — then the EKS node pools (Karpenter can run arm64 node pools), then the harder stateful pieces.
4. **Measure.** Deploy the arm64 variant alongside the x86 one, send it real traffic, and compare *price-per-request* — not just instance price, because performance differs. The win is real but you prove it with a number.

For the capstone, the homework asks you to migrate one service to Graviton and report the measured delta. That number — "we cut the API tier's compute cost 22% with a multi-arch rebuild and a node-pool change" — is exactly the kind of line a capstone reviewer wants to see.

## 1.9 — The precondition under everything: tag hygiene and cost categories

Notice that every Optimize lever depends on Inform, and Inform depends on **allocation**, and allocation depends on **tags**. You cannot tell `team=checkout` to rightsize if you cannot tell which resources are `team=checkout`. This is why "tag every resource `team`, `service`, `environment`" appears in the capstone spec as a hard requirement and why it is the first thing you should fix.

Two mechanisms do the allocation:

**Cost allocation tags.** A resource tag becomes a *cost dimension* only after you **activate** it in the Billing console (Cost allocation tags → activate `team`, `service`, `environment`). Activation is **not retroactive** — it allocates from activation forward — so do it early (Week 1, ideally; this Monday at the latest). Enforce the tags at *creation* time, not as cleanup: CDK `Tags.of(scope).add('team', 'checkout')` applied at the app or stack level tags every taggable resource, and an **SCP or an AWS Config rule** can *deny* creation of untagged resources or flag them. The goal is **zero untagged spend** — every line in the CUR attributable to a team.

**Cost categories.** Tags allocate by what's *on* the resource; **cost categories** allocate by *rules*. A cost category is a named bucket defined by rules over accounts/tags/services — e.g. "any spend in the `prod-*` accounts → `Production`," "any `service=ml` or SageMaker usage → `ML Platform`," "everything else → `Shared`." Cost categories are how you roll messy reality up into the handful of buckets finance actually reports on, and how you **split shared cost** (the NAT gateway, the data-lake bucket) across teams by a rule rather than a tag. They show up as a grouping dimension in Cost Explorer, Budgets, and the CUR.

The honest first-look number — *what percent of your bill is untagged?* — is the single best measure of your FinOps maturity. A team at 30% untagged cannot do FinOps; a team at <5% can allocate, chargeback, and optimize per-team. Driving that number down is the unglamorous, load-bearing work, and it is why Tuesday's exercise makes you stare at the untagged figure on your own account.

## 1.10 — Operate: anomaly detection and the weekly review

The last loop is **Operate** — making cost a habit, not a quarterly fire drill. Two pieces:

**Cost Anomaly Detection** is the ML burn-rate alarm for the bill. You define *monitors* (by service, by account, by cost category, or by tag), AWS learns the normal spend pattern, and it alerts when actual spend deviates beyond a threshold you set. Unlike a static budget, it adapts to your baseline — it knows your bill is higher on weekdays, spikes at month-end batch, etc. — so it catches the *unexpected* $400 spike (a forgotten GPU instance, a runaway recursive Lambda, a misconfigured CloudFront cache scanning the origin) without false-alarming on normal variation. Route anomalies to the team that owns the spiking service (the tag tells you who) — that's the "blameless postmortem, with an owner" of FinOps.

**The weekly cost review** is the human part. Fifteen minutes, every week: open the dashboard, read the trend, look at any anomalies, check Savings Plan utilization (are we wasting committed capacity?), and assign one follow-up. This is the "run it like a service level" discipline made concrete. The bill is not a number that happens to you; it is a metric you steer.

## 1.11 — Open-source and multi-cloud comparators (what you traded away)

- **FOCUS** — the open billing schema. By exporting your CUR with FOCUS columns, the Athena queries you wrote this week run *unchanged* against a GCP or Azure FOCUS export. You traded AWS-specific column names for portability; take the trade if you're multi-cloud.
- **OpenCost / Kubecost** — Kubernetes-native cost allocation. The CUR tells you what the *EKS nodes* cost; OpenCost tells you what each *namespace and pod* cost by dividing node cost across requests/usage. For a multi-tenant EKS capstone, OpenCost answers "what does each tenant cost on the cluster" in a way the CUR alone cannot. The stretch goal reconciles the two.
- **Infracost** — cost estimation *in the pull request*. Instead of discovering a cost regression in next month's CUR, Infracost comments the estimated monthly delta of an infrastructure PR before merge. FinOps shifted all the way left into code review. The capstone CI is the natural place to add it.

The pattern, as always this course: AWS-native gives you depth and integration; the open tools give you portability and shift-left. Know both, and reach for the managed thing knowing exactly what the open alternative would have bought you.

## 1.12 — What you should be able to do now

After this lecture and the Monday/Tuesday/Wednesday exercises you should be able to:

- State the FinOps Inform → Optimize → Operate loop and map it onto SRE's SLI/SLO/burn-rate/postmortem.
- Pull per-service and per-tag spend from Cost Explorer and from a CUR Athena query.
- Read the **untagged-spend** number off your own account and explain why it caps your FinOps maturity.
- Choose Compute vs EC2-Instance vs SageMaker Savings Plan vs Standard/Convertible RI for a given workload, and compute the break-even and the commitment risk.
- Apply the Spot-for-stateless rule and describe graceful interruption handling on EKS via Karpenter.
- Read a Compute Optimizer recommendation, name the memory-blindness and rightsize-before-commit caveats, and act on one.
- Quantify a Graviton migration with a measured price-per-request delta.
- Set up cost allocation tags and a cost category, and route a Cost Anomaly Detection finding to the owning team.

## 1.13 — Exercises that go with this lecture

- **Exercise 1 — CUR → Athena → QuickSight by tag.** Land the CUR, catalogue it, query per-team spend, find your untagged number, build the dashboard.
- **Exercise 2 — Savings Plan, rightsizing, Graviton.** Pull the Savings Plan recommendation and Compute Optimizer findings via the API, compute the break-even, and quantify a Graviton move.

Bring your **untagged-spend percentage** and your **Savings Plan break-even number** to Friday. The challenge's cost-as-a-feature decision assumes you have produced both on your own account, not just read about them.
