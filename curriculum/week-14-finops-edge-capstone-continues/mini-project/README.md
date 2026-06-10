# Mini-Project — The Capstone Edge + FinOps Layer

> Add the **edge tier** and the **FinOps practice** to the capstone you began in Week 13. In CDK (TypeScript): put CloudFront + WAF + ACM TLS in front of the capstone API, with a CloudFront Function for header/cache-key rewrites and a Lambda@Edge function that injects a tenant header from a signed cookie, and configure origin failover. In parallel: land the Cost & Usage Report into S3, query it in Athena partitioned by your `team`/`service`/`environment` tags, build a QuickSight dashboard, and **commit to one Savings Plan recommendation for the capstone steady-state with a documented break-even.** This is the capstone's frontend/edge tier and its FinOps deliverable, both mandated verbatim by the capstone spec.

This is a **capstone-build week**, not a standalone lab. Week 13 began the capstone (the security stack and multi-region DR foundation); this week adds two of the capstone spec's required layers on top of it. When you reach Week 15 (defense + chaos drill), you will run against *this* edge layer and report against *this* cost dashboard. Build it into the capstone monorepo directly — there is nothing to "import later" because this *is* the capstone.

**Estimated time:** ~7.5 hours (Thursday spill-over, Friday, Saturday in the suggested schedule).

---

## How this compounds

The syllabus is explicit that Week 14's output feeds the capstone, and it sits on top of everything before it:

- It **fronts the capstone API** that Week 13 stood up (API Gateway HTTP API for CRUD + ALB-in-front-of-EKS for long-lived workloads, both from the capstone spec's API layer). This week's CloudFront + WAF + edge functions go *in front of those origins*. If your Week-13 capstone API isn't ready, the mini-project includes a minimal origin so you're not blocked — but wire it to the real capstone API the moment it exists.
- It **reuses the Week-11 lake-and-Athena machinery.** Week 11 taught you Firehose → S3 → Glue → Athena → QuickSight. The CUR is just another Parquet dataset in S3; you catalogue and query it with the exact same pattern. The QuickSight skills are the same. You are not learning a new tool — you are pointing a tool you already own at the bill.
- It **tags everything**, which the capstone spec requires and which the Week-11 mini-project already started (`team`, `service`, `environment` on every resource). Those tags are the precondition for this week's per-team cost dashboard. If you tagged diligently in Weeks 11 and 13, the dashboard lights up; if you didn't, your untagged-spend number tells you exactly what you skipped.
- It **commits a Savings Plan for the capstone steady-state.** Week 13 established the steady-state shape (multi-AZ EKS nodes, the recommendation endpoint from Week 11, the Lambda baseline). This week you measure that floor and (in writing — you don't have to actually purchase in a lab account) commit to ~80–90% of it, with the break-even documented.

So the acceptance bar is the capstone's bar: the IaC must deploy cleanly into the capstone monorepo, and the edge + FinOps layers must be production-shaped, not lab-shaped.

---

## What you will build

A CDK (TypeScript) addition to the capstone monorepo with two stacks:

```
                         Users (global)
                              │
                              ▼
   ┌───────────────── EdgeStack (us-east-1 for L@E/WAF) ─────────────────┐
   │  CloudFront distribution  ── ACM TLS, HTTP/3                          │
   │    ├─ WAF web ACL: managed rules + rate-based rule                    │
   │    ├─ Viewer request:                                                 │
   │    │     ├─ CloudFront Function: cache-key/header normalization       │
   │    │     └─ Lambda@Edge: verify signed cookie -> inject x-tenant-id   │
   │    └─ Origin group:                                                   │
   │          primary  → capstone API (Week 13)                           │
   │          fallback → secondary-Region failover origin (Week 13 DR)    │
   └──────────────────────────────────────────────────────────────────────┘
                              │  (the same API the rest of the capstone serves)
                              ▼
                    Capstone API origins (Week 13)

   ┌───────────────── FinOpsStack ──────────────────┐
   │  CUR (CfnReportDefinition) → S3 (Parquet)       │
   │  Glue DB + table over the CUR                   │
   │  Athena workgroup (scan cutoff) + named queries │
   │  Cost Anomaly Detection monitor                 │
   │  Budgets w/ forecast alert (+ optional action)  │
   │  (QuickSight dashboard built on top, manually)  │
   └──────────────────────────────────────────────────┘
```

The CloudFront Function and Lambda@Edge come straight from Exercise 3; the WAF + origin failover from Challenge 1; the CUR/Athena/QuickSight from Exercise 1; the Savings Plan break-even from Exercise 2. The mini-project is where you assemble all four into the capstone, as IaC.

---

## Required architecture

### Edge half (the capstone's Frontend/Edge tier)

- **CloudFront distribution** over the capstone API origins, with **ACM-managed TLS** on the capstone's domain (or the CloudFront default domain if you don't have one) and HTTP/2+3 enabled.
- **WAF web ACL** (scope `CLOUDFRONT`, `us-east-1`) with at least one AWS managed rule group **and** a custom rate-based rule. Attached to the distribution.
- **CloudFront Function** at viewer-request for cache-key/header normalization — the cheap tier, doing the high-volume transform.
- **Lambda@Edge** (deployed via `cloudfront.experimental.EdgeFunction` so the `us-east-1` placement is handled) at viewer-request, verifying a **signed tenant cookie** and injecting a trusted `x-tenant-id`, stripping any client-supplied copy on the untrusted path.
- **Origin group** with the Week-13 primary API origin and a secondary failover origin, failing over on `5xx`. This is the edge layer of the capstone's DR.
- **Cost discipline:** the cache-key logic is a CloudFront Function and only the cookie verify is Lambda@Edge — and your README states the per-1M cost of each and why you split them that way.

### FinOps half (the capstone's FinOps deliverable)

- **CUR** (`CfnReportDefinition`, `us-east-1`, Parquet, hourly, with `RESOURCES`) delivering to an S3 bucket whose policy allows `billingreports.amazonaws.com`.
- **Glue + Athena** over the CUR: a database, a table (crawler-discovered then pinned in IaC, or pinned directly), and an **Athena workgroup with a `bytesScannedCutoffPerQuery`** so a careless CUR query can't run up the bill (the same guardrail you built in Week 11).
- **A per-team spend query** committed as a CDK Athena named query (or a saved `.sql`), and a **QuickSight dashboard** (built manually on top — QuickSight assets are exported per the capstone spec's "dashboards as code") showing cost by `team`, cost by `service` over time, and the **untagged-spend** number.
- **Cost Anomaly Detection** monitor + **Budgets** with a forecast-based alert (and, as a stretch, a budget action). The capstone's "cost-as-a-service-level" operate loop.
- **A Savings Plan break-even** for the capstone steady-state, documented in `COSTREPORT.md` (you commit *on paper* in a lab account; in a real account you'd purchase the recommended commitment for ~80–90% of the observed floor).

### Cross-cutting

- **Tags.** Every resource tagged `team`, `service`, `environment` — applied at the app/stack level with `Tags.of(app).add(...)`, so the FinOps dashboard can actually group by them. Drive untagged spend toward zero.
- **One-command deploy/destroy.** The edge and FinOps stacks deploy with the rest of the capstone via `cdk deploy --all`; `cdk destroy --all` leaves nothing billing (mind the multi-step edge-function teardown).

---

## Rules

- **CDK (TypeScript) is the source of truth.** You may use the CLI/console to inspect, but every persistent resource — distribution, WAF ACL, edge functions, CUR, Glue table, workgroup, anomaly monitor — is in CDK so it's part of the capstone.
- **Lambda@Edge goes through `EdgeFunction` (or a us-east-1 stack).** A Lambda@Edge function created in the wrong Region simply won't attach; use the construct that handles placement.
- **Split the edge logic by cost.** Doing everything in Lambda@Edge when a CloudFront Function would do is a finding against you in review. The cheap, every-request transform must be a CloudFront Function.
- **The origin group must actually fail over.** A single-origin distribution does not satisfy the DR requirement; prove failover as in Challenge 1.
- **Tag hygiene is graded.** Your untagged-spend percentage is a number in the cost report; a high number is a finding.
- **Cost report required.** Real dollar figures with the date you pulled the pricing pages, not estimates from memory.
- **No edge resources left running unattended where it costs.** The WAF web ACL bills monthly; document and run the deploy-test-destroy loop (or keep it and acknowledge the cost in the report).

---

## Acceptance criteria

- [ ] A capstone-monorepo branch/PR named `capstone-edge-finops-<yourhandle>` (or committed directly to the capstone repo's edge/finops modules).
- [ ] `npx cdk deploy --all` stands up the `EdgeStack` and `FinOpsStack` alongside the existing capstone, with no manual console steps other than the QuickSight dashboard build, the one-time CUR creation, and Bedrock/ACM/tag-activation opt-ins (all documented).
- [ ] CloudFront fronts the capstone API with ACM TLS; a request flows through the CloudFront Function and Lambda@Edge.
- [ ] A request **without** a valid tenant cookie is rejected at the edge (401); a request **with** a valid signed cookie reaches the origin carrying a trusted `x-tenant-id`. Demonstrate both.
- [ ] WAF is attached with a managed rule group and a rate-based rule; show the rate limit tripping.
- [ ] Origin failover is configured and **proven** by killing the primary origin while traffic flows (capture the evidence).
- [ ] A CUR delivers Parquet to S3; an Athena query against it returns spend grouped by `team`, including the **untagged** total.
- [ ] An Athena workgroup enforces a per-query scan cutoff on the CUR queries.
- [ ] A QuickSight dashboard shows cost by `team`, cost by `service` over time, and untagged spend.
- [ ] A Cost Anomaly Detection monitor and a forecast-based Budget exist.
- [ ] Every resource is tagged `team`, `service`, `environment`; the untagged-spend percentage is reported.
- [ ] `npx cdk destroy --all` removes the edge and FinOps stacks (CUR/history may be intentionally retained — say so); no orphaned WAF ACL or enabled distribution remains.
- [ ] A `COSTREPORT.md` with the figures below.
- [ ] A `README.md` with: one-paragraph description, from-clone setup commands, the failover proof, the two edge-tier cost numbers and the split justification, and the deploy-test-destroy loop.

---

## The cost report

`COSTREPORT.md` must contain, with real numbers pulled from the pricing pages (cite the date you pulled them):

1. **Untagged spend.** The `(untagged)` total and its percentage of the bill from your CUR query — your tag-hygiene debt.
2. **Per-team breakdown.** The spend-by-`team` table for the current billing period.
3. **Edge tier cost.** Per-1M-requests cost of the CloudFront Function and the Lambda@Edge function, the WAF per-rule + per-1M-inspected cost, and the **estimated monthly edge cost** at a stated traffic profile (e.g. 5M req/mo, 60% cache-hit). Include the *split justification* — what it would have cost to put the cache-key logic in Lambda@Edge too.
4. **Savings Plan break-even.** The capstone steady-state floor (from Exercise 2 / Cost Explorer), the recommended commitment, the discount, the break-even utilization, and the commitment risk if the steady-state drops. State which Savings Plan type (Compute / EC2-Instance / SageMaker) you'd commit and why.
5. **Rightsizing & Graviton.** The largest Compute Optimizer rightsizing win you found, and the Graviton monthly delta for one migrated service.
6. **Idle bill.** What the edge + FinOps layer costs per day if *nobody calls the API* — the WAF ACL, the distribution baseline, the CUR storage — the number that justifies any nightly teardown.

---

## Suggested build order

1. **Thursday spill-over (1 h).** In the capstone monorepo, scaffold `EdgeStack`. Bring in the Exercise 3 CloudFront Function and the `EdgeFunction`-wrapped Lambda@Edge tenant injector. Point the distribution at the capstone API origin (or the minimal echo origin). Deploy; confirm a request flows through both tiers.
2. **Friday morning (2 h).** Add WAF (managed rules + rate-based) and the origin group (primary + secondary) from Challenge 1. Prove the rate limit and the failover. Capture the evidence.
3. **Friday afternoon (1 h).** Stand up `FinOpsStack`: the CUR `CfnReportDefinition`, the Glue table over it, the Athena workgroup with a scan cutoff, and the anomaly monitor + Budget. (The CUR you ideally created Monday already has data.)
4. **Saturday morning (2.5 h).** Run the spend-by-`team` query; record untagged spend. Build the QuickSight dashboard. Pull the Savings Plan recommendation and Compute Optimizer findings (Exercise 2) for the capstone fleet; compute the break-even.
5. **Saturday afternoon (1 h).** Write `COSTREPORT.md` and `README.md`. Run the full deploy-test-destroy loop once (mind the multi-step edge teardown), and confirm nothing unexpected is left billing.

---

## A worked snippet — the edge distribution in CDK

So you are not staring at a blank file, here is the distribution wiring both edge tiers, WAF, and origin failover — the resource the capstone serves through. (The `EdgeFunction` and `CfnWebACL` are defined as in Lecture 2 / Exercise 3 / Challenge 1.)

```typescript
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import { Duration } from 'aws-cdk-lib';

// Cheap viewer-tier transform.
const cacheKeyFn = new cloudfront.Function(this, 'CacheKeyFn', {
  code: cloudfront.FunctionCode.fromFile({ filePath: 'edge/cachekey.js' }),
  runtime: cloudfront.FunctionRuntime.JS_2_0,
});

// Expensive-but-necessary origin/viewer-tier logic (us-east-1 handled for you).
const tenantFn = new cloudfront.experimental.EdgeFunction(this, 'TenantFn', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'index.handler',
  code: lambda.Code.fromAsset('edge/tenant-injector'),
});

const primary = new origins.HttpOrigin('api.capstone.example.com');     // Week-13 API
const secondary = new origins.HttpOrigin('api-dr.capstone.example.com'); // Week-13 DR origin

new cloudfront.Distribution(this, 'CapstoneEdge', {
  defaultBehavior: {
    origin: new origins.OriginGroup({
      primaryOrigin: primary,
      fallbackOrigin: secondary,
      fallbackStatusCodes: [500, 502, 503, 504],   // edge-layer DR
    }),
    viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
    // API traffic is mostly uncacheable; use the managed CachingDisabled policy.
    cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
    functionAssociations: [{
      function: cacheKeyFn,
      eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,   // cheap tier
    }],
    edgeLambdas: [{
      functionVersion: tenantFn.currentVersion,
      eventType: cloudfront.LambdaEdgeEventType.VIEWER_REQUEST, // expensive tier
    }],
  },
  webAclId: edgeWebAcl.attrArn,   // the WAF web ACL from Challenge 1
  // domainNames + certificate: your ACM cert in us-east-1 for the capstone domain
});
```

The two associations on the *same* viewer-request event — a CloudFront Function *and* a Lambda@Edge function — is the cost-split made concrete: both run on the request, but the cheap one does the high-volume transform and the costly one does only the crypto. The origin group is the edge's failover. Copy the shape; tag everything.

---

## Submission

Push the branch/PR into the capstone repo. In your engineering journal, answer: *Your CUR query showed X% untagged spend. Which resources were they, and what does that tell you about your IaC tagging discipline across Weeks 11–13? And: at your capstone's measured steady-state, is a 1-year Compute Savings Plan the right commitment, or would you wait? Defend the call with the break-even number.* The honest answers — naming the untagged resources, and committing (or declining to commit) with a number — are the FinOps skill the capstone is graded on.

---

## What this sets up

Week 15 is the capstone defense and chaos drill. The **"CloudFront origin failure"** bonus drill runs against the origin group you built here; the **cost report** deliverable ("actual dollar number for one week of capstone operation, with a tagged breakdown") *is* the dashboard and CUR query you built this week, run over the defense week's usage. Do not tear down the FinOps stack — Week 15 reads the same CUR. The edge layer you can rebuild from CDK in minutes, but the cost history only accumulates if you leave the CUR running. Keep it.
