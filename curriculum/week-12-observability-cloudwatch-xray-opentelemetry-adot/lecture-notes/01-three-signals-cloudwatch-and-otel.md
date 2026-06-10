# Lecture 1 — The Three Signals, CloudWatch, and Why OpenTelemetry Is the Instrumentation

> **Reading time:** ~75 minutes. **Hands-on time:** ~60 minutes (you write your first structured logs, run a Logs Insights query, and emit an EMF custom metric).

This is the lecture that turns "we have logs somewhere" into "we have observability." The difference is not the volume of data. The difference is that the three signals — **traces, metrics, logs** — are *connected*, *queryable*, and *priced on purpose*. By the end you will understand what each signal answers and the order you reach for them, how CloudWatch Logs, Metrics, and Alarms actually work (including the cost traps that bite every team once), why the Embedded Metric Format is the production default for custom metrics, and why we instrument with **OpenTelemetry** rather than the X-Ray SDK directly. Lecture 2 takes the traces into X-Ray and ADOT and builds the burn-rate SLO alarm. This lecture lays the foundation.

## 1.1 — Observability is three signals, and the order you read them matters

A junior engineer, paged at 3 a.m., opens the logs. They grep for `ERROR`, find ten thousand lines, and start scrolling. Forty minutes later they have a theory. A senior engineer, paged for the same incident, opens the **trace** first, sees that the `checkout` service's call to `payments` is taking 4 seconds instead of 40 milliseconds, opens the **metric** to confirm it started 6 minutes ago and is affecting 30% of requests, then opens **one log line** — the log for that exact slow request, found by its `trace_id` — and reads the timeout exception. Two minutes, root cause. The difference is not talent. It is that the senior engineer reads the signals in the right order, and the signals are wired together so the next step is one click.

That order is the spine of this week:

```
   trace   →   metric   →   log
   WHERE       HOW BAD       WHAT EXACTLY
   (which      (how many,    (the one
    span)       how long)     request)
```

- **A trace** answers *where*. It is the end-to-end journey of one request, drawn as a tree of timed **spans** — one span per service call, per database query, per external API hit. The trace tells you which hop is slow or failing. It is the first thing you open during an incident because it narrows a hundred services to one.
- **A metric** answers *how bad and for how long*. It is a number sampled over time — request latency p99, error rate, queue depth. Metrics are cheap to store and aggregate beautifully, but they have **no per-request detail**: a metric says "30% of requests failed," not "*this* request failed because the token expired."
- **A log** answers *what exactly happened*. It is the highest-detail, highest-volume, highest-cost signal. You do not read all the logs; you read the *one* log line for the request the trace pointed you at. Logs are where the stack trace and the variable values live.

The three signals trade off detail against cost in exactly that order: logs are richest and most expensive, metrics are cheapest and least detailed, traces sit in between and are the navigation layer. **The skill this week is connecting them** — putting `trace_id` in every log line, deriving metrics from traces and logs, so that the pivot from "which span" to "the exact log" is instantaneous. A pile of three disconnected signals is not observability; it is three piles.

### The three-tier dashboard

For the capstone you will draw a three-tier dashboard, top to bottom:

1. **Top tier — SLO and burn rate.** Is the service meeting its objective? How much error budget is left? This is the only tier an on-call engineer should *need* to glance at.
2. **Middle tier — the golden signals.** Latency (p50/p99), traffic (requests/sec), errors (rate), and saturation (CPU/memory/queue depth). The four signals from the Google SRE book. When the top tier turns red, you look here to characterize the failure.
3. **Bottom tier — drill-down links.** A button to the X-Ray service map, a saved Logs Insights query, a link to the trace view filtered to the affected service. This tier is the bridge to the per-request detail.

We build this dashboard as code (CDK) in the mini-project. Hold the shape; everything this week populates one of its tiers.

## 1.2 — CloudWatch Logs: where the bill hides

CloudWatch Logs is the managed log store. The hierarchy is simple: a **log group** (e.g. `/aws/lambda/recommend`) contains **log streams** (one per execution environment / instance), which contain **log events** (one timestamped line each). Lambda, ECS, EKS (via Fluent Bit), API Gateway, and most AWS services write to log groups automatically.

There are two facts about CloudWatch Logs that every team learns the expensive way, and you will learn them now instead.

**Fact one: logs are forever by default.** A freshly created log group has **no retention policy**, which means CloudWatch keeps the data *indefinitely* and bills you for storage every month, forever. This is the single most common CloudWatch cost surprise. The fix is one line, and you should write it in the same breath as you create the log group:

```typescript
import * as logs from 'aws-cdk-lib/aws-logs';

new logs.LogGroup(this, 'RecommendLogs', {
  logGroupName: '/aws/lambda/recommend',
  retention: logs.RetentionDays.TWO_WEEKS,   // NEVER omit this
  removalPolicy: RemovalPolicy.DESTROY,       // lab; use RETAIN in prod
});
```

Pick a retention that matches your need: two weeks for debug-level application logs, a year or more (or ship to S3) for audit logs you must keep for compliance. The point is to *choose*, not to let the default choose "forever" for you.

**Fact two: you pay to ingest, to store, and to query.** Ingestion is per-GB (the big line item for chatty services). Storage is per-GB-month (the line that grows if you skipped fact one). And **Logs Insights queries are billed per GB scanned** — exactly like Athena in Week 11. "Bytes scanned is dollars" applies here too: a Logs Insights query over a month of an unfiltered, high-volume log group scans a lot and costs accordingly. Filter early, narrow the time range, and structure your logs so you scan less.

### Structured logging is the unlock

The most important habit this week: **log structured JSON, not free-text strings.** Compare:

```
ERROR could not reach payments for user 4821 after 3 retries (4.2s)
```

versus:

```json
{"level":"ERROR","msg":"payments unreachable","user_id":"4821","retries":3,"latency_ms":4210,"trace_id":"1-67a8...","service":"checkout"}
```

The first is a string a human can read and a machine cannot query. The second is queryable: Logs Insights can `filter latency_ms > 4000`, `stats count() by service`, and — critically — `filter trace_id = "1-67a8..."` to find the exact log for the request your trace pointed you at. **That `trace_id` field is the bridge between the trace and the log.** Wire it in and the "trace > metric > log" pivot becomes a one-line query.

In a Lambda, the cleanest way to get structured logs with the `trace_id` already injected is **AWS Lambda Powertools**:

```python
from aws_lambda_powertools import Logger

logger = Logger(service="recommend")  # JSON logs, with cold-start, request id, and trace id auto-injected

@logger.inject_lambda_context
def handler(event, context):
    logger.info("handling recommendation", extra={"user_id": event["user_id"]})
    # ...
    logger.warning("bedrock latency high", extra={"latency_ms": 812})
    return {"ok": True}
```

Powertools' `Logger` emits JSON, automatically adds `function_name`, `cold_start`, `function_request_id`, and — when X-Ray tracing is on — `xray_trace_id`. You get structured, correlatable logs for free.

### Logs Insights: your log group is a queryable dataset

Logs Insights is a purpose-built query language over log groups. The shape is `fields → filter → stats → sort → limit`, piped:

```sql
fields @timestamp, service, latency_ms, trace_id
| filter level = "ERROR"
| filter latency_ms > 3000
| stats count() as errors, avg(latency_ms) as avg_ms by service
| sort errors desc
| limit 20
```

This reads: pull these fields, keep only error lines over 3 seconds, group by service counting errors and averaging latency, show the worst offenders. It is SQL-shaped and you will live in it during incidents. Two operational notes: it parses JSON fields automatically (so `filter latency_ms > 3000` works only if you logged structured JSON — see why structured logging matters), and it **scans the time range you give it**, so always set the tightest window you can.

## 1.3 — CloudWatch Metrics, and why custom metrics are a cost decision

A CloudWatch **metric** is a time-ordered set of data points in a **namespace** (e.g. `AWS/Lambda` or your own `MyApp/Recommend`), identified by **dimensions** (key-value pairs like `FunctionName=recommend`). AWS services publish hundreds of metrics for free — Lambda duration, errors, throttles; ALB request count, target response time; DynamoDB consumed capacity. You query, alarm, and graph these without doing anything.

The interesting decision is **custom metrics** — numbers *your* code emits. There are two ways, and the difference is a real bill.

**The naive way: `PutMetricData`.** You call the API directly:

```python
import boto3
cw = boto3.client("cloudwatch")

cw.put_metric_data(
    Namespace="MyApp/Recommend",
    MetricData=[{
        "MetricName": "InferenceLatencyMs",
        "Dimensions": [{"Name": "Path", "Value": "sagemaker"}],
        "Value": 9.4,
        "Unit": "Milliseconds",
    }],
)
```

This works, but **`PutMetricData` is billed per API call**, and each call is a synchronous network round-trip on your request path. Emit a custom metric on every request and you have added latency *and* a per-request API charge. For low-volume metrics this is fine. For per-request metrics it is a trap.

**The production way: Embedded Metric Format (EMF).** EMF lets you emit metrics *as a specially-structured log line*. You were already paying to ingest that log; CloudWatch parses the EMF JSON and extracts the metrics for free of additional API cost. No `PutMetricData` call, no extra round-trip, and you can attach **high-cardinality dimensions** (like `user_id`) to the log for debugging while only promoting low-cardinality dimensions to actual metrics. An EMF log line looks like this:

```json
{
  "_aws": {
    "Timestamp": 1733788800000,
    "CloudWatchMetrics": [{
      "Namespace": "MyApp/Recommend",
      "Dimensions": [["Path"]],
      "Metrics": [{"Name": "InferenceLatencyMs", "Unit": "Milliseconds"}]
    }]
  },
  "Path": "sagemaker",
  "InferenceLatencyMs": 9.4,
  "user_id": "4821",
  "trace_id": "1-67a8..."
}
```

CloudWatch sees the `_aws` block, extracts `InferenceLatencyMs` as a metric with dimension `Path`, and stores `user_id` and `trace_id` as searchable log fields. You almost never hand-write EMF — Powertools does it:

```python
from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics(namespace="MyApp/Recommend", service="recommend")

@metrics.log_metrics  # flushes the EMF blob at the end of the invocation
def handler(event, context):
    metrics.add_metric(name="InferenceLatencyMs", unit=MetricUnit.Milliseconds, value=9.4)
    metrics.add_dimension(name="Path", value="sagemaker")
    return {"ok": True}
```

> **The rule:** for any metric you emit per-request or with cardinality, use **EMF** (via Powertools), not `PutMetricData`. Reserve direct `PutMetricData` for low-frequency, batch, or out-of-band metrics. This is the single most common custom-metrics cost mistake, and now you won't make it.

A note on **resolution**: standard metrics have 1-minute granularity; **high-resolution** metrics go to 1-second but cost more and are rarely needed outside latency-critical alarming. Default to standard.

## 1.4 — CloudWatch Alarms: thresholds, composite, anomaly, and the missing-data trap

A metric you never alarm on is a graph nobody looks at. An **alarm** watches a metric (or a metric-math expression) and transitions between `OK`, `ALARM`, and `INSUFFICIENT_DATA`, firing an action (usually an SNS topic → PagerDuty / Slack / email) on transition.

### Static-threshold alarms and `M out of N`

The basic alarm: "fire if the metric crosses a threshold." But a single data point over threshold is noise — one slow minute is not an incident. So alarms evaluate **`M out of N` data points**: fire only if `M` of the last `N` periods breach. This is your first noise filter.

```typescript
import * as cw from 'aws-cdk-lib/aws-cloudwatch';

const errorRate = new cw.Metric({
  namespace: 'AWS/ApiGateway',
  metricName: '5XXError',
  dimensionsMap: { ApiName: 'recommend-api' },
  statistic: 'Sum',
  period: Duration.minutes(1),
});

new cw.Alarm(this, 'Api5xxAlarm', {
  metric: errorRate,
  threshold: 5,
  evaluationPeriods: 5,        // N = 5 periods
  datapointsToAlarm: 3,        // M = 3 must breach -> fire (filters single-minute blips)
  comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
  treatMissingData: cw.TreatMissingData.NOT_BREACHING,
});
```

### The `treatMissingData` trap

That last line, `treatMissingData`, is the setting that has caused more "why didn't the alarm fire?" postmortems than any other. When a metric stops reporting — because the service is *so* broken it emits nothing — what should the alarm do? The options:

- `NOT_BREACHING` — missing data is "fine." **Danger:** a service that crashed and stopped emitting looks healthy.
- `BREACHING` — missing data is "bad." Safe for "this should always be reporting" metrics, but noisy if the metric is naturally sparse.
- `IGNORE` — missing data doesn't change the current state.
- `MISSING` — evaluate using only the data points that exist (the default).

The judgment: for a **heartbeat** metric (a canary success, a synthetic ping that *must* report), use `BREACHING` so silence pages you. For a **sparse error-count** metric where "no errors reported" genuinely means "no errors," `NOT_BREACHING` is correct. Choosing wrong is how a total outage produces zero alarms. Decide on purpose, every time.

### Composite alarms: killing the noise

When ten alarms all fire from one root cause (the database is down, so every service that touches it alarms), your on-call drowns. A **composite alarm** has a state that is a boolean expression over *other* alarms:

```typescript
new cw.CompositeAlarm(this, 'CheckoutDegraded', {
  alarmRule: cw.AlarmRule.allOf(
    cw.AlarmRule.fromAlarm(api5xxAlarm, cw.AlarmState.ALARM),
    cw.AlarmRule.not(cw.AlarmRule.fromAlarm(maintenanceWindowAlarm, cw.AlarmState.ALARM)),
  ),
  actionsEnabled: true,
});
```

This says: "page only if the API 5xx alarm is firing **AND** we are not in a maintenance window." Composite alarms let you express "page on the *combination*, suppress the children" so on-call gets one meaningful page, not ten. They are the primary tool against alert fatigue.

### Anomaly detection: when there is no good fixed threshold

Some metrics have no sensible static threshold because "normal" varies by time of day and day of week. Traffic at 3 a.m. Sunday is legitimately 1/20th of Tuesday lunch. A fixed threshold either pages on every Tuesday or never catches a Sunday-night anomaly. **Anomaly detection** trains a model on the metric's history and produces a *band* of expected values; the alarm fires when the metric leaves the band.

```typescript
const anomalyAlarm = new cw.CfnAlarm(this, 'TrafficAnomaly', {
  comparisonOperator: 'LessThanLowerOrGreaterThanUpperThreshold',
  evaluationPeriods: 3,
  thresholdMetricId: 'ad1',
  metrics: [
    { id: 'm1', metricStat: { metric: { namespace: 'AWS/ApiGateway', metricName: 'Count',
        dimensions: [{ name: 'ApiName', value: 'recommend-api' }] }, period: 300, stat: 'Sum' },
      returnData: true },
    { id: 'ad1', expression: 'ANOMALY_DETECTION_BAND(m1, 2)', label: 'Count expected band', returnData: true },
  ],
});
```

`ANOMALY_DETECTION_BAND(m1, 2)` is a 2-standard-deviation band around the learned normal. Use anomaly detection for traffic, latency-with-seasonality, and any metric where "normal" is a moving target. Use static thresholds for hard limits (error rate must be under 0.1%, queue depth must not exceed 10,000) where the threshold is a *business* number, not a statistical one. We use both this week: a static threshold for the SLO error rate, anomaly detection for traffic shape.

## 1.5 — Synthetics, RUM, and Evidently in a paragraph each

**Synthetics canaries.** A metric is reactive: it tells you a real user hit an error. A **canary** is proactive: a scheduled script (Node/Puppeteer or Python/Selenium) that hits your endpoint from outside, every minute, and reports success, latency, and a screenshot. It catches "the site is down" *before* a user does, and it works even when traffic is zero (so you are not blind at 3 a.m. when no one is testing your checkout for you). The canary's success metric is the perfect SLO signal — it is the "is the service up" heartbeat, and it is the one we alarm on Friday. Always set its alarm's `treatMissingData` to `BREACHING`: a canary that stopped reporting is itself a symptom.

**RUM (Real User Monitoring).** Synthetics tests from a robot in one Region; **RUM** instruments the *actual browser* of *actual users* with a JavaScript snippet, reporting real page-load times, JS errors, and the geographic/device distribution of your real traffic. Synthetics answers "is it up from us-east-1"; RUM answers "is it fast for a user on a phone in Brazil." Use both — they catch different failures.

**Evidently.** Feature flags and A/B experiments evaluated server-side, with the results wired into CloudWatch metrics so you can measure whether the new feature moved the number you care about. It is the "ship behind a flag, measure the impact, roll back without a deploy" tool. Out of scope for the core lab but worth knowing it exists and is the AWS-native answer to LaunchDarkly-style flagging.

## 1.6 — The pivot: why we instrument with OpenTelemetry, not the X-Ray SDK

Now we cross from "CloudWatch as the backend" to "how telemetry gets generated," and we make a decision that shapes the rest of the course.

AWS has its own tracing SDK — the X-Ray SDK — and you *could* instrument your code with it directly. **You should not.** Instead, you instrument with **OpenTelemetry (OTel)**, the CNCF vendor-neutral standard, and let the **ADOT collector** ship the resulting traces to X-Ray. Here is why that indirection is worth it.

**OpenTelemetry is the instrumentation; the backend is a config line.** When you write OTel spans in your code, the spans are vendor-neutral. The decision of *where they go* — X-Ray, Jaeger, Tempo, Datadog, Honeycomb, all of them at once — lives in the **collector's exporter config**, not in your application. Change clouds, change vendors, add a second backend: your application code does not change one line. The X-Ray SDK locks your instrumentation to X-Ray; OTel keeps it portable. This is the same lesson as Week 11's "Bedrock is a router" — you are decoupling your code from a single vendor on purpose.

The OpenTelemetry data model you must know:

- **Span** — one timed operation, with a name, start/end time, a set of **attributes** (key-value tags like `http.status_code=500`), **events** (timestamped logs within the span), and a **status** (OK / ERROR).
- **Trace** — a tree of spans sharing a **trace context** (a `trace_id` plus the parent `span_id`).
- **Context propagation** — how the `trace_id` travels from one service to the next: injected into an outgoing HTTP header (`traceparent`, the W3C standard) and extracted by the receiver, so the two services' spans join the same trace. Propagating context across an *asynchronous* boundary (EventBridge, SQS) is the hard part, and a stretch goal this week.
- **Resource attributes** — attributes describing the *emitter* (service name, version, deployment environment, cloud region), attached to every span from that process.
- **Baggage** — key-value data that rides along the context across services (e.g. a `tenant_id` you want available on every downstream span).

And the three moving parts of the OTel stack:

- **The API** — the interface your code calls (`tracer.start_span(...)`). Stable, minimal.
- **The SDK** — the implementation that batches, samples, and exports. Configured once at startup.
- **The Collector** — a separate process/agent that *receives* telemetry (over OTLP, the OpenTelemetry wire protocol), processes it (batching, filtering, adding attributes), and *exports* it to backends. **ADOT is AWS's distribution of this Collector**, pre-built with the AWS exporters (`awsxray` for traces, `awsemf` for metrics) and supported by AWS.

Auto-instrumentation vs manual: OTel ships **auto-instrumentation** libraries that wrap common frameworks (boto3, requests, Flask, the AWS Lambda runtime) and emit spans with *no code changes* — you set an environment variable and your HTTP calls and AWS SDK calls produce spans automatically. **Manual instrumentation** is you adding spans around *your* business logic (`with tracer.start_as_current_span("score_model"):`) where the auto-instrumentation can't see. The production pattern is both: auto-instrument the framework boundaries for free, manually instrument the few spans that carry your domain meaning.

Here is the minimal Python OTel setup the Wednesday exercise builds on (the SDK wiring; the Lambda case is even simpler because the ADOT layer does most of it):

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Resource attributes describe THIS service; they ride on every span.
resource = Resource.create({"service.name": "recommend", "deployment.environment": "dev"})

provider = TracerProvider(resource=resource)
# Export over OTLP to the local ADOT collector (a sidecar / DaemonSet / Lambda extension).
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4317")))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("recommend")

def score(features):
    # A manual span around YOUR business logic. boto3 calls inside are auto-instrumented.
    with tracer.start_as_current_span("score_model") as span:
        span.set_attribute("model.features", len(features))
        result = run_inference(features)   # any boto3 call here emits its own child span
        span.set_attribute("model.label", result)
        return result
```

Notice the exporter points at `http://localhost:4317` — the OTLP gRPC port of a *local* collector. Your code does not know or care that the collector ships to X-Ray. That is the whole point: the destination is the collector's problem, not your application's. Lecture 2 configures that collector — as a Lambda extension and as an EKS DaemonSet — and watches the traces land in X-Ray.

## 1.7 — Cost: observability is not free, and the traps are predictable

Before we leave CloudWatch, internalize where the bill comes from, because "we turned on full observability and the CloudWatch bill tripled" is a real and avoidable outcome:

- **Log ingestion** is per-GB and is usually the biggest line. Chatty `DEBUG` logging in production at scale is the top offender. Log at `INFO`, sample debug, and structure so you can filter.
- **Log storage forever** (the retention trap from §1.2). Set retention on every group.
- **Logs Insights per-GB-scanned** — narrow your queries.
- **Custom metrics via `PutMetricData`** per-call (the §1.3 trap). Use EMF.
- **High-resolution metrics and dashboards** — each dashboard and each high-res metric has a cost. Default to standard resolution.
- **X-Ray per-trace** — controlled by your **sampling rate**. You do not trace 100% of requests in production; you sample (e.g. 5% plus all errors). Lecture 2 covers sampling rules.

The discipline is the same as every other week of C19: every signal you turn on has a dollar number, and you turn it on *because* the visibility is worth that number, not reflexively. The mini-project's cost report makes you put a figure on your observability bill.

## 1.8 — What you should be able to do now

After this lecture and the Monday/Tuesday hands-on you should be able to:

- Name the three signals, what each answers, and the "trace > metric > log" triage order.
- Draw the three-tier dashboard (SLO/burn-rate → golden signals → drill-down).
- Set retention on every log group and explain the "logs are forever by default" trap.
- Write structured JSON logs with a `trace_id` and query them in Logs Insights.
- Choose EMF over `PutMetricData` for per-request custom metrics and explain why.
- Build a static-threshold alarm with `M out of N`, choose `treatMissingData` correctly, and compose alarms to kill noise.
- Explain when anomaly detection beats a fixed threshold.
- Explain why we instrument with OpenTelemetry and let ADOT export to X-Ray, instead of using the X-Ray SDK directly.
- Define span, trace, context propagation, resource attributes, and the API/SDK/Collector split.

## 1.9 — Exercises that go with this lecture

- **Exercise 1 — CloudWatch Logs, EMF, and alarms.** Emit structured logs and an EMF custom metric from a Lambda, query them in Logs Insights, build a metric filter and an alarm, and watch it fire.

Bring your structured-logging habit and your EMF metric to Wednesday. The trace work in Lecture 2 assumes your logs already carry a `trace_id` so the trace-to-log pivot works.
