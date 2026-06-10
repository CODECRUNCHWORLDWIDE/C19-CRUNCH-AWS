# Mini-Project — The Observability Layer

> Deliver a working observability layer over the Week-10 event pipeline and the Week-11 inference path: OpenTelemetry instrumentation shipping through the **ADOT collector** (Lambda extension on the serverless side, EKS DaemonSet on the container side), traces to **X-Ray**, metrics and structured logs to **CloudWatch**, a **three-tier dashboard-as-code**, a **multi-window burn-rate alarm** on a 99.9% SLO, and a **Synthetics canary** against the public API. The whole thing is defined in CDK (TypeScript), deploys from zero, and produces a cost report. **This layer becomes the capstone's observability spine — the burn-rate alarms, canary, traces, and dashboards-as-code the capstone spec requires verbatim.**

This is the week's capstone-feeder. Everything you built in the exercises and the challenge gets assembled into one CDK app you can `cdk deploy --all` from a blank account and tear down with `cdk destroy --all`. When you reach Week 13 and the capstone build begins, you will *import this stack*, not rebuild it. Build it to keep.

**Estimated time:** ~7.5 hours (Thursday spill-over, Friday, Saturday in the suggested schedule).

---

## How this compounds

The syllabus is explicit that Week 12's output is not a throwaway lab — it is the observability layer the capstone is graded on:

- It **instruments the Week-10 event pipeline.** In Week 10 you built API Gateway → Lambda → EventBridge → (SQS / Step Functions / Firehose). This week you add OTel spans across that path and propagate trace context so one request is one trace. If you kept the Week-10 stack, instrument it directly; if you didn't, this project includes a minimal API + Lambda so you are not blocked — but wire it to the real Week-10 pipeline if you have it.
- It **instruments the Week-11 inference path.** The `recommend` Lambda that calls the SageMaker endpoint (Path A) and Bedrock Haiku (Path B) gets a span per path, with the Bedrock token usage emitted as a metric. The capstone's recommendation feature ships with this instrumentation already on it.
- It **becomes the capstone's alarm catalog.** The capstone spec calls for "burn-rate alarms on a 99.9% SLO" and "a Synthetics canary against the public API." This is where both are authored, as code, ready to import.
- It **becomes the capstone's dashboards-as-code.** The capstone spec calls for "CloudWatch dashboards defined in CDK." The three-tier dashboard you build here is that deliverable.

So the acceptance bar is higher than a lab: the IaC must be clean enough to import into the capstone monorepo in Week 13, and the alarms must have been *proven* to fire (the challenge's synthetic-outage step).

---

## What you will build

A CDK (TypeScript) app with three stacks plus the instrumentation woven into the services:

```
                  Week-10 pipeline + Week-11 inference path
                          (instrumented with OTel)
                                    │
        serverless side            │            container side
   ┌──── ADOT Lambda extension ────┤──── ADOT EKS DaemonSet (IRSA) ────┐
   │   (AWS_LAMBDA_EXEC_WRAPPER)    │      (one collector per node)     │
   └───────────────┬───────────────┴───────────────┬───────────────────┘
                   │ traces (awsxray)               │ metrics (awsemf)
                   ▼                                ▼
   ┌───────── TelemetryStack ──────────┐  ┌──── DashboardAlarmStack ────┐
   │  X-Ray (service map + traces)      │  │  3-tier CloudWatch dashboard│
   │  CloudWatch Logs (retention set!)  │  │  multi-window burn-rate SLO │
   │  EMF custom metrics                │  │  composite alarms           │
   │  Container/Lambda Insights         │  │  page + ticket SNS topics   │
   └────────────────────────────────────┘  └──────────────┬─────────────┘
                                                           │
                                      ┌──── CanaryStack ───┴────┐
                                      │  Synthetics canary on    │
                                      │  the public API endpoint │
                                      │  (treatMissingData=BREACHING)
                                      └──────────────────────────┘
```

The instrumentation (OTel spans) is shared across both deployment topologies; only the collector deployment differs (extension vs DaemonSet), exactly as the lectures teach.

---

## Required architecture

### Instrumentation

- **OpenTelemetry, not the X-Ray SDK.** The `recommend` Lambda and any EKS workload emit OTel spans. Auto-instrumentation covers the boto3/HTTP boundaries; you add **manual spans** around the SageMaker call (`invoke_endpoint`) and the Bedrock call (`converse`) so the two inference paths appear as named spans.
- **Trace context propagation** from API Gateway through the Lambda (via `tracing: ACTIVE`). Propagating across the EventBridge boundary is a documented stretch goal; at minimum the synchronous request path must be one connected trace.
- **Structured JSON logs** (Lambda Powertools `Logger`) with the `trace_id` on every line, so the trace→log pivot is one Logs Insights query.
- **EMF custom metrics** (Powertools `Metrics`) for per-request numbers — inference latency per path, Bedrock token counts — never `PutMetricData` on the request path.

### Collector

- **Serverless side:** the ADOT **Lambda extension layer** with `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument` and a bundled collector config exporting `awsxray` (traces) + `awsemf` (metrics). The layer ARN is Region/arch-specific — pin the live version and document it.
- **Container side:** the ADOT collector as an **EKS DaemonSet** using an **IRSA**-bound ServiceAccount scoped to X-Ray write + CloudWatch agent — *not* the node role. (If you have no EKS workload this week, the DaemonSet may serve a single demo pod; the capstone's EKS services attach to it later.)

### CloudWatch backend

- **Log groups with retention set on every one.** No "logs forever" defaults. Document the retention you chose and why.
- **A three-tier dashboard in CDK:** top tier SLO + error-budget-remaining + burn rate; middle tier the golden signals (latency p50/p99, traffic, errors, saturation); bottom tier drill-down links (X-Ray service map, a saved Logs Insights query).
- **Container Insights / Lambda Insights** enabled where you have EKS/Lambda workloads, justified (they cost per metric).

### Alarms and SLO

- **A 99.9% availability SLO** on the public API with a clear SLI.
- **A multi-window, multi-burn-rate alarm set** (14.4 / 6 / 3 rows minimum), fast burns to a **page** SNS topic, slow burns to a **ticket** topic, each row a composite of long+short windows. (This is the challenge's deliverable, imported here.)
- **`treatMissingData` chosen on purpose** for each alarm.

### Synthetics

- **A canary** hitting the public API every minute, with its success metric alarmed and `treatMissingData: BREACHING` (a silent canary is a symptom). The canary is the heartbeat SLI for the SLO.

### Cross-cutting

- **Tags.** Every resource tagged `team`, `service`, `environment` — the capstone's FinOps requirement starts here.
- **One-command deploy/destroy.** `cdk deploy --all` from zero; `cdk destroy --all` leaves nothing billing (especially no canary, no high-res alarms, no orphaned EKS).

---

## Rules

- **CDK (TypeScript) is the source of truth.** You may use the CLI/SDK to *drive* a synthetic outage or *invoke* the Lambda, but every persistent resource (log groups, metrics filters, alarms, canary, dashboard, collector config) is in CDK so the capstone can import it.
- **OpenTelemetry instrumentation, not the X-Ray SDK.** The portability is the point; a submission that hard-codes the X-Ray SDK does not satisfy the "instrument once, export anywhere" requirement.
- **The burn-rate alarm must have been proven to fire.** Include the synthetic-outage capture (detection + recovery-confirmation times) in the README. An unproven alarm is not acceptable for the capstone.
- **Every log group must have a retention policy.** A log group without retention is an automatic fail — it is the week's signature cost trap.
- **Cost report required.** Real dollar figures for the observability bill, not estimates-from-memory.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c19-week-12-observability-<yourhandle>`.
- [ ] `npx cdk deploy --all` from a clean account stands up the telemetry, dashboard/alarm, and canary stacks with no manual console steps (other than the documented ADOT layer ARN and any one-time Bedrock model-access opt-in).
- [ ] The `recommend` Lambda emits OTel traces visible as a connected X-Ray trace (API Gateway → Lambda → SageMaker span → Bedrock span). Include a service-map screenshot.
- [ ] Structured logs carry `trace_id`; a Logs Insights query filtering by a `trace_id` returns the exact request's log line. Demonstrate the trace→log pivot.
- [ ] EMF custom metrics for per-path inference latency and Bedrock tokens exist (confirmed not sent via `PutMetricData`).
- [ ] The ADOT collector runs as a Lambda extension AND as an EKS DaemonSet with IRSA (the SA's role, not the node role, carries the X-Ray/CloudWatch grants). Show the IRSA annotation.
- [ ] Every log group has a retention policy. Show them.
- [ ] A three-tier CloudWatch dashboard exists in CDK. Include a screenshot.
- [ ] A multi-window burn-rate alarm on a 99.9% SLO, fast→page and slow→ticket, **proven by a synthetic outage** with recorded detection and recovery-confirmation times.
- [ ] A Synthetics canary runs against the public API with `treatMissingData: BREACHING` on its alarm.
- [ ] Every resource tagged `team`, `service`, `environment`.
- [ ] `npx cdk destroy --all` removes everything, including the canary and any EKS the project created. Prove nothing remains billing.
- [ ] A `COSTREPORT.md` with the figures below.
- [ ] A `README.md` with: one-paragraph description, exact from-clone setup commands, the service-map and dashboard screenshots, the trace→log pivot demo, and the synthetic-outage timing capture.

---

## The cost report

`COSTREPORT.md` must contain, with real numbers pulled from the pricing pages (cite the date you pulled them):

1. **Log ingestion.** GB/day your instrumented services ingest and the per-GB cost — the biggest observability line for most teams.
2. **Log storage.** What your chosen retention costs per month, and what "forever" *would* have cost (the trap you avoided).
3. **Custom metrics.** Number of EMF custom metrics and their per-metric-month cost — and a note on what the same metrics via `PutMetricData` per-call would have cost at your request volume.
4. **X-Ray.** Your sampling rate, traces recorded per day, and the per-trace cost.
5. **Synthetics.** Per-canary-run cost × runs/day.
6. **Container/Lambda Insights.** Per-metric cost for the infra metrics you enabled.
7. **Total observability bill.** The all-in daily and monthly figure, and what fraction of the *workload's* compute bill it represents — the number that tells you whether your observability is proportionate.

---

## Suggested build order

1. **Thursday spill-over (1 h).** Scaffold the CDK app (`cdk init app --language typescript`). Create `TelemetryStack`: log groups with retention, the `recommend` Lambda with the ADOT layer + wrapper + Active tracing, scoped X-Ray IAM. Deploy and confirm a trace lands.
2. **Friday morning (2 h).** Add manual spans around the SageMaker and Bedrock calls; add EMF metrics for latency and tokens. Wire structured logging with `trace_id`. Demonstrate the trace→log pivot.
3. **Friday afternoon (1 h).** Build `DashboardAlarmStack`: the three-tier dashboard and the multi-window burn-rate alarm set (import from the challenge). Wire the page/ticket SNS topics.
4. **Saturday morning (2.5 h).** Build `CanaryStack` (Synthetics canary + heartbeat alarm). If you have EKS, deploy the ADOT DaemonSet with IRSA and point a workload at it. Run the synthetic outage and capture detection/recovery times.
5. **Saturday afternoon (1 h).** Write `COSTREPORT.md` and `README.md`. Run the full deploy-prove-destroy loop once, clean, and confirm nothing is left billing (canary, alarms, EKS).

---

## A worked snippet — the three-tier dashboard in CDK

So you are not staring at a blank file, here is the dashboard skeleton. This is the resource the capstone imports.

```typescript
import * as cw from 'aws-cdk-lib/aws-cloudwatch';

const dash = new cw.Dashboard(this, 'RecommendDashboard', {
  dashboardName: 'recommend-observability',
});

// --- Tier 1: SLO / burn rate ---
const errorRatio = new cw.MathExpression({
  expression: 'e / t',
  usingMetrics: {
    e: new cw.Metric({ namespace: 'AWS/ApiGateway', metricName: '5XXError',
      dimensionsMap: { ApiName: 'recommend-api' }, statistic: 'Sum' }),
    t: new cw.Metric({ namespace: 'AWS/ApiGateway', metricName: 'Count',
      dimensionsMap: { ApiName: 'recommend-api' }, statistic: 'Sum' }),
  },
  label: 'error ratio (SLI inverse)',
});
dash.addWidgets(new cw.SingleValueWidget({
  title: 'SLO: error ratio (budget = 0.001)',
  metrics: [errorRatio], width: 24,
}));

// --- Tier 2: golden signals ---
const p99 = new cw.Metric({ namespace: 'AWS/ApiGateway', metricName: 'Latency',
  dimensionsMap: { ApiName: 'recommend-api' }, statistic: 'p99' });
const traffic = new cw.Metric({ namespace: 'AWS/ApiGateway', metricName: 'Count',
  dimensionsMap: { ApiName: 'recommend-api' }, statistic: 'Sum' });
const sageLatency = new cw.Metric({ namespace: 'MyApp/Recommend',
  metricName: 'InferenceLatencyMs', dimensionsMap: { Path: 'sagemaker' }, statistic: 'Average' });
const bedrockLatency = new cw.Metric({ namespace: 'MyApp/Recommend',
  metricName: 'InferenceLatencyMs', dimensionsMap: { Path: 'bedrock' }, statistic: 'Average' });

dash.addWidgets(
  new cw.GraphWidget({ title: 'Latency (p99) & Traffic', left: [p99], right: [traffic], width: 12 }),
  new cw.GraphWidget({ title: 'Inference latency by path', left: [sageLatency, bedrockLatency], width: 12 }),
);

// --- Tier 3: drill-down (a text widget with the saved queries / map links) ---
dash.addWidgets(new cw.TextWidget({
  markdown: [
    '### Drill-down',
    '- [X-Ray service map](https://console.aws.amazon.com/xray/home#/service-map)',
    '- Logs Insights: `fields @timestamp, level, path, trace_id | filter trace_id = "<paste>"`',
  ].join('\n'),
  width: 24, height: 4,
}));
```

The three tiers map exactly to the triage order: glance at tier 1 (is the SLO healthy?), characterize in tier 2 (which signal moved?), and jump to the per-request detail in tier 3. That is the dashboard an on-call engineer actually uses, and it is what the capstone is graded on.

---

## Submission

Push the repo. In your engineering journal, answer: *When you fired the synthetic outage, how long did the fast-burn alarm take to page, and how long to clear? Were your windows right? What is your observability bill as a fraction of your workload's compute bill — and is that proportionate?* The honest answers (a well-tuned alarm detects a hard outage in minutes and clears in minutes; observability typically runs 5–15% of compute and more than that is a signal to sample harder) are the point. Knowing them about your own system is the skill.

---

## What this sets up

Week 13 begins the capstone build and **imports both this observability layer and the security stack you build next.** The capstone is graded on the exact four artifacts here: burn-rate alarms on a 99.9% SLO, a Synthetics canary, distributed traces via ADOT, and CloudWatch dashboards-as-code. Do not delete the repo when the week ends — you will `git submodule`/copy it forward, and the chaos drill in Week 15 will read *these* dashboards while it breaks *that* system.
