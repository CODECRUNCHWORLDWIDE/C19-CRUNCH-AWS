# Week 11 — Resources

Everything here is free to read. AWS documentation is open. The re:Invent talks are on YouTube. The open-source projects are public on GitHub. We link a few paid books at the chapter level only where the free docs genuinely fall short.

A scheduling note that will save you a day: **enable Bedrock model access for Anthropic Claude on Monday.** It is a one-time, per-account, per-Region opt-in under Bedrock → Model access, and the first approval is not always instant. Do not discover this on Friday.

## Required reading (work it into your week)

- **What is a data lake? (AWS)** — the canonical framing for the storage-layer-plus-catalog pattern:
  <https://docs.aws.amazon.com/whitepapers/latest/building-data-lakes/building-data-lake-aws.html>
- **AWS Glue Data Catalog overview** — the metadata seam everything queries through:
  <https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html>
- **Athena — partitioning and partition projection** — the single most important cost lever this week:
  <https://docs.aws.amazon.com/athena/latest/ug/partitions.html>
  <https://docs.aws.amazon.com/athena/latest/ug/partition-projection.html>
- **Athena — columnar storage (Parquet/ORC) and CTAS** — how to turn a full scan into a few-megabyte read:
  <https://docs.aws.amazon.com/athena/latest/ug/columnar-storage.html>
  <https://docs.aws.amazon.com/athena/latest/ug/ctas.html>
- **SageMaker — managed Spot training**:
  <https://docs.aws.amazon.com/sagemaker/latest/dg/model-managed-spot-training.html>
- **SageMaker — deploy models for inference (the four modes)**:
  <https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model.html>
- **Bedrock — what is Amazon Bedrock** and the **Converse API**:
  <https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html>
  <https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html>

## Pricing pages (read these as dollars, not docs)

You cannot do this week's decision frame without the numbers. Open these and write the figures into your cost report:

- **Athena pricing** — per-TB scanned for the standard engine; capacity reservations for the alternative model:
  <https://aws.amazon.com/athena/pricing/>
- **Glue pricing** — DPU-hours for crawlers and ETL jobs; the catalog is mostly free until you have a lot of objects:
  <https://aws.amazon.com/glue/pricing/>
- **SageMaker pricing** — training (Spot vs on-demand), real-time endpoint instance-hours, serverless per-second, async, and batch transform:
  <https://aws.amazon.com/sagemaker/pricing/>
- **Bedrock pricing** — on-demand per-1K-input/output-tokens by model; provisioned-throughput per-model-unit-hour:
  <https://aws.amazon.com/bedrock/pricing/>
- **Kinesis Data Firehose pricing** — per-GB ingested, plus dynamic-partitioning and format-conversion surcharges:
  <https://aws.amazon.com/kinesis/data-firehose/pricing/>

## AWS docs you will reach for during the build

- **Firehose — dynamic partitioning**: <https://docs.aws.amazon.com/firehose/latest/dev/dynamic-partitioning.html>
- **Firehose — record format conversion to Parquet** (an alternative to Athena CTAS):
  <https://docs.aws.amazon.com/firehose/latest/dev/record-format-conversion.html>
- **Glue Crawlers — how crawlers work** (and how they mis-infer): <https://docs.aws.amazon.com/glue/latest/dg/add-crawler.html>
- **Lake Formation — fine-grained access** (row/column filters, LF-tags):
  <https://docs.aws.amazon.com/lake-formation/latest/dg/data-filtering.html>
- **Redshift Spectrum — querying external data in S3** (same Glue catalog as Athena):
  <https://docs.aws.amazon.com/redshift/latest/dg/c-using-spectrum.html>
- **OpenSearch Serverless — overview**: <https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html>
- **SageMaker Python SDK** (the `Estimator` / `Predictor` you use Thursday):
  <https://sagemaker.readthedocs.io/en/stable/>
- **SageMaker SKLearn estimator** (the prebuilt scikit-learn container):
  <https://sagemaker.readthedocs.io/en/stable/frameworks/sklearn/index.html>
- **Athena Iceberg tables** (stretch goal): <https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg.html>

## CDK / IaC reference

- **AWS CDK — `aws-glue-alpha`** (L2 constructs for Glue databases, tables, jobs; still alpha in 2026):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_glue_alpha-readme.html>
- **AWS CDK — `aws-sagemaker-alpha`** (endpoint config / endpoint constructs):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sagemaker_alpha-readme.html>
- **AWS CDK — `aws-kinesisfirehose`** (delivery streams, now stable):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_kinesisfirehose-readme.html>
- **CloudFormation — `AWS::Glue::Table`** (when you want the partition-projection table properties verbatim):
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-glue-table.html>
- **OpenTofu / Terraform AWS provider** — `aws_glue_catalog_table`, `aws_athena_workgroup`, `aws_sagemaker_endpoint`:
  <https://search.opentofu.org/provider/hashicorp/aws/latest>

## re:Invent and AWS talks (free, on YouTube)

- **"Deep dive into Amazon Athena"** (re:Invent ANT-track deep dive — partitioning, projection, federation). Search the AWS Events channel for the most recent year's ANT3xx Athena session:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Building a modern data architecture on AWS"** — the lakehouse framing from the horse's mouth (annual; pick the latest):
  <https://www.youtube.com/@AWSEventsChannel>
- **"Amazon SageMaker inference: deploy and scale models"** — the four-modes talk:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Amazon Bedrock: build generative AI applications"** — the router pitch and the Converse API:
  <https://www.youtube.com/@AWSEventsChannel>

*(re:Invent session IDs change yearly; the channel is stable. Filter by the most recent year and the ANT / AIM tracks.)*

## Open-source comparators (know what you traded away)

- **DuckDB** — an in-process analytical database that reads Parquet from S3 directly; the right tool when your data fits on one box. Free, no cluster, no per-scan bill:
  <https://duckdb.org/docs/>
- **Trino** — the distributed SQL engine Athena is built on; run it yourself when you outgrow Athena's per-scan model or want federation Athena doesn't offer:
  <https://trino.io/docs/current/>
- **Apache Iceberg** — the open table format that gives a lake ACID transactions, time travel, and schema evolution; Athena, Glue, Redshift, and Spark all speak it:
  <https://iceberg.apache.org/docs/latest/>
- **MinIO** — S3-API-compatible object storage you run yourself; pair with Iceberg for a fully open lakehouse:
  <https://min.io/docs/minio/linux/index.html>
- **Ray** — distributed Python for training and data processing; the open alternative to SageMaker's managed training (and what Glue for Ray wraps):
  <https://docs.ray.io/en/latest/>
- **vLLM** — high-throughput LLM serving with PagedAttention; the self-hosted alternative to Bedrock when you have GPUs and traffic to justify them:
  <https://docs.vllm.ai/en/latest/>

## Books (chapter-level)

- **"Data Engineering on AWS"** patterns — the free AWS Prescriptive Guidance has a usable data-lake reference architecture you can read in 30 minutes:
  <https://docs.aws.amazon.com/prescriptive-guidance/latest/modern-data-centric-use-cases/welcome.html>
- **"Designing Data-Intensive Applications" (Kleppmann)** — Chapter 3 (storage engines, column-oriented storage) is the best explanation of *why Parquet wins* that exists. Borrow it; read one chapter.

## The Claude / Bedrock model reference

This week you call **Anthropic Claude Haiku** through Bedrock. Model IDs, the region-prefixed **inference profile** IDs, token pricing, and the Converse-vs-InvokeModel request shapes change often enough that you should not trust memory. Confirm the current Haiku model ID and per-1K-token price from the Bedrock console (Model access → the model's detail page) and the pricing page above before you write your cost report. The lecture notes use `anthropic.claude-3-5-haiku-20241022-v1:0` and the US cross-Region inference profile `us.anthropic.claude-3-5-haiku-20241022-v1:0` as the worked example; verify against your account's available models, because availability is Region- and account-specific.

## Tools you'll use this week

- **AWS CLI v2** — `aws athena start-query-execution`, `aws glue start-crawler`, `aws sagemaker invoke-endpoint`. Verify with `aws --version` (want `aws-cli/2.x`).
- **Python 3.12+** with `boto3`, `sagemaker`, `scikit-learn`, `pandas`, `pyarrow`. A `requirements.txt` ships with each exercise.
- **AWS CDK v2** (TypeScript) — `npx cdk deploy`. The mini-project's infra is CDK.
- **DuckDB CLI** (optional, stretch) — `brew install duckdb` / `apt install duckdb`.
- **`jq`** — for slicing the JSON that the Athena and SageMaker CLIs return.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Data lake** | Raw and processed data on object storage (S3), queried in place. No mandatory schema-on-write. |
| **Lakehouse** | A lake plus warehouse-grade features (transactions, schema) via an open table format like Iceberg. |
| **Glue Data Catalog** | The shared metadata store: databases → tables → partitions. Athena, Redshift, EMR all read it. |
| **Crawler** | A Glue job that scans S3, infers schema and partitions, and writes catalog tables. Often gets types wrong. |
| **Partition** | A folder prefix (e.g. `dt=2026-06-09/`) that lets the engine skip data it doesn't need to read. |
| **Partition projection** | Athena computes partition values from a formula instead of listing them. No `MSCK REPAIR`, no crawler. |
| **Parquet** | A columnar file format. Stores columns together so the engine reads only the columns a query touches. |
| **CTAS** | `CREATE TABLE AS SELECT` — Athena writes query results to S3 as Parquet, partitioned, in one statement. |
| **Bytes scanned** | The amount of S3 data Athena read for a query. **This is what you pay for.** Lower it relentlessly. |
| **Lake Formation** | Fine-grained (row/column) access control over catalog tables, replacing hand-written bucket policies. |
| **Endpoint (real-time)** | A persistent SageMaker HTTPS server backed by instance(s) you pay for by the hour, 24/7. |
| **Serverless endpoint** | A SageMaker endpoint that scales to zero; you pay per inference-second; cold starts apply. |
| **Batch transform** | A SageMaker job that runs inference over a whole S3 dataset, then shuts down. No persistent server. |
| **Bedrock** | A managed API that routes one request shape to many foundation models. You bring no infra. |
| **Inference profile** | A Region-prefixed Bedrock model ID (e.g. `us.anthropic...`) that routes across Regions for capacity. |
| **Token** | The unit Bedrock bills in. Roughly ¾ of a word. Priced separately for input and output. |

---

*If a link 404s, please open an issue so we can replace it.*
