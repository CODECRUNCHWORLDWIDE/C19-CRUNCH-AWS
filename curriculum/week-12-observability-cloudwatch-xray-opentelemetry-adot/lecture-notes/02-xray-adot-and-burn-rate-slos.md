# Lecture 2 — X-Ray, ADOT on Lambda and EKS, and Burn-Rate SLO Alarms

> **Reading time:** ~80 minutes. **Hands-on time:** ~75 minutes (you wire the ADOT collector, watch traces land in X-Ray, and build the burn-rate alarm).

Lecture 1 ended with a claim: you instrument with OpenTelemetry, and the *destination* of the telemetry is the collector's problem. This lecture makes that real. We walk the X-Ray service map and trace, configure the **ADOT collector** two ways — as a Lambda extension and as an EKS DaemonSet — route traces to X-Ray and metrics to CloudWatch, look at what Container Insights, Lambda Insights, and Application Signals add on top, and then build the centerpiece of the week: a **multi-window, multi-burn-rate alarm** on a 99.9% SLO that pages fast on a fast burn and slow on a slow burn. By Friday you will fire a synthetic outage and watch the alarm transition at exactly the right moment — the deliverable for the challenge.

## 2.1 — X-Ray: the service map and the trace

X-Ray is AWS's managed tracing backend. It ingests **segments** (a segment is X-Ray's name for the root span of a service's contribution to a trace) and **subsegments** (child spans — a downstream call, a DB query), correlates them by `trace_id`, and renders two views you live in during an incident:

- **The service map** — a node-and-edge graph of your services, each node colored by health (green/yellow/red) and labeled with request rate, average latency, and error percentage. One glance tells you *which* service is the problem. This is the "WHERE" from the triage order, made visual.
- **The trace view** — a waterfall of spans for a single request, each bar showing where the time went. You open this for a slow request and instantly see that 4 of the 4.2 seconds were spent in the `payments` subsegment. This is how you find the slow span.

The X-Ray data model in the terms you will use:

- **Segment** — one service's slice of a trace (e.g. the API Gateway segment, the Lambda segment).
- **Subsegment** — work inside a segment (a downstream HTTP call, a DynamoDB query, a manual block you wrapped).
- **Annotations** — indexed key-value pairs you can **filter and group traces by** in the console (e.g. `tenant_id`, `endpoint`). X-Ray indexes annotations, so use them for the dimensions you want to slice traces on. You get a limited number; spend them wisely.
- **Metadata** — non-indexed key-value data attached to a span for context. You cannot filter on it, but it shows in the trace detail. Use it for the rich debugging payload.
- **Sampling** — X-Ray does **not** trace every request in production. A **sampling rule** says, e.g., "record the first request each second, plus 5% of the rest," so you get representative traces without paying to record every call. You raise the rate for a service you are actively debugging and keep it low at steady state. The default reservoir-plus-percentage rule is sensible; tune per service.

The relationship between X-Ray and OpenTelemetry is the thing to hold onto from Lecture 1: **your code emits OTel spans; the ADOT collector's `awsxray` exporter translates them into X-Ray segments.** Annotations map from specific OTel span attributes (the `awsxray` exporter promotes attributes you list to indexed annotations). You write OTel; X-Ray is just one place the OTel goes.

### Sampling rules in depth: reservoir + fixed rate

Sampling deserves more than the one paragraph above, because it is the single lever that controls both your X-Ray bill and whether you have a trace when you need one. X-Ray's sampling decision is **made once, at the head of the trace** (head-based sampling), by the first instrumented service the request hits — usually API Gateway or your front-door Lambda. That decision is then propagated down the trace via the `X-Amzn-Trace-Id` header's `Sampled=1` flag, so every downstream service honours it and you get a *complete* trace or no trace at all (never half a trace).

Each sampling rule is a two-part budget — a **reservoir** plus a **fixed rate** — and understanding both halves is the whole game:

- **Reservoir** — a guaranteed floor expressed as *traces per second*. A reservoir of `1` means "record at least the first matching request each second, no matter what." The reservoir guarantees you always have *some* traces even on a near-idle service, so you are never blind at 3 a.m. when traffic is one request a minute. The reservoir is enforced by the X-Ray service centrally (the SDK/collector calls `GetSamplingTargets` to borrow from the shared reservoir), so it holds across all instances of a service, not per-host.
- **Fixed rate** — a percentage applied to *everything past the reservoir*. A fixed rate of `0.05` records 5% of the requests that exceed the reservoir floor. This is the part that scales with traffic: at 1,000 req/s with a reservoir of 1 and rate 0.05, you record ~1 + (999 × 0.05) ≈ 51 traces/sec, not 1,000.

The default rule that ships with every account is reservoir `1`, rate `0.05` — one per second plus 5% of the rest, matching every request. You override it with **custom rules**, evaluated in **priority order** (lowest number wins), with the default rule always last as the catch-all. Custom rules let you sample *aggressively* on the endpoints you are debugging and *cheaply* on the chatty health checks. Here is a realistic rule set as the JSON the `CreateSamplingRule` API (and the CDK `CfnSamplingRule`) takes:

```json
{
  "SamplingRule": {
    "RuleName": "checkout-high-fidelity",
    "Priority": 100,
    "ReservoirSize": 5,
    "FixedRate": 0.5,
    "ServiceName": "checkout",
    "ServiceType": "*",
    "Host": "*",
    "HTTPMethod": "POST",
    "URLPath": "/checkout*",
    "ResourceARN": "*",
    "Version": 1
  }
}
```

Read it as: "for `POST /checkout*` on the `checkout` service, guarantee 5 traces/sec and sample 50% of the rest" — high fidelity because checkout is the revenue path you most want traces for. A second, lower-priority rule does the opposite for noise:

```json
{
  "SamplingRule": {
    "RuleName": "healthcheck-drop",
    "Priority": 50,
    "ReservoirSize": 0,
    "FixedRate": 0.0,
    "ServiceName": "*",
    "ServiceType": "*",
    "Host": "*",
    "HTTPMethod": "GET",
    "URLPath": "/health*",
    "ResourceARN": "*",
    "Version": 1
  }
}
```

Reservoir `0` and rate `0.0` means "never trace `/health*`" — those load-balancer pings would otherwise drown your trace store and your bill in noise that has zero debugging value. Note the lower priority number (`50` < `100`): the health-check drop is evaluated *first*, so a health check never even reaches the high-fidelity rule. Deploy these rules with CDK so they are versioned with the rest of your stack:

```typescript
import * as xray from 'aws-cdk-lib/aws-xray';

new xray.CfnSamplingRule(this, 'CheckoutHighFidelity', {
  samplingRule: {
    ruleName: 'checkout-high-fidelity', priority: 100,
    reservoirSize: 5, fixedRate: 0.5,
    serviceName: 'checkout', serviceType: '*', host: '*',
    httpMethod: 'POST', urlPath: '/checkout*', resourceArn: '*', version: 1,
  },
});
```

Two caveats that bite people. First, X-Ray sampling is **head-based** — the decision is made before the request runs, so you cannot say "always trace requests that errored" purely through sampling rules (the error hasn't happened yet when the decision is made). To guarantee error traces you need **tail-based sampling**, which the *collector* does, not X-Ray: the ADOT/OTel collector's `tail_sampling` processor buffers spans and decides *after* the trace completes, so it can keep 100% of traces containing an error or exceeding a latency threshold while down-sampling the happy path. That processor lives in §2.2's pipeline, not in these rules. Second, raising a rate to debug is fine, but **lower it again** — a forgotten `FixedRate: 1.0` on a high-traffic service is a six-figure surprise. Treat sampling rates like a feature flag: turn them up, capture what you need, turn them down.

## 2.2 — ADOT on Lambda: the extension layer

For Lambda, the ADOT collector runs as an **extension** — a layer you attach to the function that starts a tiny collector alongside your handler in the same execution environment. Your handler emits OTLP to `localhost`; the extension batches and ships to X-Ray and CloudWatch. You do not run or scale anything; it lives and dies with the function.

The wiring has three parts:

**1. Attach the ADOT layer and the auto-instrumentation wrapper.** The layer ARN is Region- and architecture-specific and versioned — confirm the current one from the ADOT docs (the structure is shown; fill in the live version):

```typescript
import * as lambda from 'aws-cdk-lib/aws-lambda';

// Region- and arch-specific; confirm the current version from the ADOT docs.
const adotLayer = lambda.LayerVersion.fromLayerVersionArn(
  this, 'AdotLayer',
  `arn:aws:lambda:${this.region}:901920570463:layer:aws-otel-python-amd64-ver-1-32-0:1`,
);

const fn = new lambda.Function(this, 'Recommend', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'app.handler',
  code: lambda.Code.fromAsset('lambda'),
  layers: [adotLayer],
  tracing: lambda.Tracing.ACTIVE,        // tells Lambda to pass through X-Ray trace context
  environment: {
    // The wrapper that auto-instruments boto3/requests and starts the collector:
    AWS_LAMBDA_EXEC_WRAPPER: '/opt/otel-instrument',
    // Point the collector at a config that exports to X-Ray + CloudWatch EMF:
    OPENTELEMETRY_COLLECTOR_CONFIG_URI: '/var/task/collector.yaml',
  },
});
```

`AWS_LAMBDA_EXEC_WRAPPER: /opt/otel-instrument` is the magic line: it injects the OTel auto-instrumentation before your handler runs, so every boto3 call (the SageMaker `invoke_endpoint`, the Bedrock `converse`) becomes a span with **zero code changes**. `tracing: ACTIVE` tells the Lambda service to propagate the X-Ray trace header so API Gateway → Lambda is one connected trace.

**2. Grant the function permission to write to X-Ray.** The execution role needs the X-Ray write actions (and CloudWatch for EMF, which it already has via the basic execution role):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
    "Resource": "*"
  }]
}
```

X-Ray's write actions do not support resource-level scoping, so `Resource: "*"` is correct *here specifically* — this is the documented exception, not laziness. The managed policy `AWSXRayDaemonWriteAccess` grants exactly this.

**3. The collector config** that the extension reads — this is where the "destination is a config line" promise becomes concrete:

```yaml
# collector.yaml — bundled with the function
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: localhost:4317   # your handler sends OTLP here

processors:
  batch: {}

exporters:
  awsxray:                          # traces -> X-Ray
    region: us-east-1
  awsemf:                           # metrics -> CloudWatch via EMF
    region: us-east-1
    namespace: MyApp/Recommend

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsxray]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsemf]
```

Read that config as three nouns: **receivers** (what comes in — OTLP from your code), **processors** (what happens in between — batching), **exporters** (where it goes — X-Ray for traces, CloudWatch EMF for metrics). To *also* ship to Jaeger or Tempo, you add one exporter and one line to the pipeline. Your Lambda code never changes. That is the entire value of the collector pattern, and it is Wednesday's exercise.

## 2.3 — ADOT on EKS: the DaemonSet with IRSA

On the serverless side the collector is an extension; on the EKS side it is a **DaemonSet** — one collector pod per node, that all the application pods on that node send OTLP to. (You can also run it as a per-app **sidecar** or use the **ADOT EKS add-on**; the DaemonSet is the common pattern and what Thursday's exercise deploys.)

The critical AWS-specific detail is **IRSA — IAM Roles for Service Accounts** (Week 5). The collector pod needs permission to write to X-Ray and CloudWatch. The wrong way is to grant those permissions to the *node's* instance role, because then *every* pod on the node inherits them. The right way is IRSA: the collector's Kubernetes ServiceAccount is annotated with an IAM role ARN, and only pods using that ServiceAccount get those credentials, scoped to exactly X-Ray and CloudWatch writes.

Create the IRSA-bound service account with `eksctl`:

```bash
eksctl create iamserviceaccount \
  --cluster c19-eks \
  --namespace observability \
  --name adot-collector \
  --attach-policy-arn arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess \
  --attach-policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy \
  --approve
```

That creates an IAM role with exactly the two managed policies the collector needs (X-Ray write, CloudWatch agent/EMF write), and wires the OIDC trust so only the `adot-collector` ServiceAccount in the `observability` namespace can assume it. Now the DaemonSet references that ServiceAccount:

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: adot-collector
  namespace: observability
spec:
  selector:
    matchLabels: { app: adot-collector }
  template:
    metadata:
      labels: { app: adot-collector }
    spec:
      serviceAccountName: adot-collector     # the IRSA-bound SA -> scoped X-Ray + CW creds
      containers:
        - name: adot-collector
          image: public.ecr.aws/aws-observability/aws-otel-collector:latest
          ports:
            - containerPort: 4317             # OTLP gRPC; app pods send here
          volumeMounts:
            - name: config
              mountPath: /etc/otel
          args: ["--config=/etc/otel/collector.yaml"]
      volumes:
        - name: config
          configMap: { name: adot-collector-config }
```

The collector config (in a ConfigMap) is the *same shape* as the Lambda one — `otlp` receiver, `awsxray` + `awsemf` exporters — but on a long-lived node you add the production-grade processors that a short-lived Lambda extension does not need. Here is the fuller pipeline the Thursday exercise deploys, with every block annotated:

```yaml
# adot-collector-config (ConfigMap data) — the EKS DaemonSet pipeline
receivers:
  otlp:
    protocols:
      grpc: { endpoint: 0.0.0.0:4317 }   # app pods on this node send OTLP here
      http: { endpoint: 0.0.0.0:4318 }
  awscontainerinsightreceiver:            # node/pod/container infra metrics (CPU, mem, net)
    collection_interval: 60s

processors:
  memory_limiter:                         # FIRST processor: shed load before the pod OOMs
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 25
  resourcedetection/eks:                  # stamp every span with cluster/node/region
    detectors: [env, eks, ec2]
    timeout: 5s
  batch:                                  # batch before export to cut API calls
    timeout: 10s
    send_batch_size: 8192
  tail_sampling:                          # decide AFTER the trace completes (see §2.1)
    decision_wait: 30s
    policies:
      - name: keep-errors
        type: status_code
        status_code: { status_codes: [ERROR] }
      - name: keep-slow
        type: latency
        latency: { threshold_ms: 1000 }
      - name: sample-rest
        type: probabilistic
        probabilistic: { sampling_percentage: 5 }

exporters:
  awsxray:                                # traces -> X-Ray
    region: us-east-1
    indexed_attributes: [tenant_id, endpoint]   # promote these OTel attrs to X-Ray annotations
  awsemf:                                 # app metrics -> CloudWatch via EMF
    region: us-east-1
    namespace: MyApp/Recommend
  awsemf/ci:                              # Container Insights metrics in their own namespace
    region: us-east-1
    namespace: ContainerInsights

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, resourcedetection/eks, tail_sampling, batch]
      exporters: [awsxray]
    metrics/app:
      receivers: [otlp]
      processors: [memory_limiter, resourcedetection/eks, batch]
      exporters: [awsemf]
    metrics/infra:
      receivers: [awscontainerinsightreceiver]
      processors: [memory_limiter, batch]
      exporters: [awsemf/ci]
```

Three things changed from the Lambda config, and each earns its place. `memory_limiter` runs **first** in every pipeline so a traffic spike sheds telemetry rather than OOM-killing the collector pod and taking your observability down at the worst moment. `resourcedetection/eks` auto-stamps `k8s.cluster.name`, `k8s.node.name`, and `cloud.region` onto every span so the X-Ray service map and your queries know *which* node a span came from — free attribution you would otherwise hand-set. `tail_sampling` is the answer to §2.1's head-sampling limitation: it buffers each trace for `decision_wait` (30 s), then keeps **100% of error traces and 100% of slow traces** and only 5% of the boring successes — exactly the bias you want, impossible with X-Ray's head-based rules alone. The `indexed_attributes` line on the exporter is where the promise from §2.1 lands: those two OTel attributes become filterable X-Ray annotations. The application pods send OTLP to the collector via `OTEL_EXPORTER_OTLP_ENDPOINT` (the node IP or a headless service), injected by the OTel auto-instrumentation. The same OTel SDK code from Lecture 1 runs unchanged in the pod; only the collector deployment differs from the Lambda case.

> **The unifying idea:** Lambda extension vs EKS DaemonSet is a *deployment topology* choice for the collector. The instrumentation in your application code — the OTel spans — is identical across both. You learn OTel once and deploy the pipe to fit the platform.

## 2.4 — Container Insights, Lambda Insights, and Application Signals

ADOT gives you *application* telemetry (the spans and metrics your code emits). You also want *infrastructure* telemetry — CPU, memory, network, disk — without instrumenting anything. That is what the "Insights" agents provide.

**Container Insights** runs an agent (the CloudWatch agent / ADOT collector with the container-insight receiver) on your ECS or EKS cluster and emits per-cluster, per-node, per-pod, per-container metrics (CPU/memory utilization, network, restart counts) plus a dashboard. On EKS you enable it as part of the same DaemonSet or via the EKS add-on. It is the "saturation" signal of the golden four — the thing that tells you the pod is OOM-killing before the errors start. It has a per-metric cost, so enable it where you need node/pod visibility, not blindly everywhere.

**Lambda Insights** is the equivalent for functions: a managed layer that emits per-invocation memory, CPU, and init-duration metrics, and a dashboard showing cold-start frequency, memory headroom, and concurrency. You attach the Lambda Insights layer (separate from the ADOT layer) and get the infrastructure view the standard Lambda metrics don't include — crucially, *memory utilization*, which tells you if you over- or under-provisioned. Attach it to functions where right-sizing or cold-start matters.

**Application Signals** is the newest and the closest AWS gets to a turnkey APM. It consumes your OTel/X-Ray data and **automatically**: discovers your services, builds a service map, computes the golden-signal metrics (latency, error rate, throughput) per service and per operation, and — the headline feature — lets you **define SLOs as first-class objects** with built-in burn-rate tracking and auto-generated dashboards. You enable it, point your instrumentation at it (it uses the same ADOT collector with the Application Signals receiver/exporter), and it gives you the SLO machinery you would otherwise hand-build. We hand-build the burn-rate alarm in §2.6 *first* — because you must understand the mechanism before you trust a button that does it for you — and the stretch goal has you compare your hand-built alarm to the one Application Signals generates.

A worked walkthrough, because "it does it for you" is worth seeing concretely. Application Signals is enabled by switching your instrumentation on: instead of (or alongside) the plain `awsxray`/`awsemf` exporters, you set `OTEL_AWS_APPLICATION_SIGNALS_ENABLED=true` and the ADOT layer/collector emits the standardized **Application Signals metrics** — `Latency`, `Error`, `Fault`, and `Availability` per service and per operation — into the `AWS/ApplicationSignals` namespace. Within a few minutes the console's **Services** tab populates with auto-discovered services (keyed by the OTel `service.name`), each row showing its golden signals, and a service map that is the X-Ray map enriched with those rolled-up metrics.

Now you create an SLO without writing any metric math. In the console: **Application Signals → SLOs → Create SLO**, then:

1. **Pick the SLI.** Choose a discovered service (`recommend`) and an operation (`POST /recommend`), then pick the signal — **Availability** (the fraction of non-fault requests) or **Latency** (the fraction under a threshold you set, e.g. 300 ms). This is the same SLI from §2.5, selected from a dropdown instead of hand-derived.
2. **Set the objective and window.** Enter `99.9%` over a **rolling 30 days**. Application Signals computes the error budget (`0.1%`) for you.
3. **Set burn-rate alarms.** It offers the multi-window burn-rate pattern as a checkbox set — you pick the burn-rate thresholds (the same `14.4 / 6 / 3 / 1` ladder) and it provisions the underlying CloudWatch alarms and metric math behind the scenes.

The same SLO is creatable as code, which is what you actually ship:

```typescript
import * as appsignals from 'aws-cdk-lib/aws-applicationsignals';

new appsignals.CfnServiceLevelObjective(this, 'RecommendAvailabilitySlo', {
  name: 'recommend-availability-99-9',
  sli: {
    sliMetric: {
      keyAttributes: { Type: 'Service', Name: 'recommend', Environment: 'eks:c19/default' },
      operationName: 'POST /recommend',
      metricType: 'AVAILABILITY',
    },
    metricThreshold: 99.9,
    comparisonOperator: 'GreaterThanOrEqualToPercent',
  },
  goal: {
    attainmentGoal: 99.9,
    warningThreshold: 30,                    // warn when 30% of the budget is consumed
    interval: { rollingInterval: { duration: 30, durationUnit: 'DAY' } },
  },
});
```

What you get for that one construct: an **SLO detail dashboard** auto-rendered with the attainment percentage, the **error budget remaining as a burn-down chart** (the budget draining over the 30-day window — green while you have room, red when you blow through), the current **burn rate**, and a built-in list of the **top contributing operations and traces** so you can pivot straight from "budget is burning" to "these five traces are why." That trace pivot is the payoff of feeding it OTel/X-Ray data: the SLO, the metric, and the offending traces are already wired together, which is the "trace > metric > log" connection of the week handed to you pre-built. The honest trade-off: Application Signals has its own per-signal and per-SLO cost, and it is opinionated about *what* an SLI is, whereas the hand-built metric-math alarm in §2.6 is free-form and free-of-extra-charge. You learn the mechanism by hand first; you reach for Application Signals when you want the dashboards and the trace correlation without building them.

## 2.5 — SLI, SLO, and the error budget

Now the conceptual heart of Friday. An alarm on a raw metric ("error rate > 1%") is a blunt instrument: it pages on a brief blip and stays quiet during a slow grind that is steadily eating your reliability. The SRE answer is to alarm on the **rate at which you are spending your error budget**, not on the instantaneous metric. To get there, three definitions in order:

**SLI — Service Level Indicator.** The *measured* number that represents user-perceived reliability. The standard form is a ratio of good events to total events. For an API: `SLI = (count of requests that returned 2xx/3xx AND under 300 ms) / (count of all requests)`. You compute it from your metrics. A *good* SLI measures what the user actually experiences, not what is easy to measure.

**SLO — Service Level Objective.** The *target* for the SLI over a window. "99.9% of requests succeed and are fast, measured over a rolling 28 days." The SLO is a promise; the number is chosen by the business, not the engineer. 99.9% is three nines; 99.99% is four. Each nine is roughly 10x harder and more expensive.

**Error budget.** `error_budget = 100% − SLO`. At a 99.9% SLO, **0.1% of requests are allowed to fail** over the window. That 0.1% is a *budget you may spend* — on risky deploys, on experiments, on the occasional bad day. The reframe that makes SLOs powerful: failures are not categorically bad; they are a budget. As long as you have budget left, ship. When the budget is exhausted, you stop shipping features and spend the next period on reliability. This turns "how reliable is reliable enough" from a religious argument into an arithmetic one.

Make the budget concrete. At 99.9% over 28 days, with (say) 10 million requests in the window, the budget is `0.001 × 10,000,000 = 10,000` failed requests. If you burn through 10,000 failures in the first day, you are wildly over budget and something is broken. If you burn 300/day, you end the month right at budget. **Burn rate** is exactly this: how fast you are spending relative to the rate that would empty the budget precisely at window end. A burn rate of `1` spends the whole budget exactly on schedule; a burn rate of `14.4` empties a 30-day budget in about 2 days; a burn rate of `1` sustained means you end the month with zero budget left.

## 2.6 — The multi-window, multi-burn-rate alarm

Here is the problem a single threshold cannot solve. You want to be **paged immediately** for a *fast* burn (a total outage eating the budget in hours) but only **ticketed** for a *slow* burn (a low-grade error rate that will exhaust the budget in weeks if ignored). One static threshold cannot do both: set it sensitive enough to catch the slow burn and it pages constantly; set it insensitive enough to ignore blips and it misses the fast burn. The Google SRE Workbook's answer — and the production standard — is **multiple alarms at different burn rates over different windows**, combined so each fires for the failure mode it is tuned to.

The canonical pattern (from the SRE Workbook, "Alerting on SLOs") for a 99.9% / 30-day budget uses pairs of windows:

| Burn rate | Long window | Short window | Budget consumed if sustained | Action |
|----------:|------------:|-------------:|------------------------------|--------|
| **14.4** | 1 hour | 5 min | ~2% of 30-day budget in 1 h | **Page** (fast burn — outage) |
| **6** | 6 hours | 30 min | ~5% in 6 h | **Page** (medium burn) |
| **3** | 1 day | 2 h | ~10% in 1 day | **Ticket** (slow burn) |
| **1** | 3 days | 6 h | ~10% in 3 days | **Ticket** (very slow burn) |

Two windows per row is the noise filter: the **long window** confirms the burn is sustained (not a 2-minute blip), and the **short window** ensures the alarm *resets quickly* once the burn stops (so you are not paged for an incident that already recovered). The alarm fires only when **both** the long-window and short-window error rates exceed the burn-rate threshold.

In CloudWatch, you express the error *ratio* with **metric math** and threshold it on the burn rate. The error rate that corresponds to a burn rate of `B` for an SLO with error budget `E` is `B × E`. For 99.9% (`E = 0.001`) and `B = 14.4`, the alarm threshold is an error rate of `0.0144` — i.e. fire when more than 1.44% of requests are failing over the window. Here is the fast-burn alarm in CDK using metric math:

```typescript
import * as cw from 'aws-cdk-lib/aws-cloudwatch';

// Good and bad request counts from API Gateway.
const total = new cw.Metric({ namespace: 'AWS/ApiGateway', metricName: 'Count',
  dimensionsMap: { ApiName: 'recommend-api' }, statistic: 'Sum' });
const errors = new cw.Metric({ namespace: 'AWS/ApiGateway', metricName: '5XXError',
  dimensionsMap: { ApiName: 'recommend-api' }, statistic: 'Sum' });

// Error ratio over the LONG window (1 hour) and SHORT window (5 min).
const burnLong = new cw.MathExpression({
  expression: 'errorsLong / totalLong',
  usingMetrics: {
    errorsLong: errors.with({ period: Duration.hours(1) }),
    totalLong: total.with({ period: Duration.hours(1) }),
  },
  period: Duration.hours(1),
});
const burnShort = new cw.MathExpression({
  expression: 'errorsShort / totalShort',
  usingMetrics: {
    errorsShort: errors.with({ period: Duration.minutes(5) }),
    totalShort: total.with({ period: Duration.minutes(5) }),
  },
  period: Duration.minutes(5),
});

// SLO = 99.9% -> error budget E = 0.001. Burn rate 14.4 -> threshold = 14.4 * 0.001 = 0.0144.
const FAST_BURN_THRESHOLD = 14.4 * 0.001;

const fastLong = new cw.Alarm(this, 'FastBurnLong', {
  metric: burnLong, threshold: FAST_BURN_THRESHOLD, evaluationPeriods: 1,
  comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
  treatMissingData: cw.TreatMissingData.NOT_BREACHING,
});
const fastShort = new cw.Alarm(this, 'FastBurnShort', {
  metric: burnShort, threshold: FAST_BURN_THRESHOLD, evaluationPeriods: 1,
  comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
  treatMissingData: cw.TreatMissingData.NOT_BREACHING,
});

// Page only when BOTH windows agree the burn is fast and sustained.
new cw.CompositeAlarm(this, 'FastBurnPage', {
  alarmRule: cw.AlarmRule.allOf(
    cw.AlarmRule.fromAlarm(fastLong, cw.AlarmState.ALARM),
    cw.AlarmRule.fromAlarm(fastShort, cw.AlarmState.ALARM),
  ),
  compositeAlarmName: 'recommend-slo-fast-burn',
});
```

Rather than copy-paste that block four times, factor the window pair into a helper and drive it from the SRE-Workbook table, routing each row to the right SNS topic. This is the shape you actually ship for Friday:

```typescript
import * as cw from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as sns from 'aws-cdk-lib/aws-sns';
import { Duration } from 'aws-cdk-lib';

const pageTopic = new sns.Topic(this, 'SloPage');     // -> PagerDuty
const ticketTopic = new sns.Topic(this, 'SloTicket'); // -> Jira / business hours

const E = 0.001; // 99.9% SLO -> error budget

// Build one burn-rate metric (errors/total) over an arbitrary window.
const burnOver = (window: Duration) => new cw.MathExpression({
  expression: 'errs / tot',
  usingMetrics: {
    errs: errors.with({ period: window }),
    tot: total.with({ period: window }),
  },
  period: window,
});

// One composite per row: fire only when BOTH windows exceed B * E.
function burnRow(id: string, burn: number, long: Duration, short: Duration, topic: sns.Topic) {
  const threshold = burn * E;
  const mk = (suffix: string, w: Duration) => new cw.Alarm(this, `${id}${suffix}`, {
    metric: burnOver(w), threshold, evaluationPeriods: 1,
    comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
    treatMissingData: cw.TreatMissingData.NOT_BREACHING,
  });
  const composite = new cw.CompositeAlarm(this, `${id}Composite`, {
    compositeAlarmName: `recommend-slo-${id}`,
    alarmRule: cw.AlarmRule.allOf(
      cw.AlarmRule.fromAlarm(mk('Long', long), cw.AlarmState.ALARM),
      cw.AlarmRule.fromAlarm(mk('Short', short), cw.AlarmState.ALARM),
    ),
  });
  composite.addAlarmAction(new cwActions.SnsAction(topic));
}

// The four-row SRE-Workbook ladder for a 99.9% / 30-day budget:
burnRow('fast',   14.4, Duration.hours(1), Duration.minutes(5),  pageTopic);   // page
burnRow('medium', 6,    Duration.hours(6), Duration.minutes(30), pageTopic);   // page
burnRow('slow',   3,    Duration.days(1),  Duration.hours(2),    ticketTopic); // ticket
burnRow('creep',  1,    Duration.days(3),  Duration.hours(6),    ticketTopic); // ticket
```

The result: a fast outage pages you within minutes (the 5-minute short window plus the 1-hour confirmation, which in practice trips quickly when the rate is high), the medium burn also pages, while a slow 0.3% error grind opens a ticket you handle in business hours and a very slow creep opens a lower-urgency ticket. **That asymmetry — page fast, ticket slow — is the entire point, and a single threshold cannot express it.** This is the load-bearing pattern of Friday's challenge.

A note on why the composite-of-two-windows: the long window prevents the slow-burn alarm from firing on a brief spike (it requires the elevated rate to persist), and the short window makes the alarm *clear* fast once the incident is over (without it, a 1-hour window keeps the alarm red for an hour after recovery, paging you about a resolved incident). Both windows, AND-ed, give you "fire when sustained, clear when recovered."

## 2.7 — The synthetic outage: proving the alarm

An alarm you have never seen fire is a hope, not a control. Friday's challenge ends by *deliberately breaking* the service and watching the alarm transition. The cleanest synthetic outage: deploy a config flag (or an environment variable) that makes the Lambda return 5xx for a controlled fraction of requests, drive load with the canary plus a small request generator, and watch:

1. The **error-ratio metric** climb on the dashboard.
2. The **short-window alarm** go `ALARM` first (it reacts in ~5 minutes).
3. The **long-window alarm** confirm, flipping the **composite** to `ALARM` and firing the SNS page.
4. After you flip the flag back, the **short window** clears within minutes, dropping the composite back to `OK` — *not* an hour later.

You record the timestamps and compute: how long from injection to page (the **detection time**), and how long from fix to clear (the **recovery confirmation time**). A well-tuned fast-burn alarm detects a hard outage in single-digit minutes and clears within minutes of recovery. If yours pages an hour late or stays red long after recovery, your windows are wrong — and now you know how to fix them. That measured detection-and-recovery loop is the challenge deliverable.

## 2.8 — Open-source comparators (what you traded away)

- **Prometheus + Alertmanager** replaces CloudWatch Metrics + Alarms: pull-based scraping, PromQL (far more expressive than CloudWatch metric math for ratio/burn-rate queries — `sum(rate(errors[1h])) / sum(rate(total[1h]))` is exactly a burn-rate query), and Alertmanager's routing/inhibition for the page-vs-ticket split. The burn-rate alarm you hand-built in metric math is a one-line PromQL recording rule. You give up the managed-ness and gain expressiveness and portability. **Amazon Managed Prometheus** is AWS hosting this for you, and the ADOT collector can `remotewrite` to it instead of (or alongside) CloudWatch.
- **Jaeger / Grafana Tempo** replaces X-Ray as the trace backend: take the *same* OTLP from your *same* ADOT collector and store traces yourself. Tempo on S3 is dramatically cheaper at high trace volume than X-Ray's per-trace pricing. You give up the AWS-native service-map integration and gain cost control.
- **Grafana** replaces CloudWatch dashboards, reading X-Ray, CloudWatch, Prometheus, Tempo, and Loki side by side in one pane. **Amazon Managed Grafana** is the hosted version.
- **Loki** replaces CloudWatch Logs: label-indexed log aggregation, cheap on object storage, queried with LogQL.

The pattern, identical to every week of C19: the **instrumentation does not change** — it is OpenTelemetry either way. Only the **collector's exporter** changes. You can run the AWS-native backend today and migrate to the open stack by editing one config file, never touching application code. That portability is *why* we taught OTel-and-ADOT rather than the X-Ray SDK. Internalize it: instrument once, export anywhere.

## 2.9 — What you should be able to do now

- Read an X-Ray service map and trace, find the slow/failing span, and pivot to the metric.
- Explain segments, subsegments, annotations (indexed) vs metadata (not), and sampling.
- Configure the ADOT collector as a Lambda extension (`AWS_LAMBDA_EXEC_WRAPPER`, layer, config) and as an EKS DaemonSet with IRSA.
- Read a collector config as receivers → processors → exporters, and add a second exporter without touching app code.
- Explain what Container Insights, Lambda Insights, and Application Signals each add on top of ADOT.
- Define SLI, SLO, and error budget, and compute a budget in failed-requests.
- Build a multi-window, multi-burn-rate alarm in CloudWatch metric math, route fast burns to page and slow burns to ticket, and explain why two windows.
- Fire a synthetic outage and measure detection and recovery-confirmation time.

## 2.10 — The challenge that goes with this lecture

**Challenge 1 — Burn-rate SLO and a synthetic outage.** Define a 99.9% SLO on your instrumented API, build the multi-window multi-burn-rate alarm, fire a controlled synthetic outage, and prove the alarm pages at the right moment and clears on recovery — with timestamps. The acceptance criteria are in `challenges/challenge-01-burn-rate-slo-and-synthetic-outage.md`. Bring real numbers: detection time and recovery-confirmation time, measured.
