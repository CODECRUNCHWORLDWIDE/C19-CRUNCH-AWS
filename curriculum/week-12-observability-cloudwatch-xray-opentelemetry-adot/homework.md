# Week 12 Homework

Five problems that revisit and extend the week's topics. The full set should take about **5 hours**. Work in your Week 12 Git repository so each problem produces at least one commit you can point to later. Several problems produce numbers that belong in your cost report — keep them.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — The trace → metric → log pivot, end to end

**Problem statement.** Using the instrumented Lambda from Exercise 2 (with structured logging and `trace_id` from Exercise 1 folded in), produce a written walkthrough that demonstrates the full triage pivot on a *single failing request*:

1. Find the failing request in the **X-Ray service map / trace** (the WHERE).
2. Confirm scope and duration on a **CloudWatch metric** (the HOW BAD).
3. Pivot to the **exact log line** for that request via a Logs Insights query `filter trace_id = "<the id>"` (the WHAT EXACTLY).

Capture the trace id, the screenshot/CLI output at each step, and the one log line you landed on.

**Acceptance criteria.**

- A committed `notes/triage-pivot.md` with the three steps, each showing the artifact (trace, metric, log line) and naming the signal.
- The Logs Insights query uses the `trace_id` from the trace to find the exact log — proving the signals are connected.
- A two-sentence reflection on how long the pivot took versus grepping logs blind.

**Hint.** For the failing request, set `FAIL_RATE=1.0` briefly, invoke once, then immediately `aws xray get-trace-summaries` to get the trace id; use that id in the Logs Insights `filter`.

**Estimated time.** 45 minutes.

---

## Problem 2 — EMF vs PutMetricData, with the bill

**Problem statement.** Quantify the cost difference between EMF and `PutMetricData` for a per-request custom metric. For a hypothetical service doing **5,000,000 requests/month**, each emitting one custom metric:

1. Compute the cost if each metric is sent via a **`PutMetricData` API call** (per-call pricing).
2. Compute the cost if the same metric rides in an **EMF log line** you were already ingesting (i.e. the marginal API cost is zero; only the metric-storage and the already-paid log ingestion count).
3. State the ratio and the dollar delta per month.

**Acceptance criteria.**

- A committed `notes/emf-vs-putmetricdata.md` with both costs, the arithmetic, and the prices cited with the date pulled from the CloudWatch pricing page.
- A correct statement of *why* EMF avoids the per-call charge (the metric is parsed from a log line, not posted via the API).
- The conclusion names the threshold request volume above which EMF clearly wins (hint: it wins almost immediately for per-request metrics).

**Hint.** `PutMetricData` is billed per API call beyond the free tier; EMF metrics cost the per-metric-month custom-metric fee but no per-call API fee, because they arrive inside the log ingestion you already pay for. Pull the per-1,000-requests `PutMetricData` price and the per-custom-metric price from the live pricing page.

**Estimated time.** 45 minutes.

---

## Problem 3 — The burn-rate alarm table, derived

**Problem statement.** For a **99.9% SLO over 30 days**, derive the full multi-window multi-burn-rate alarm table yourself (do not copy the lecture's). For each of the four canonical burn rates **14.4, 6, 3, 1**, compute:

1. The **error-ratio threshold** the alarm fires at (`burn_rate × 0.001`).
2. The **time-to-exhaust-budget** if that burn rate is sustained.
3. The recommended **long/short window** pair and whether it routes to **page** or **ticket**.

Then write one paragraph explaining why a single static threshold cannot replace this table.

**Acceptance criteria.**

- A committed `notes/burn-rate-table.md` with a four-row table (burn rate | threshold | time-to-exhaust | windows | page/ticket).
- The thresholds are arithmetically correct (`14.4 × 0.001 = 0.0144`, etc.).
- The "why one threshold fails" paragraph names the page-vs-ticket asymmetry explicitly.

**Hint.** Time-to-exhaust at burn rate `B` over a 30-day budget is `30 days / B` (a burn rate of 1 exhausts exactly at 30 days; 14.4 exhausts in ~2 days). The threshold is `B × error_budget`. Windows come from the SRE workbook's table; you may reuse those window choices but you must compute the thresholds.

**Estimated time.** 45 minutes.

---

## Problem 4 — Pin a burn-rate alarm in IaC (OpenTofu)

**Problem statement.** The challenge built the burn-rate alarm in CDK. Re-implement **one** burn-rate composite alarm (the fast-burn 14.4 row, long+short windows AND-ed) in **OpenTofu** (or Terraform) to exercise the cross-tool muscle. The alarm must:

- Use `aws_cloudwatch_metric_alarm` with a **metric-math `metric_query`** computing the error ratio `errors / total`.
- Threshold at `0.0144` for each window.
- Combine the two child alarms with an `aws_cloudwatch_composite_alarm`.

**Acceptance criteria.**

- A committed `.tf` file declaring the two child alarms (metric-math ratio, 1h and 5min) and the composite alarm.
- `tofu plan` shows the alarms will be created; capture the plan output in the commit message or a `notes/` file.
- `tofu apply` creates them, and `aws cloudwatch describe-alarms` shows the composite.

**Hint.** In OpenTofu, the metric-math ratio is expressed as `metric_query` blocks: one with `id = "e"` (the 5XXError metric), one with `id = "t"` (the Count metric), and one with `expression = "e/t"` and `return_data = true`. The composite uses `alarm_rule = "ALARM(child-long) AND ALARM(child-short)"`.

**Estimated time.** 1 hour.

---

## Problem 5 — Reflection: what did you trade away, and what does it cost?

**Problem statement.** Write a 350–450 word reflection at `notes/week-12-reflection.md` answering:

1. This week's instrumentation is OpenTelemetry, but the backend was AWS-native (X-Ray, CloudWatch). Pick the *one* place in your mini-project where you'd most seriously consider the open-source backend (Jaeger/Tempo for traces, Prometheus for metrics, Loki for logs, Grafana for dashboards) and say what you'd gain and lose. Note that the *instrumentation* would not change — only the exporter.
2. "Trace > metric > log." Did wiring `trace_id` into your logs actually change how fast you found the root cause in Problem 1, versus how you'd have done it before this week?
3. Your observability bill (from the cost report) as a fraction of your workload's compute bill — is it proportionate? If it's over ~15%, what would you sample down first (trace sampling rate? log level? high-res metrics?)?
4. One thing this week didn't cover that you now want to learn (trace context across async boundaries? PromQL? continuous profiling? eBPF auto-instrumentation?).

**Acceptance criteria.**

- File exists, 350–450 words, each numbered question in its own paragraph.
- Committed.

**Hint.** This is for *you*. The honest answer to Q3 (observability commonly runs 5–15% of compute; over that, sample traces harder and drop DEBUG logging in prod first) is exactly the kind of cost judgment a senior engineer carries into a design review.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 45 min |
| 2 | 45 min |
| 3 | 45 min |
| 4 | 1 h 0 min |
| 5 | 30 min |
| **Total** | **~3 h 45 min** |

*(The schedule budgets 5h for homework to leave slack for the IaC in Problem 4, which always takes longer than you think the first time — metric-math `metric_query` blocks in OpenTofu are fiddly the first time.)*

---

## Rubric

Graded out of 20.

| Criterion | Points | What earns full marks |
|---|---:|---|
| **Triage rigor (P1)** | 5 | A real end-to-end trace→metric→log pivot on one request, with the `trace_id` carried from the trace into the Logs Insights filter. Not three disconnected screenshots. |
| **Cost arithmetic (P2)** | 4 | Correct EMF vs `PutMetricData` numbers, prices cited with dates, the per-call-charge mechanism stated correctly. |
| **Burn-rate reasoning (P3)** | 5 | The table's thresholds and time-to-exhaust are arithmetically correct, and the page-vs-ticket asymmetry is explained. |
| **IaC correctness (P4)** | 4 | The OpenTofu metric-math alarm and composite apply cleanly and show in `describe-alarms`. |
| **Reflection honesty (P5)** | 2 | Engages genuinely with the trade-offs, especially the "instrumentation doesn't change, only the exporter" point and the observability-cost-proportionality judgment. |

A pass is 14/20. Anything below means re-read Lecture 2's SLO/burn-rate section and redo Problem 3 with the arithmetic shown — that derivation is the week's load-bearing skill and the capstone is graded on it.

When you've finished all five, push your repo and open the [mini-project](./mini-project/README.md) if you haven't already.
