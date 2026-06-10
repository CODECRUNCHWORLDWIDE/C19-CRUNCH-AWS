# Mini-Project — The Lake + Inference Layer

> Deliver a working data lake (Kinesis Firehose → S3 → Glue → Athena, Parquet-optimized with partition projection) **plus** a SageMaker real-time endpoint invoked from Lambda, with a Bedrock Claude Haiku comparison. The whole thing is defined in CDK (TypeScript), deploys from zero, and produces a cost report. **This layer becomes the capstone's analytics lake and its SageMaker/Bedrock recommendation feature, feeding off the Week-10 Firehose analytics tap.**

This is the week's capstone-feeder. Everything you built in the exercises and the challenge gets assembled into one CDK app you can `cdk deploy --all` from a blank account and tear down with `cdk destroy --all`. When you reach Week 13 and the capstone build begins, you will *import this stack*, not rebuild it. Build it to keep.

**Estimated time:** ~7.5 hours (Thursday spill-over, Friday, Saturday in the suggested schedule).

---

## How this compounds

The syllabus is explicit that Week 11's output is not a throwaway lab:

- It **feeds off the Week-10 Firehose analytics tap.** In Week 10 you stood up a Kinesis Data Firehose delivery stream as the analytics branch of the event pipeline. This week's lake is the *destination* that tap writes to. If you kept the Week-10 stream, point it at this lake's bucket. If you didn't, this project includes a self-contained Firehose stack so you are not blocked — but wire it to the real Week-10 tap if you have it.
- It **becomes the capstone's analytics lake.** The capstone spec calls for "S3 + Glue + Athena for the data lake." This is that lake.
- It **becomes the capstone's recommendation feature.** The capstone spec calls for "a SageMaker real-time endpoint serving a small recommendation model, called from Lambda" and "a parallel Bedrock-Claude call for a comparison feature." This is that feature.

So the acceptance bar is higher than a lab: the IaC must be clean enough to import into the capstone monorepo in Week 13.

---

## What you will build

A CDK (TypeScript) app with three stacks and one inference component:

```
                    Week-10 Firehose tap (events)
                              │
                              ▼
   ┌───────── LakeIngestStack ─────────┐
   │  Firehose → S3 (events/dt=.../)    │
   │  Athena results bucket             │
   │  Athena workgroup (scan cutoff)    │
   └────────────────┬───────────────────┘
                     │
   ┌───────── LakeCatalogStack ────────┐
   │  Glue database                     │
   │  Glue table: events_parquet_proj   │   ← partition-projected, Parquet
   │  (the raw->Parquet CTAS is run via  │
   │   an Athena named query / script)   │
   └────────────────┬───────────────────┘
                     │
   ┌───────── InferenceStack ──────────┐
   │  SageMaker model (from trained     │
   │    artifact in S3) + endpoint cfg  │
   │    + real-time endpoint            │
   │  Lambda: recommend()               │
   │    ├─ Path A: invoke endpoint      │
   │    └─ Path B: Bedrock Haiku        │
   │  API Gateway HTTP API in front     │
   └─────────────────────────────────────┘
```

The model artifact is produced by the Exercise 3 training job (run once, by hand, on Spot); the endpoint that serves it is defined in CDK so it is reproducible. The Lambda is the capstone's recommendation handler in miniature.

---

## Required architecture

### Data lake half

- **Ingest.** A Firehose delivery stream writing NDJSON to `s3://<lake>/events/dt=YYYY-MM-DD/` with an `errorOutputPrefix` set. Buffering tuned for analytics freshness (justify your numbers in the README), not the lab's tiny 1 MB.
- **Storage.** A KMS-encrypted lake bucket, public access fully blocked, `enforceSSL`. A separate Athena results bucket with a lifecycle rule expiring results after 7 days (results are disposable; don't pay to store them).
- **Catalog.** A Glue database and a **partition-projected, Parquet** external table (`events_parquet_proj`) defined in IaC — not crawler-created. The crawler may be used for one-time discovery, but the table that the capstone depends on is pinned in CDK.
- **Transform.** A documented path from raw JSON to partitioned Parquet via Athena CTAS. You may run the CTAS by hand (a named query in CDK) or on a schedule (a Glue ETL job / EventBridge-triggered Athena query) — pick one and justify it.
- **Guardrail.** An Athena workgroup with a `bytesScannedCutoffPerQuery` and `enforceWorkGroupConfiguration: true`.

### Inference half

- **Endpoint.** A SageMaker real-time endpoint serving the Exercise 3 model, defined as model + endpoint config + endpoint in CDK (the `aws-sagemaker` L1/L2 constructs). The training job that produces the artifact is run separately and its S3 artifact URI is a stack parameter.
- **Lambda.** A `recommend` handler that takes a feature vector, invokes the endpoint (Path A) and Bedrock Haiku (Path B) on the same input, and returns both with per-path latency and (for Bedrock) token usage.
- **API.** An API Gateway HTTP API in front of the Lambda so the feature is callable over HTTPS, matching the capstone's API layer.
- **IAM.** The Lambda role grants `sagemaker:InvokeEndpoint` and `bedrock:InvokeModel` on **specific resource ARNs**. No `*`.

### Cross-cutting

- **Tags.** Every resource tagged `team`, `service`, `environment` — the capstone's FinOps requirement starts here.
- **One-command deploy/destroy.** `cdk deploy --all` from zero; `cdk destroy --all` leaves nothing billing.

---

## Rules

- **CDK (TypeScript) is the source of truth.** You may use the Athena/Glue CLI to *run* the CTAS and the SageMaker SDK to *train*, but every persistent resource is in CDK so the capstone can import it.
- **No real-time endpoint left running unattended.** Because the endpoint bills by the hour, your README must document the deploy-test-destroy loop, and your `cdk destroy --all` must actually remove the endpoint. Demonstrate it.
- **The Parquet table must use partition projection.** A crawler-dependent table is not acceptable for the capstone; new days must work with no `MSCK`/crawler.
- **The Lambda must hit both paths.** A SageMaker-only or Bedrock-only Lambda does not satisfy the comparison requirement.
- **Cost report required.** Real dollar figures, not estimates-from-memory.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c19-week-11-lake-inference-<yourhandle>`.
- [ ] `npx cdk deploy --all` from a clean account stands up the lake-ingest, catalog, and inference stacks with no manual console steps (other than the one-time training run and Bedrock model-access opt-in, both documented).
- [ ] Firehose delivers NDJSON to `events/dt=YYYY-MM-DD/` with an error prefix configured.
- [ ] An Athena query against `events_parquet_proj` filtered by `dt` scans **materially fewer bytes** than the same query against the raw JSON table. Include both query footers in the README.
- [ ] Partition projection is configured; a query for a `dt` that landed *after* the table was created works with no `MSCK`/crawler. Demonstrate it.
- [ ] The Athena workgroup enforces a per-query scan cutoff. Show a query that would exceed it being cancelled.
- [ ] A SageMaker real-time endpoint serves the trained model, defined in CDK.
- [ ] The `recommend` Lambda, callable through API Gateway, returns both a SageMaker prediction and a Bedrock Haiku answer for the same input, each with a latency, and Bedrock with token usage.
- [ ] The Lambda role uses least-privilege resource ARNs for both `InvokeEndpoint` and `InvokeModel`.
- [ ] Every resource is tagged `team`, `service`, `environment`.
- [ ] `npx cdk destroy --all` removes everything, including the endpoint. Prove no endpoint remains with `aws sagemaker list-endpoints`.
- [ ] A `COSTREPORT.md` with the figures below.
- [ ] A `README.md` with: one-paragraph description, exact from-clone setup commands, the two query footers (raw vs Parquet), and the deploy-test-destroy loop.

---

## The cost report

`COSTREPORT.md` must contain, with real numbers pulled from the pricing pages (cite the date you pulled them):

1. **Athena improvement.** Bytes scanned and estimated dollars for the analytical query on the raw JSON table vs the Parquet projected table, and the ratio.
2. **Firehose.** Per-GB ingest cost and what one day of your event volume costs.
3. **SageMaker endpoint.** The hourly instance cost and the implied monthly cost if left running 24/7.
4. **SageMaker training.** Spot billable seconds and the savings percentage from your Exercise 3 run.
5. **Bedrock.** Measured average input/output tokens per `recommend` call and the per-call cost.
6. **Break-even.** The traffic level (requests/month) at which the always-on endpoint's fixed cost equals Bedrock's variable cost for this feature.
7. **Idle bill.** What this whole stack costs per day if *nobody calls it* — the number that explains why you destroy the endpoint nightly.

---

## Suggested build order

1. **Thursday spill-over (1 h).** Scaffold the CDK app (`cdk init app --language typescript`), create the `LakeIngestStack` (bucket, results bucket, workgroup, Firehose), deploy it, and re-point your Week-10 tap (or the generator) at it.
2. **Friday morning (2 h).** Run the CTAS to produce Parquet, then write `LakeCatalogStack` to pin the `events_parquet_proj` table with projection in IaC. Capture both query footers.
3. **Friday afternoon (1 h).** Run the Exercise 3 training job once on Spot; record the artifact S3 URI; write the savings line into the cost report.
4. **Saturday morning (2.5 h).** Build `InferenceStack`: SageMaker model/config/endpoint from the artifact, the `recommend` Lambda hitting both paths, the API Gateway HTTP API, and the scoped IAM.
5. **Saturday afternoon (1 h).** Write `COSTREPORT.md` and `README.md`. Run the full deploy-test-destroy loop once, clean, and confirm nothing is left billing.

---

## A worked snippet — the catalog table in CDK

So you are not staring at a blank file, here is the partition-projected Parquet table as an L1 `CfnTable`. This is the resource the capstone imports.

```typescript
import * as glue from 'aws-cdk-lib/aws-glue';

new glue.CfnTable(this, 'EventsParquetProj', {
  catalogId: this.account,
  databaseName: 'events',
  tableInput: {
    name: 'events_parquet_proj',
    tableType: 'EXTERNAL_TABLE',
    parameters: {
      'classification': 'parquet',
      'projection.enabled': 'true',
      'projection.dt.type': 'date',
      'projection.dt.range': '2026-01-01,NOW',
      'projection.dt.format': 'yyyy-MM-dd',
      'projection.dt.interval': '1',
      'projection.dt.interval.unit': 'DAYS',
      'storage.location.template':
        `s3://${this.lakeBucket.bucketName}/events_parquet/dt=\${dt}/`,
    },
    partitionKeys: [{ name: 'dt', type: 'string' }],
    storageDescriptor: {
      location: `s3://${this.lakeBucket.bucketName}/events_parquet/`,
      inputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat',
      outputFormat: 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat',
      serdeInfo: {
        serializationLibrary:
          'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe',
      },
      columns: [
        { name: 'user_id', type: 'string' },
        { name: 'country', type: 'string' },
        { name: 'page', type: 'string' },
        { name: 'session_ms', type: 'int' },
        { name: 'event_ts', type: 'timestamp' },
      ],
    },
  },
});
```

The `inputFormat` / `outputFormat` / `serializationLibrary` triple is the verbose part of a Parquet external table; copy it exactly. The projection parameters are what make new `dt=` folders queryable with no crawler — exactly the operational property the capstone needs.

---

## Submission

Push the repo. In your engineering journal, answer: *If the recommendation feature gets 50 calls a day in production, did you ship the right thing by self-hosting a SageMaker endpoint? What would you change?* The honest answer (at 50 calls/day you are far below break-even and an always-on endpoint is wasteful — serverless or Bedrock wins) is the point. Knowing it, and being able to say it about your own architecture, is the skill.

---

## What this sets up

Week 12 instruments this layer with OpenTelemetry: traces from the `recommend` Lambda through the endpoint and the Bedrock call, and a burn-rate alarm on the API's availability. Week 13 imports both stacks into the capstone monorepo. Do not delete the repo when the week ends — you will `git submodule`/copy it forward.
