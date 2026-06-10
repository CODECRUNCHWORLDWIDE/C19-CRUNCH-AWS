# Week 12 — Observability: CloudWatch, X-Ray, OpenTelemetry, ADOT

Welcome to the week that turns "it's probably fine" into "here is the trace, here is the alarm, here is the error budget we have left." By Friday you will have instrumented the Week-10 event pipeline and the Week-11 inference path with OpenTelemetry, run the ADOT (AWS Distro for OpenTelemetry) collector as a DaemonSet on EKS and as a Lambda extension on the serverless side, sent traces to X-Ray and metrics to CloudWatch, built a multi-window burn-rate alarm on a 99.9% availability SLO, and triggered a synthetic outage to watch that alarm fire at exactly the right moment — not too early (alert fatigue), not too late (you already missed the budget).

This is Phase 4's first week, and it is the hinge of the whole course. Everything before this week *built* a system. Everything after this week assumes you can *see* it. The capstone (Weeks 13–15) requires burn-rate alarms, a Synthetics canary, distributed traces, and dashboards-as-code; this week is where you earn all four. The recurring conviction in the syllabus is stated plainly: **observability comes before "doing more services."** You do not get to add the next service until you can observe the ones you have.

We teach the three telemetry signals in the order a senior engineer actually reaches for them during an incident: **trace > metric > log**. A trace tells you *where* the latency or the error is across a dozen services. A metric tells you *how bad* and *for how long*. A log tells you *exactly what happened* on the one request you drilled into. Junior engineers grep logs first and drown; seniors open the trace, find the slow span, pivot to the metric that quantifies it, then read the one relevant log line. The whole week is built to make you the second kind of engineer.

We are vendor-aware, not vendor-loyal. The instrumentation we write is **OpenTelemetry** — the CNCF vendor-neutral standard — precisely so that the day you leave AWS, your traces still flow. ADOT is just AWS's supported distribution of the OTel collector; the SDK calls in your code are pure OTel. The open-source comparators this week are real and worth knowing: **Prometheus + Grafana** for metrics and dashboards, **Jaeger** and **Tempo** for traces, **Loki** for logs, and **the upstream OpenTelemetry Collector** that ADOT is built from. We name them so you know what you traded away when you reached for the managed backend.

The artifacts you build this week are not throwaway. The instrumented pipeline becomes the **capstone's observability layer**; the burn-rate alarms and the canary become the **capstone's alarm catalog**; the CloudWatch dashboard becomes the **capstone's dashboards-as-code**. Build them to keep.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the three telemetry signals — traces, metrics, logs — and the "trace > metric > log" triage order, and draw the three-tier dashboard for the capstone.
- **Navigate** CloudWatch Logs: log groups, retention, metric filters, and Logs Insights queries that turn a log group into a queryable dataset.
- **Emit** custom metrics cheaply with the **Embedded Metric Format (EMF)** instead of paying per `PutMetricData` call, and explain why EMF is the production default.
- **Build** CloudWatch alarms — static-threshold, **composite**, and **anomaly-detection** — and explain when each is right.
- **Stand up** a CloudWatch **Synthetics canary** against a public endpoint and a **CloudWatch RUM** app monitor, and reason about when to add **Evidently** for feature flags and A/B.
- **Instrument** a service with **OpenTelemetry** SDKs (Python) producing traces and metrics, and explain auto- vs manual instrumentation.
- **Run** the **ADOT collector** two ways: as a DaemonSet on EKS (with IRSA) and as a Lambda extension layer, and route traces to X-Ray and metrics to CloudWatch.
- **Read** an X-Ray service map and a trace, find the slow or failing span, and pivot from trace to metric.
- **Enable** Container Insights and Lambda Insights, and explain what CloudWatch **Application Signals** gives you on top (auto-discovered SLOs and service maps from OTel data).
- **Define** an SLI and an SLO, compute an **error budget**, and build a **multi-window, multi-burn-rate** alarm that pages fast on a fast burn and slow on a slow burn.

## Prerequisites

This week assumes you have completed Weeks 1–11 of C19, or have equivalent AWS fluency. Specifically:

- You can deploy a CDK stack (TypeScript) from zero and read the synthesized CloudFormation. (Week 3.)
- You have a running EKS cluster, or can stand one up, with **IRSA** configured for pod-scoped IAM. (Week 5.) The ADOT DaemonSet uses IRSA, not node-role credentials.
- You can write a Lambda in Python with a least-privilege execution role. (Weeks 2, 7.)
- You built the **Week-10 event pipeline** (API Gateway → Lambda → EventBridge → SQS / Step Functions / Firehose) and the **Week-11 inference path** (SageMaker endpoint + Bedrock from Lambda). **This week instruments both.** If you skipped them, the exercises include a minimal Lambda + API to instrument so you are not blocked.
- Comfort reading an IAM policy and a CDK construct, and turning a CloudWatch metric math expression into a number.

You do **not** need prior observability tooling experience. If you have run Prometheus or Datadog before, the mental model transfers directly; if you have not, we build it from the signal up.

## Topics covered

- **The three signals:** traces, metrics, logs — what each answers, the triage order, and the three-tier dashboard.
- **CloudWatch Logs:** log groups, retention policies (and the "logs are forever by default = a silent bill" trap), **metric filters** to turn a log pattern into a metric, and **Logs Insights** query language.
- **CloudWatch Metrics:** namespaces, dimensions, resolution (standard vs high-resolution), the cost of `PutMetricData`, and the **Embedded Metric Format (EMF)** that makes custom metrics nearly free.
- **CloudWatch Alarms:** static thresholds, **composite alarms** (AND/OR over child alarms to kill noise), **anomaly-detection** bands, `M out of N` evaluation, and `treatMissingData` — the setting that decides whether a silent service is "OK" or "ALARM."
- **Synthetics, RUM, Evidently:** canaries (blueprints, the puppeteer/selenium runtime), real-user monitoring, and feature-flag/experiment evaluation — and where each belongs.
- **X-Ray:** segments, subsegments, the service map, trace sampling, annotations vs metadata, and the relationship between X-Ray and OpenTelemetry.
- **OpenTelemetry:** the data model (spans, span context, baggage, resource attributes), the SDK vs the API vs the Collector, auto-instrumentation, and the OTLP wire protocol.
- **ADOT:** the AWS-supported OTel Collector distribution — receivers, processors, exporters; running it as an EKS DaemonSet (with IRSA), as a sidecar, and as a Lambda extension layer; the `awsxray` and `awsemf` exporters.
- **Container Insights & Lambda Insights:** the managed agents that emit infrastructure metrics for ECS/EKS and Lambda, and what they cost.
- **Application Signals:** the 2024+ layer that auto-discovers services from OTel/X-Ray data, builds SLOs, and renders a service map — the closest AWS gets to a turnkey APM.
- **SLO/SLI thinking:** error budgets, the **multi-window multi-burn-rate** alarm pattern (the Google SRE workbook approach), and why a single static threshold pages you at 3 a.m. for nothing.
- **Open-source comparators:** Prometheus + Grafana, Jaeger/Tempo, Loki, and the upstream OTel Collector — what each replaces and what you give up.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target.

| Day       | Focus                                                            | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Three signals; CloudWatch Logs/Insights/EMF/alarms (Lecture 1)   |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | CloudWatch Logs + EMF + alarms hands-on (Exercise 1)             |    1h    |    2.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Wednesday | OTel + ADOT on Lambda; X-Ray traces (Exercise 2)                 |    1h    |    2.5h   |     1h     |    0.5h   |   0.5h   |     0h       |    0.5h    |     6h      |
| Thursday  | ADOT DaemonSet on EKS; Container/Lambda Insights (Exercise 3)    |    2h    |    2h     |     0h     |    0.5h   |   0.5h   |     1h       |    0h      |     6h      |
| Friday    | SLO/SLI; burn-rate alarms; synthetic outage (Challenge 1)        |    0h    |    0h     |     2.5h   |    0.5h   |   0.5h   |     2h       |    0h      |     5.5h    |
| Saturday  | Mini-project deep work                                           |    0h    |    0h     |     0h     |    0h     |   0.5h   |     3.5h     |    0h      |     4h      |
| Sunday    | Quiz, cost report, review                                        |    0h    |    0h     |     0h     |    1h     |   1h     |     0.5h     |    0h      |     2.5h    |
| **Total** |                                                                  | **6h**   | **8.5h**  | **3.5h**   | **3.5h**  | **5h**   | **7.5h**     | **1.5h**   | **35.5h**   |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated AWS docs, talks, the Google SRE workbook, and open-source comparators, current to 2026 |
| [lecture-notes/01-three-signals-cloudwatch-and-otel.md](./lecture-notes/01-three-signals-cloudwatch-and-otel.md) | The three signals and triage order; CloudWatch Logs/Metrics/EMF/Alarms; why OpenTelemetry is the instrumentation, ADOT the pipe |
| [lecture-notes/02-xray-adot-and-burn-rate-slos.md](./lecture-notes/02-xray-adot-and-burn-rate-slos.md) | X-Ray service maps; ADOT on Lambda and EKS; Application Signals; SLO/SLI and multi-window burn-rate alarms |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-cloudwatch-logs-emf-alarms.md](./exercises/exercise-01-cloudwatch-logs-emf-alarms.md) | Structured logs, a Logs Insights query, an EMF custom metric, a metric-filter, and an alarm |
| [exercises/exercise-02-adot-lambda-xray.py](./exercises/exercise-02-adot-lambda-xray.py) | Instrument a Lambda with OTel + the ADOT extension, send traces to X-Ray, read the service map |
| [exercises/exercise-03-adot-eks-daemonset.py](./exercises/exercise-03-adot-eks-daemonset.py) | Deploy the ADOT collector as an EKS DaemonSet with IRSA; route traces to X-Ray, metrics to CloudWatch |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-burn-rate-slo-and-synthetic-outage.md](./challenges/challenge-01-burn-rate-slo-and-synthetic-outage.md) | Build a multi-window burn-rate alarm on a 99.9% SLO, fire a synthetic outage, prove it pages at the right moment |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the "Observability Layer" — feeds the capstone |
| [quiz.md](./quiz.md) | 14 questions with an answer key |
| [homework.md](./homework.md) | Concrete homework with deliverables and a rubric |

## The "trace > metric > log" promise

C19's recurring marker this week is the triage order. When an alarm fires, the senior move is:

```
1. Open the TRACE   → which service / span is slow or erroring? (X-Ray service map)
2. Open the METRIC  → how bad, how long, is it still happening? (CloudWatch dashboard)
3. Open the LOG     → what exactly happened on this one request? (Logs Insights, filtered by trace_id)
```

If your instinct under pressure is still "grep the logs," you are not done. The point of this week is to wire `trace_id` into every log line so that step 3 is a one-click pivot from step 1 — and to make the trace exist at all, so step 1 is possible. By Friday you should be able to take an alarm notification and reach the root-cause log line in under a minute, every time, because the signals are connected.

## Stretch goals

If you finish the regular work early and want to push further:

- Stand up **Grafana** (Amazon Managed Grafana or self-hosted) pointed at the **X-Ray** and **CloudWatch** data sources, and rebuild your three-tier dashboard there. Compare the developer experience and the cost against native CloudWatch dashboards.
- Add a second exporter to your ADOT collector config that *also* ships traces to a self-hosted **Jaeger** (or **Tempo**) via OTLP, proving the "instrument once, export anywhere" promise of OpenTelemetry.
- Turn on **CloudWatch Application Signals** for the instrumented services and let it auto-discover the SLO you hand-built; compare its generated burn-rate alarm to yours.
- Add **trace context propagation** across the EventBridge boundary so a single trace spans API Gateway → Lambda → EventBridge → the downstream consumer (the hard part is propagating the `traceparent` through an asynchronous event).
- Replace the CloudWatch metrics backend in your ADOT config with a **Prometheus remote-write** exporter to **Amazon Managed Prometheus**, and query it with PromQL.

## Up next

Week 13 — Security Stack & Multi-Region DR, where the **capstone build begins**. The capstone spec requires the exact four artifacts you build this week: burn-rate alarms on a 99.9% SLO, a Synthetics canary, distributed traces via ADOT, and CloudWatch dashboards-as-code. Push your instrumented pipeline and your alarm catalog before you move on; Week 13 imports them into the capstone monorepo and assumes they exist.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
