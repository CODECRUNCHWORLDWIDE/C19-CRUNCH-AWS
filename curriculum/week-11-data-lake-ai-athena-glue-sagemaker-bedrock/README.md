# Week 11 — Data Lake & AI: S3 + Athena + Glue, OpenSearch, SageMaker, Bedrock

Welcome to the data-and-inference week. By Friday you will have a working data lake — NDJSON events landing in S3 through Firehose, catalogued by Glue, queried by Athena, partitioned and re-encoded as Parquet with a measured cost-and-latency improvement — and an inference path: a tiny scikit-learn classifier trained on a SageMaker Spot training job, deployed to a real-time endpoint, invoked from Lambda, and benchmarked against a Bedrock Claude Haiku call on the same input.

This is Phase 3's last week, and it is two weeks in a trench coat. The first half is **analytics**: the lakehouse pattern, the Glue Data Catalog as the seam everything queries through, Athena partitioning and partition projection, columnar formats, and Lake Formation for fine-grained access. The second half is **inference**: SageMaker's four serving modes (real-time, serverless, async, batch transform), Spot training economics, and Bedrock as a *managed model router* — not a model. We deliberately end with the decision frame: when do you self-host a model on SageMaker, and when do you call a managed API? You will leave able to defend either choice with a cost and a latency number, not a vibe.

We are vendor-aware, not vendor-loyal. Every AWS primitive this week is shadowed by an open-source comparator you should know exists: **DuckDB** and **Trino** for query, **Apache Iceberg** on **MinIO** for the open table format, **Ray** for distributed training, and **vLLM** for self-hosted LLM serving. We name them not to send you down a rabbit hole, but so you know what you traded away when you reached for the managed thing.

The artifacts you build this week are not throwaway. The data lake becomes the **capstone's analytics lake**, and the SageMaker-endpoint-plus-Bedrock-comparison becomes the **capstone's recommendation feature**. Both feed off the Kinesis Firehose analytics tap you wired up in Week 10. Build them to keep.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the data-lakehouse pattern on AWS — why S3 is the storage layer, why the Glue Data Catalog is the metadata seam, and why "lake" and "warehouse" stopped being opposites.
- **Land** streaming NDJSON events into S3 via Kinesis Data Firehose with a dynamic-partitioning prefix and a buffering policy you chose on purpose.
- **Catalogue** raw data with a Glue Crawler, read the inferred schema critically, and fix the things the crawler got wrong.
- **Query** S3 data with Athena and read the bytes-scanned number as a dollar figure, not a footnote.
- **Partition** a dataset by date and **convert** it from JSON to Parquet, then re-query and **measure** the bytes-scanned and runtime improvement.
- **Configure** Athena partition projection so you stop paying for `MSCK REPAIR TABLE` and crawler reruns.
- **Reason** about Lake Formation row- and column-level security, and about when Redshift Spectrum or OpenSearch is the right tool instead of Athena.
- **Train** a small scikit-learn model in a SageMaker training job on **managed Spot** instances, with checkpointing, and read the savings line.
- **Deploy** the trained model to a SageMaker **real-time endpoint**, and explain when you would instead pick serverless, async, or batch transform.
- **Invoke** the endpoint from Lambda and **compare** its cost and latency against a Bedrock Claude Haiku call on the same input, producing a defensible self-hosted-vs-managed write-up.

## Prerequisites

This week assumes you have completed Weeks 1–10 of C19, or have equivalent AWS fluency. Specifically:

- You can deploy a CDK stack (TypeScript) from zero and read the synthesized CloudFormation. (Week 3.)
- You understand S3 storage classes, KMS encryption on a bucket, and bucket policies. (Week 6.)
- You wired up a Kinesis Data Firehose delivery stream to S3 in the Week 10 event-pipeline lab. **This week reuses that tap.** If you skipped it, the exercises include a minimal Firehose stack so you are not blocked.
- You can write a Lambda function in Python with an execution role scoped by least privilege. (Weeks 2, 7.)
- You have an AWS account with Bedrock model access enabled for **Anthropic Claude** in your Region. Enabling model access can take a few minutes to a few hours the first time — **do this on Monday**, not Thursday afternoon. (See `resources.md` for the exact console path.)
- Comfort reading a cost number off the AWS pricing page and turning it into a per-1,000-invocations figure.

You do **not** need prior machine-learning experience. The model we train is a 4-feature logistic-regression-grade classifier; the point is the *plumbing*, not the math.

## Topics covered

- **The lakehouse pattern:** S3 as the storage layer, open table formats (Parquet, ORC, Iceberg), and the Glue Data Catalog as the shared metadata layer that Athena, Redshift Spectrum, EMR, and Glue ETL all read through.
- **Kinesis Data Firehose into S3:** buffering hints (size vs interval), dynamic partitioning, JSONL delivery, error-record prefixes, and the hand-off to the Week 10 tap.
- **Glue:** the Data Catalog (databases, tables, partitions), Crawlers (and their failure modes), Glue ETL jobs (the visual editor vs PySpark vs Glue for Ray), and Glue Schema Registry in one paragraph.
- **Athena (Trino/Presto under the hood):** the `$3.99-per-TB-scanned` cost model, partitioning, **partition projection**, columnar formats, `CREATE TABLE AS SELECT` (CTAS) to write Parquet, result reuse, and workgroup cost guardrails.
- **Columnar formats:** why Parquet's column pruning and predicate pushdown turn a full-table scan into a few-megabyte read; Snappy vs ZSTD; row-group sizing.
- **Lake Formation:** tag-based access control, row- and column-level filters, and the LF-vs-bucket-policy decision.
- **Redshift basics:** RA3 nodes, Redshift Spectrum reading the same Glue catalog, Serverless — when a warehouse beats a lake.
- **OpenSearch:** managed vs Serverless, when log/text search beats SQL-over-S3.
- **SageMaker:** Studio, training jobs, **managed Spot training** with checkpointing, and the four serving modes — **real-time**, **serverless**, **async**, **batch transform** — with a decision table.
- **Bedrock:** the router mental model, `InvokeModel` vs the Converse API, on-demand vs provisioned throughput, model IDs and inference profiles, and cost per 1K tokens.
- **The decision frame:** self-hosted SageMaker vs managed Bedrock — latency, cold-start, fixed-cost-per-hour vs per-token, and the break-even traffic level.
- **Open-source comparators:** DuckDB, Trino, MinIO + Iceberg, Ray, vLLM — what each replaces and what you give up.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target.

| Day       | Focus                                                          | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Lakehouse pattern; enable Bedrock access; S3/Glue/Athena read  |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | Firehose → S3 → Glue crawl → Athena (Exercise 1)               |    1h    |    2.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Wednesday | Partition + Parquet; cost/latency measurement (Exercise 2)     |    1h    |    2.5h   |     1h     |    0.5h   |   0.5h   |     0h       |    0.5h    |     6h      |
| Thursday  | SageMaker Spot training + real-time endpoint (Exercise 3)      |    2h    |    2h     |     0h     |    0.5h   |   0.5h   |     1h       |    0h      |     6h      |
| Friday    | Bedrock router; the decision frame (Challenge 1)               |    0h    |    0h     |     2.5h   |    0.5h   |   0.5h   |     2h       |    0h      |     5.5h    |
| Saturday  | Mini-project deep work                                         |    0h    |    0h     |     0h     |    0h     |   0.5h   |     3.5h     |    0h      |     4h      |
| Sunday    | Quiz, cost report, review                                      |    0h    |    0h     |     0h     |    1h     |   1h     |     0.5h     |    0h      |     2.5h    |
| **Total** |                                                                | **6h**   | **8.5h**  | **3.5h**   | **3.5h**  | **5h**   | **7.5h**     | **1.5h**   | **35.5h**   |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated AWS docs, talks, books, and open-source comparators, current to 2026 |
| [lecture-notes/01-data-lakehouse-and-bedrock-router.md](./lecture-notes/01-data-lakehouse-and-bedrock-router.md) | The lakehouse pattern on AWS; Glue/Athena/Parquet mechanics; why Bedrock is a router not a model |
| [lecture-notes/02-sagemaker-inference-vs-bedrock.md](./lecture-notes/02-sagemaker-inference-vs-bedrock.md) | SageMaker's four serving modes, Spot training, and the cost-and-latency decision frame vs Bedrock |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-firehose-glue-athena.md](./exercises/exercise-01-firehose-glue-athena.md) | Land NDJSON via Firehose, crawl with Glue, query with Athena |
| [exercises/exercise-02-partition-parquet-measure.py](./exercises/exercise-02-partition-parquet-measure.py) | Partition by date, convert to Parquet via CTAS, re-query, measure cost & latency |
| [exercises/exercise-03-sagemaker-spot-endpoint.py](./exercises/exercise-03-sagemaker-spot-endpoint.py) | Train a scikit-learn classifier on Spot, deploy a real-time endpoint |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-endpoint-vs-bedrock.md](./challenges/challenge-01-endpoint-vs-bedrock.md) | Invoke the endpoint and a Bedrock Haiku call from Lambda; write the decision doc |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the "Lake + Inference Layer" — feeds the capstone |
| [quiz.md](./quiz.md) | 13 questions with an answer key |
| [homework.md](./homework.md) | Concrete homework with deliverables and a rubric |

## The "bytes scanned is dollars" promise

C19's recurring marker this week is the Athena query footer:

```
Run time: 1.84 sec · Data scanned: 12.74 MB · Estimated cost: $0.0000485
```

If you cannot point at the **Data scanned** number after every query and explain why it is what it is, you are not done. The single most common AWS data-lake bill shock is "we ran a dashboard that scans the whole lake every 60 seconds." The point of Wednesday is to make a 4 GB scan into a 12 MB scan and to *feel* the difference in the footer. Bytes scanned is dollars. Internalize it.

## Stretch goals

If you finish the regular work early and want to push further:

- Re-do Exercise 2 with an **Apache Iceberg** table in Athena (`CREATE TABLE ... TBLPROPERTIES ('table_type'='ICEBERG')`) and run an `UPDATE` and a `DELETE` — something raw Parquet cannot do — then read the Iceberg manifest in the bucket.
- Query the same Parquet locally with **DuckDB** (`SELECT * FROM read_parquet('s3://.../*.parquet')`) and compare the developer experience and cost (free) against Athena.
- Deploy the same scikit-learn model to a **SageMaker Serverless** endpoint instead of real-time, and measure the cold-start penalty against the per-hour savings at low traffic.
- Switch the Bedrock call from `InvokeModel` to the **Converse API** and note how the request shape becomes model-agnostic — the whole point of "router."
- Stand up a single-node **vLLM** server on a `g5.xlarge` Spot instance, serve a small open model, and compare tokens-per-second and dollars-per-1M-tokens against Bedrock Haiku.

## Up next

Week 12 — Observability: CloudWatch, X-Ray, OpenTelemetry, ADOT. You will instrument the Week-10 pipeline and this week's inference path with traces and burn-rate alarms. Push your lake and endpoint before you move on; Week 13 begins the capstone build and assumes both exist.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
