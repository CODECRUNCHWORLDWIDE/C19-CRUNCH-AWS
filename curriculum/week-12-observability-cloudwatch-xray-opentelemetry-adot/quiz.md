# Week 12 — Quiz

Fourteen questions. Take it with your lecture notes closed. Aim for 11/14 before moving to Week 13. Answer key at the bottom — don't peek.

---

**Q1.** During an incident, a senior engineer reaches for the three signals in which order?

- A) Log → metric → trace.
- B) Metric → log → trace.
- C) Trace → metric → log.
- D) Trace → log → metric.

---

**Q2.** You create a CloudWatch log group and never set a retention policy. What happens?

- A) The data is deleted after 30 days automatically.
- B) The data is kept indefinitely and billed for storage every month, forever.
- C) The log group rejects new events until retention is configured.
- D) CloudWatch defaults retention to 7 days.

---

**Q3.** You want to emit a per-request custom metric without paying a per-call API charge or adding a network round-trip on the request path. You should use:

- A) `PutMetricData` on every request.
- B) The Embedded Metric Format (EMF) — emit the metric as a structured log line.
- C) A CloudWatch dashboard.
- D) An X-Ray annotation.

---

**Q4.** A service crashes so completely that it stops emitting its error-count metric. Your alarm has `treatMissingData: NOT_BREACHING`. What does the alarm do?

- A) Fires `ALARM`, correctly catching the outage.
- B) Stays `OK` — the dead service looks healthy, and you are not paged.
- C) Goes to `INSUFFICIENT_DATA` and pages.
- D) Automatically restarts the service.

---

**Q5.** Ten alarms all fire from one root cause (a shared database is down) and your on-call drowns in pages. The right tool to send one meaningful page instead of ten is:

- A) Anomaly detection.
- B) A composite alarm with a boolean rule over the child alarms.
- C) Raising every alarm's threshold.
- D) Deleting nine of the alarms.

---

**Q6.** Why does this course instrument application code with OpenTelemetry instead of the AWS X-Ray SDK directly?

- A) The X-Ray SDK is deprecated.
- B) OpenTelemetry is vendor-neutral — the backend (X-Ray, Jaeger, Tempo, Datadog) is the collector's exporter config, so app code never changes when you switch backends.
- C) OpenTelemetry is faster at runtime.
- D) X-Ray cannot trace Lambda functions.

---

**Q7.** In the ADOT-on-Lambda setup, what does `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument` do?

- A) Encrypts the function's environment variables.
- B) Injects the OTel auto-instrumentation (so boto3/HTTP calls become spans) and starts the in-process collector, with no code changes.
- C) Increases the function's memory.
- D) Disables X-Ray to save cost.

---

**Q8.** The ADOT collector on EKS should get its X-Ray and CloudWatch write permissions via:

- A) Hard-coded access keys in the pod's environment.
- B) The EC2 node instance role, shared by all pods on the node.
- C) IRSA — an IAM role bound to the collector's ServiceAccount, scoping creds to that pod only.
- D) The cluster's admin kubeconfig.

---

**Q9.** A collector config has `receivers`, `processors`, and `exporters`. To *also* send your existing traces to a self-hosted Jaeger without touching application code, you:

- A) Rewrite the application to use the Jaeger SDK.
- B) Add a Jaeger exporter and add it to the traces pipeline — one config change, no app change.
- C) Deploy a second copy of every service.
- D) Switch from OpenTelemetry to the X-Ray SDK.

---

**Q10.** Your SLO is 99.9% availability over 28 days, and the window sees 10,000,000 requests. How many failed requests is your error budget?

- A) 100 requests.
- B) 1,000 requests.
- C) 10,000 requests.
- D) 100,000 requests.

---

**Q11.** Why does a burn-rate alarm use *two* windows (e.g. a 1-hour long window AND a 5-minute short window) rather than one?

- A) To cost less.
- B) The long window confirms the burn is sustained (not a blip); the short window makes the alarm clear quickly once the burn stops.
- C) AWS requires exactly two windows.
- D) One window is for traces and the other for metrics.

---

**Q12.** For a 99.9% SLO (error budget 0.001), the fast-burn alarm uses burn rate 14.4. What error-ratio threshold does that correspond to?

- A) 0.0001 (0.01%).
- B) 0.0144 (1.44%).
- C) 0.144 (14.4%).
- D) 0.001 (0.1%).

---

**Q13.** A CloudWatch Synthetics canary's success metric has its alarm set to `treatMissingData: BREACHING`. Why is that the right choice here (unlike the error-count alarm in Exercise 1)?

- A) Canaries are more expensive, so they need stricter alarms.
- B) A canary that stopped reporting is itself a symptom — silence should page, not look healthy.
- C) Canaries cannot use `NOT_BREACHING`.
- D) It makes the canary run more often.

---

**Q14.** What does CloudWatch **Application Signals** add on top of raw ADOT/X-Ray instrumentation?

- A) Nothing; it is a rebrand of X-Ray.
- B) It auto-discovers services from the OTel/X-Ray data, builds a service map and golden-signal metrics, and lets you define SLOs as first-class objects with built-in burn-rate tracking.
- C) It replaces the need to instrument your code at all.
- D) It is a log storage tier cheaper than CloudWatch Logs.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **C** — Trace (WHERE — which span), then metric (HOW BAD — how many, how long), then the one log line (WHAT EXACTLY). Grepping logs first is the junior anti-pattern.
2. **B** — Log groups have no default retention; data is kept and billed forever until you set a policy. Set retention in the same breath you create the group. This is the week's signature cost trap.
3. **B** — EMF embeds the metric in a log line CloudWatch parses for free, avoiding the per-call `PutMetricData` charge and the request-path round-trip. It is the production default for per-request custom metrics.
4. **B** — `NOT_BREACHING` treats missing data as "fine," so a service so broken it emits nothing looks healthy and never pages. For a metric that *must* always report, use `BREACHING`.
5. **B** — A composite alarm's state is a boolean over child alarms; you express "page on the combination, suppress the children." It is the primary tool against alert fatigue.
6. **B** — OpenTelemetry keeps instrumentation vendor-neutral; the destination lives in the collector's exporter config, so switching or adding backends never touches application code. (The X-Ray SDK is not deprecated, and OTel is not chosen for runtime speed.)
7. **B** — The wrapper injects auto-instrumentation before your handler and starts the in-process collector, so AWS SDK and HTTP calls become spans with zero code changes.
8. **C** — IRSA scopes credentials to the collector's ServiceAccount/pod. Granting on the node role (B) leaks the permissions to every pod on the node; hard-coded keys (A) are never acceptable.
9. **B** — Add the exporter to the pipeline; the application keeps emitting the same OTLP. "Instrument once, export anywhere" is the whole point of the collector pattern.
10. **C** — Error budget = (1 − 0.999) × 10,000,000 = 0.001 × 10,000,000 = 10,000 failed requests.
11. **B** — Two windows: the long one confirms the burn is sustained (filters blips), the short one lets the alarm reset fast after recovery (so you're not paged about a resolved incident). AND-ed: fire when sustained, clear when recovered.
12. **B** — Threshold = burn rate × error budget = 14.4 × 0.001 = 0.0144. Fire when more than 1.44% of requests are failing over the window.
13. **B** — A silent canary means the canary (or the path it tests) is down; silence is a symptom, so `BREACHING` makes the absence of data page you. An error *count* metric is different — "no data" there genuinely means "no errors."
14. **B** — Application Signals consumes the OTel/X-Ray data to auto-discover services, render a map, compute golden signals, and make SLOs first-class with burn-rate tracking — the closest AWS gets to turnkey APM. It still needs your instrumentation underneath.

</details>

---

If you scored under 10, re-read the lecture for the questions you missed — especially the error-budget and burn-rate arithmetic (Q10–Q12) and the `treatMissingData` judgment (Q4, Q13), which the homework and challenge both lean on. If you scored 13 or 14, you're ready for the [homework](./homework.md).
