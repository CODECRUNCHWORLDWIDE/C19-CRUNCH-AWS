# Week 11 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 12. Answer key at the bottom — don't peek.

---

**Q1.** In the AWS lakehouse pattern, which component is "the seam" that lets Athena, Redshift Spectrum, EMR, and Glue ETL all query the same table definition?

- A) The S3 bucket policy.
- B) The Glue Data Catalog.
- C) The Athena workgroup.
- D) Lake Formation.

---

**Q2.** Athena's standard engine charges primarily by:

- A) The number of rows returned.
- B) The wall-clock time the query runs.
- C) The number of bytes scanned from S3.
- D) A flat per-query fee.

---

**Q3.** You have 4 GB of NDJSON click events. The query `SELECT count(*) FROM clicks WHERE dt = '2026-06-09' AND country = 'JP'` is slow and expensive. Which change reduces bytes scanned the **most**?

- A) Adding a secondary index.
- B) Partitioning by `dt` and converting to Parquet.
- C) Increasing the Athena query timeout.
- D) Switching the result-output bucket to a colder storage class.

---

**Q4.** What does Athena **partition projection** let you avoid?

- A) Paying for S3 storage.
- B) Running `MSCK REPAIR TABLE` or a crawler to register new partitions.
- C) Writing SQL `WHERE` clauses.
- D) Encrypting the data at rest.

---

**Q5.** A Glue crawler is scheduled to run hourly in production with `UpdateBehavior: UPDATE_IN_DATABASE`. One morning every dashboard breaks. What is the most likely cause?

- A) The crawler ran out of DPU credits.
- B) A new file had a value that made the crawler re-infer a column's type, mutating the table schema.
- C) Athena deprecated the table format overnight.
- D) S3 returned the data in a different byte order.

---

**Q6.** Why does Parquet typically beat NDJSON for analytical queries?

- A) Parquet files are always smaller because JSON is banned.
- B) Parquet is columnar, so the engine reads only the columns a query touches and can prune row groups by predicate.
- C) Parquet caches results in memory automatically.
- D) Parquet stores data in S3 Glacier by default.

---

**Q7.** The lecture's central claim is "Bedrock is a router, not a model." What does that mean operationally?

- A) Bedrock is a networking appliance.
- B) Bedrock is a managed API that routes one request shape to many foundation models; the model is a per-request parameter.
- C) Bedrock can only call Amazon's own Titan/Nova models.
- D) Bedrock requires you to provision GPU instances before use.

---

**Q8.** You want to swap from Claude Haiku to Llama with the least code change while keeping the same request/response handling. You should use:

- A) `InvokeModel` with a per-model request body.
- B) The Converse API, changing only the `modelId`.
- C) A separate SDK per model vendor.
- D) A SageMaker endpoint per model.

---

**Q9.** For training a model, why is managed Spot training usually the right choice?

- A) Spot instances are faster than on-demand.
- B) Training is interruptible and can resume from a checkpoint, so the 60–90% Spot discount comes at low risk.
- C) Spot guarantees the job finishes sooner.
- D) Real-time endpoints require Spot.

---

**Q10.** Your inference feature gets unpredictable, low-volume, spiky traffic and can tolerate occasional cold-start latency. Which SageMaker serving mode fits best?

- A) Real-time endpoint.
- B) Serverless endpoint.
- C) Batch transform.
- D) A 24/7 fleet of on-demand instances.

---

**Q11.** A SageMaker real-time `ml.m5.large` endpoint costs ~$0.115/hour and runs 24/7. A Bedrock Haiku call for your task costs ~$0.000068. Roughly where is the monthly break-even traffic?

- A) ~1,000 requests/month.
- B) ~120,000 requests/month.
- C) ~1.2 million requests/month.
- D) ~120 million requests/month.

---

**Q12.** You need full-text search and a Kibana-style dashboard over the last 15 minutes of application logs. The right tool is:

- A) Athena.
- B) Redshift Spectrum.
- C) OpenSearch.
- D) Glue ETL.

---

**Q13.** Which IAM grant correctly follows least privilege for a Lambda that calls one specific SageMaker endpoint?

- A) `Action: "sagemaker:*"`, `Resource: "*"`.
- B) `Action: "sagemaker:InvokeEndpoint"`, `Resource: "arn:aws:sagemaker:us-east-1:1234:endpoint/iris-realtime"`.
- C) `Action: "*"`, `Resource: "arn:aws:sagemaker:*"`.
- D) `Action: "sagemaker:InvokeEndpoint"`, `Resource: "*"`.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — The Glue Data Catalog holds the database/table/partition metadata that every analytics engine reads through. It decouples storage from compute. (Lake Formation enforces *access* on the catalog but is not itself the metadata seam.)
2. **C** — Per byte scanned from S3, ~$5/TB in 2026, with a 10 MB minimum per query. This single fact drives every layout decision.
3. **B** — Partitioning lets the engine skip the prefixes that don't match `dt`; Parquet lets it read only the `country` column and prune row groups. Together they turn a multi-GB scan into a few-MB scan. Athena has no secondary indexes (A is nonsense); C and D don't reduce scan.
4. **B** — Projection computes partition values from a formula, so new `dt=` folders are queryable instantly with no `MSCK REPAIR` and no crawler.
5. **B** — `UPDATE_IN_DATABASE` lets a re-running crawler re-infer and mutate the schema. The fix is to crawl once for discovery, pin the table in IaC, and turn the crawler off (or set `UpdateBehavior: LOG`).
6. **B** — Columnar storage plus per-row-group min/max statistics enable column pruning and predicate pushdown. The other options are false.
7. **B** — Bedrock routes a single (Converse) request shape to many models chosen per request. The model is a parameter; the infrastructure is managed for you.
8. **B** — The Converse API is model-agnostic; swapping models is changing the `modelId` string. `InvokeModel` requires per-model bodies, partially giving up the router benefit.
9. **B** — Training resumes from checkpoints after a Spot interruption, so the large discount carries little risk. Spot is not faster (A/C) and is unrelated to endpoints (D).
10. **B** — Serverless scales to zero, costs nothing at idle, and tolerates spiky traffic at the price of cold starts — exactly this profile. Real-time wastes money at idle; batch/offline isn't request-path.
11. **C** — $0.115/hr × ~720 hr ≈ $83/month fixed; $83 / $0.000068 ≈ 1.2 million requests/month. Below that Bedrock wins; above it the always-on endpoint wins.
12. **C** — OpenSearch is the text-search/log-exploration tool. Athena and Redshift are for SQL-shaped analytics over columnar data; Glue ETL transforms data, it doesn't search it.
13. **B** — Specific action on a specific endpoint ARN. A and C are wildly over-broad; D over-grants on `Resource: "*"`. A Week-2 review fails A, C, and D.

</details>

---

If you scored under 9, re-read the lecture for the questions you missed — especially the bytes-scanned and break-even arithmetic, which the homework and challenge both lean on. If you scored 12 or 13, you're ready for the [homework](./homework.md).
