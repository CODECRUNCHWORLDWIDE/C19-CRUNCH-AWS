# Week 12 — Resources

Everything here is free to read. AWS documentation is open. The re:Invent talks are on YouTube. The OpenTelemetry and ADOT projects are public on GitHub. The Google SRE books are free online. We link a few paid books at the chapter level only where the free material falls short.

A scheduling note that saves a day: **the ADOT Lambda layer ARN is Region- and architecture-specific**, and the layer version changes. Confirm the current ARN for your Region (`x86_64` vs `arm64`) from the ADOT docs before Wednesday — do not paste a stale version from memory. The lecture notes use a placeholder ARN with the structure spelled out; you fill in the live version number.

## Required reading (work it into your week)

- **The three pillars / OpenTelemetry "Observability primer"** — what traces, metrics, and logs each answer:
  <https://opentelemetry.io/docs/concepts/observability-primer/>
- **Google SRE Workbook — "Alerting on SLOs"** — the multi-window, multi-burn-rate alarm pattern is straight from here. **Read this chapter; it is the load-bearing idea of Friday:**
  <https://sre.google/workbook/alerting-on-slos/>
- **CloudWatch Logs Insights query syntax** — the query language you will use all week:
  <https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html>
- **CloudWatch Embedded Metric Format (EMF)** — how to emit custom metrics from a log line for nearly free:
  <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html>
- **AWS X-Ray concepts** — segments, subsegments, the service map, sampling:
  <https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html>
- **AWS Distro for OpenTelemetry (ADOT) — getting started**:
  <https://aws-otel.github.io/docs/introduction>
- **CloudWatch Application Signals** — auto-discovered SLOs and service maps from OTel/X-Ray:
  <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Monitoring-Sections.html>

## Pricing pages (read these as dollars, not docs)

Observability has a real bill, and the most common shock is "we logged everything forever at high resolution." Open these and write the figures into your cost report:

- **CloudWatch pricing** — log ingestion per GB, log storage per GB-month, custom-metric per metric-month, `PutMetricData` API cost, dashboards, Logs Insights per-GB-scanned, alarms (standard vs high-resolution):
  <https://aws.amazon.com/cloudwatch/pricing/>
- **X-Ray pricing** — per-trace recorded, per-trace retrieved, per-trace scanned:
  <https://aws.amazon.com/xray/pricing/>
- **CloudWatch Synthetics pricing** — per canary run:
  <https://aws.amazon.com/cloudwatch/pricing/>  (Synthetics section)
- **CloudWatch RUM pricing** — per 100,000 events:
  <https://aws.amazon.com/cloudwatch/pricing/>  (RUM section)
- **Application Signals pricing** — per service-hour monitored and per SLO:
  <https://aws.amazon.com/cloudwatch/pricing/>  (Application Signals section)

The single most important pricing fact this week: **CloudWatch Logs has no default retention — log groups keep data forever unless you set a retention policy.** Every log group you create should get a retention in the same breath. The second: **`PutMetricData` is billed per call**, which is why EMF (metrics embedded in a log line you were already paying to ingest) is the production default for high-cardinality custom metrics.

## AWS docs you will reach for during the build

- **CloudWatch metric filters** (turn a log pattern into a metric): <https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/MonitoringLogData.html>
- **CloudWatch composite alarms**: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Create_Composite_Alarm.html>
- **CloudWatch anomaly detection**: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Anomaly_Detection.html>
- **CloudWatch metric math** (the language burn-rate alarms are written in): <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html>
- **ADOT Collector configuration** (receivers / processors / exporters): <https://aws-otel.github.io/docs/getting-started/collector>
- **ADOT on Lambda** (the managed layer + `AWS_LAMBDA_EXEC_WRAPPER`): <https://aws-otel.github.io/docs/getting-started/lambda>
- **ADOT on EKS** (DaemonSet, sidecar, the EKS add-on): <https://aws-otel.github.io/docs/getting-started/adot-eks-add-on>
- **The `awsxray` exporter** and **`awsemf` exporter** docs (where your collector sends data):
  <https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter/awsxrayexporter>
  <https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter/awsemfexporter>
- **Container Insights** (ECS/EKS infra metrics): <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ContainerInsights.html>
- **Lambda Insights** (per-function infra metrics, the managed layer): <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Lambda-Insights.html>
- **AWS Lambda Powertools (Python)** — `Logger`, `Metrics` (EMF), `Tracer` (X-Ray): <https://docs.powertools.aws.dev/lambda/python/latest/>
- **CloudWatch Synthetics canary blueprints**: <https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Synthetics_Canaries.html>

## CDK / IaC reference

- **AWS CDK — `aws-cloudwatch`** (alarms, dashboards, metric math, anomaly detection):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch-readme.html>
- **AWS CDK — `aws-synthetics-alpha`** (canary L2 construct; still alpha in 2026):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/@aws-cdk_aws-synthetics-alpha-readme.html>
- **AWS CDK — `aws-logs`** (log groups with retention, metric filters, subscription filters):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs-readme.html>
- **AWS CDK — `aws-applicationsignals-alpha`** (SLOs and service-level objectives as code):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_applicationsignals_alpha-readme.html>
- **CloudFormation — `AWS::CloudWatch::Alarm`** (when you need the raw metric-math `Metrics` array verbatim):
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-cw-alarm.html>
- **OpenTofu / Terraform AWS provider** — `aws_cloudwatch_metric_alarm`, `aws_synthetics_canary`, `aws_xray_sampling_rule`:
  <https://search.opentofu.org/provider/hashicorp/aws/latest>

## re:Invent and AWS talks (free, on YouTube)

- **"Observability the open-source way on AWS"** — the OpenTelemetry/ADOT/Managed-Prometheus/Managed-Grafana story (annual; pick the latest COP-track session). Search the AWS Events channel:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Building an effective observability strategy"** — CloudWatch, X-Ray, Application Signals, and the three signals framing:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Instrumenting applications with OpenTelemetry and ADOT"** — the hands-on collector talk:
  <https://www.youtube.com/@AWSEventsChannel>

*(re:Invent session IDs change yearly; the channel is stable. Filter by the most recent year and the COP / DOP tracks.)*

## Open-source comparators (know what you traded away)

- **OpenTelemetry Collector (upstream)** — the CNCF collector ADOT is a distribution of. Running it yourself gives you exporters AWS doesn't ship and zero AWS coupling:
  <https://opentelemetry.io/docs/collector/>
- **Prometheus** — the de-facto open metrics system: pull-based scraping, PromQL, recording/alerting rules. The open alternative to CloudWatch Metrics + Alarms:
  <https://prometheus.io/docs/introduction/overview/>
- **Grafana** — the dashboard layer that reads Prometheus, X-Ray, CloudWatch, Tempo, Loki, and more. Amazon Managed Grafana is AWS hosting this for you:
  <https://grafana.com/docs/grafana/latest/>
- **Jaeger** — open distributed tracing (the CNCF tracer); the self-hosted alternative to X-Ray:
  <https://www.jaegertracing.io/docs/latest/>
- **Grafana Tempo** — a high-scale trace backend that takes OTLP directly and is cheap to run on object storage:
  <https://grafana.com/docs/tempo/latest/>
- **Grafana Loki** — log aggregation that indexes labels not full text, the open alternative to CloudWatch Logs:
  <https://grafana.com/docs/loki/latest/>

The pattern: the *instrumentation* (OpenTelemetry SDKs in your code) is identical whether you ship to AWS or to this open stack. Only the **exporter** in the collector config changes. That is the entire point of OpenTelemetry — and the reason this week teaches OTel, not the X-Ray SDK directly.

## Books (chapter-level)

- **Google SRE Book and SRE Workbook** — free online. The SLO/SLI/error-budget chapters are the canonical source and the basis of Friday's burn-rate alarm:
  <https://sre.google/books/>
- **"Observability Engineering" (Majors, Fong-Jones, Miranda)** — the case for high-cardinality, high-dimensionality events and "trace > metric > log." Read Chapters 1–3; they reframe how you think about this week.
- **"Distributed Systems Observability" (Cindy Sridharan)** — a free short O'Reilly report that is the best 60-minute intro to the three signals that exists:
  <https://www.oreilly.com/library/view/distributed-systems-observability/9781492033431/>

## Tools you'll use this week

- **AWS CLI v2** — `aws logs start-query`, `aws cloudwatch put-metric-alarm`, `aws synthetics start-canary`, `aws xray get-service-graph`. Verify with `aws --version` (want `aws-cli/2.x`).
- **Python 3.12+** with `boto3`, `aws-lambda-powertools`, `opentelemetry-distro`, `opentelemetry-sdk`. A `requirements.txt` ships with each exercise.
- **AWS CDK v2** (TypeScript) — `npx cdk deploy`. The mini-project's infra is CDK.
- **`kubectl`** and **`helm`** — to deploy the ADOT collector DaemonSet on EKS (Thursday).
- **`eksctl`** — to create the IRSA service account the DaemonSet assumes.
- **`jq`** — for slicing the JSON the CloudWatch and X-Ray CLIs return.

## The Claude / Bedrock note

If your Week-11 inference path calls **Anthropic Claude** through Bedrock, you will instrument *that call* this week so its latency appears as a span in your trace and its token usage as a metric. The Bedrock model IDs and the Converse-vs-InvokeModel request shapes change often; confirm the current Haiku model ID from the Bedrock console before you wire the span attributes. The lecture notes reuse Week 11's worked example `us.anthropic.claude-3-5-haiku-20241022-v1:0`; verify against your account's available models, because availability is Region- and account-specific.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Trace** | The end-to-end path of one request across all services, as a tree of spans with timings. |
| **Span** | One unit of work in a trace (one service call, one DB query). Has a start, end, parent, and attributes. |
| **Metric** | A number sampled over time (latency p99, error count). Cheap to store, aggregates well, no per-request detail. |
| **Log** | A timestamped text/structured record of one event. Highest detail, highest volume, highest cost. |
| **EMF** | Embedded Metric Format — a JSON log line CloudWatch parses into metrics. Custom metrics for the price of a log. |
| **Metric filter** | A pattern over a log group that increments a CloudWatch metric when a line matches. |
| **Logs Insights** | CloudWatch's query language over log groups. You pay per GB scanned, like Athena. |
| **Composite alarm** | An alarm whose state is a boolean expression over other alarms. Used to suppress noise. |
| **Anomaly detection** | A CloudWatch band that learns a metric's normal range and alarms on deviation, no fixed threshold. |
| **X-Ray** | AWS's managed tracing backend: ingests segments, renders a service map and traces. |
| **OpenTelemetry (OTel)** | The CNCF vendor-neutral standard for generating traces/metrics/logs. The instrumentation in your code. |
| **ADOT** | AWS Distro for OpenTelemetry — AWS's supported build of the OTel Collector with AWS exporters. |
| **Collector** | The agent that receives telemetry (OTLP), processes it, and exports it to a backend (X-Ray, CloudWatch). |
| **IRSA** | IAM Roles for Service Accounts — how the EKS ADOT pod gets scoped AWS credentials, not node creds. |
| **Container Insights** | The managed agent emitting ECS/EKS infrastructure metrics (CPU, memory, network) to CloudWatch. |
| **Application Signals** | The AWS layer that auto-discovers services from OTel/X-Ray data and builds SLOs + a service map. |
| **SLI** | Service Level Indicator — the measured number (e.g. % of requests under 300 ms and 2xx/3xx). |
| **SLO** | Service Level Objective — the target for the SLI (e.g. 99.9% of requests succeed over 28 days). |
| **Error budget** | `100% − SLO`. At 99.9% you may "spend" 0.1% of requests failing. When it's gone, you stop shipping. |
| **Burn rate** | How fast you are spending the error budget, relative to the rate that would exhaust it exactly at period end. |

---

*If a link 404s, please open an issue so we can replace it.*
