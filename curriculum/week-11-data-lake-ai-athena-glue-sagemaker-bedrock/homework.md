# Week 11 Homework

Five problems that revisit and extend the week's topics. The full set should take about **5 hours**. Work in your Week 11 Git repository so each problem produces at least one commit you can point to later. Several problems produce numbers that belong in your cost report — keep them.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — The bytes-scanned ladder

**Problem statement.** Using the data and tables from Exercises 1 and 2, run the *same* analytical query (`SELECT country, count(*) ... GROUP BY country`) against three table variants and record the bytes scanned and runtime for each:

1. Raw NDJSON, unpartitioned (or full-scan, no `dt` filter).
2. Raw NDJSON with a `WHERE dt = '<a date that exists>'` filter (partition pruning only).
3. Parquet, partition-projected, with the same `dt` filter (partition + column pruning).

Produce a small Markdown table of `variant | scanned_mb | runtime_s | est_usd` and a two-sentence explanation of why each step down the ladder is smaller.

**Acceptance criteria.**

- A committed `notes/bytes-scanned-ladder.md` with the three-row table and the explanation.
- Each `est_usd` computed as `max(scanned_bytes, 10MB) / 1e12 × $5`.
- The explanation names *partition pruning* and *column pruning* as the two distinct mechanisms.

**Hint.** You already have the projected Parquet table from Exercise 2. For variant 2, just add `WHERE dt = '...'` to the raw query. The Athena CLI's `Statistics.DataScannedInBytes` is the number you record.

**Estimated time.** 45 minutes.

---

## Problem 2 — Pin the table in IaC

**Problem statement.** The crawler-created table from Exercise 1 is fine for discovery but unfit for production (it re-infers, it typed `ts` as a string). Replace it with a hand-authored, partition-projected Parquet table defined in **OpenTofu** (or CDK if you prefer, but do at least one in OpenTofu to exercise the cross-tool muscle). The table must:

- Be Parquet, partitioned by `dt`, with projection enabled.
- Type `event_ts` as a real `timestamp`, not a string.
- Point at the Parquet location from Exercise 2.

**Acceptance criteria.**

- A committed `.tf` file declaring an `aws_glue_catalog_table` with the projection parameters and the correct Parquet SerDe.
- `tofu plan` shows the table will be created; `tofu apply` creates it.
- An Athena query against the IaC-defined table returns rows with no crawler involved.
- Committed, with the `tofu plan` output captured in the commit message or a `notes/` file.

**Hint.** The projection parameters go in the table's `parameters` map (`projection.enabled`, `projection.dt.type`, `projection.dt.range`, `storage.location.template`). The Parquet SerDe is `org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe`. See the mini-project's CDK snippet for the exact strings; the OpenTofu shape is the same metadata.

**Estimated time.** 1 hour.

---

## Problem 3 — The four-modes decision memo

**Problem statement.** For each of the four SageMaker serving modes (real-time, serverless, async, batch transform), write one concrete scenario from a hypothetical product where that mode is the *right* choice, and one sentence on why the other three would be wrong for it. Then add a final paragraph: for the capstone's recommendation feature (synchronous, on the request path, steady traffic), which mode wins and why.

**Acceptance criteria.**

- A committed `notes/sagemaker-modes-memo.md` with four scenarios (one per mode) plus the capstone paragraph.
- Each scenario states the deciding factor: synchronous-vs-async and steady-vs-spiky traffic.
- The capstone paragraph picks real-time and justifies it on latency + steady traffic, and acknowledges the idle-cost downside.

**Hint.** The two-question rule from Lecture 2: *Does the caller need a synchronous answer?* and *Is traffic steady enough to keep an instance warm?* Map each mode to a corner of that 2×2.

**Estimated time.** 45 minutes.

---

## Problem 4 — Compute your own break-even

**Problem statement.** Using the *measured* numbers from the challenge (or Exercise 3 + a single Bedrock call if you didn't finish the challenge), compute the break-even traffic between your SageMaker real-time endpoint and Bedrock Haiku for your task. Pull the *current* instance hourly rate and Bedrock per-token prices from the pricing pages (cite the date). Show:

1. The endpoint's fixed monthly cost.
2. The Bedrock per-call cost from your measured input/output tokens.
3. The break-even requests/month.
4. A recommendation for two traffic profiles: 500 calls/day and 5M calls/month.

**Acceptance criteria.**

- A committed `notes/break-even.md` with all four items and the arithmetic shown.
- Prices cited with the date pulled.
- The recommendation flips correctly across the break-even (Bedrock below, endpoint above).

**Hint.** Fixed monthly ≈ hourly × 730. Per-call Bedrock = `in_tokens × in_price/1e6 + out_tokens × out_price/1e6`. Break-even = fixed_monthly / per_call.

**Estimated time.** 45 minutes.

---

## Problem 5 — Reflection: what did you trade away?

**Problem statement.** Write a 350–450 word reflection at `notes/week-11-reflection.md` answering:

1. This week's managed services (Athena, SageMaker, Bedrock) each have an open-source comparator (DuckDB/Trino, Ray, vLLM). Pick the *one* place in your mini-project where you'd most seriously consider the open-source alternative, and say what you'd gain and lose.
2. The "bytes scanned is dollars" footer — did the Parquet improvement match your expectation, or was it smaller than you hoped (the 10 MB minimum)? What does that tell you about when the optimization actually pays off?
3. "Bedrock is a router, not a model." Did that reframing change how you'd architect an LLM feature? How?
4. One thing this week didn't cover that you now want to learn (Iceberg transactions? distributed training? fine-tuning?).

**Acceptance criteria.**

- File exists, 350–450 words, each numbered question in its own paragraph.
- Committed.

**Hint.** This is for *you*. The honest answer to Q2 (on tiny lab data the 10 MB minimum hides most of the win; the optimization pays off at multi-GB scale) is exactly the kind of nuance a senior engineer carries.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 45 min |
| 2 | 1 h 0 min |
| 3 | 45 min |
| 4 | 45 min |
| 5 | 30 min |
| **Total** | **~3 h 45 min** |

*(The schedule budgets 5h for homework to leave slack for the IaC in Problem 2, which always takes longer than you think the first time.)*

---

## Rubric

Graded out of 20.

| Criterion | Points | What earns full marks |
|---|---:|---|
| **Measurement rigor (P1, P4)** | 6 | Real bytes-scanned and token numbers, correct dollar arithmetic, prices cited with dates. Not estimates from memory. |
| **IaC correctness (P2)** | 5 | The OpenTofu/CDK table applies cleanly, uses projection, types `event_ts` correctly, and queries with no crawler. |
| **Decision reasoning (P3, P4)** | 5 | The mode memo and break-even recommendation are defensible and name the deciding factors; the recommendation flips correctly across break-even. |
| **Reflection honesty (P5)** | 2 | Engages genuinely with the trade-offs, especially the 10 MB-minimum nuance and the router reframing. |
| **Hygiene** | 2 | All commits present, files where specified, nothing left billing (no orphaned endpoint). |

A pass is 14/20. Anything below means re-read Lecture 2's decision frame and re-run Problem 4 with real numbers — that arithmetic is the week's load-bearing skill.

When you've finished all five, push your repo and open the [mini-project](./mini-project/README.md) if you haven't already.
