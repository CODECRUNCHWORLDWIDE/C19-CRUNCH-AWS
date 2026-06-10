# Exercise 1 — CUR → Athena → QuickSight by Tag

> **Estimated time:** ~75 minutes of work, plus an **up-to-24-hour wait** for the first Cost & Usage Report file to land. **Cost:** cents (a little S3 for the CUR, sub-GB Athena scans) plus your QuickSight edition (trial is free).

## Goal

Create a Cost & Usage Report, land it in S3, catalogue it with Glue, and query your AWS spend **broken down by your `team` cost allocation tag** in Athena — including the number that matters most: your **untagged spend**. Then surface it in a QuickSight dashboard. The headline outcome: you can answer "what did each team cost last month, and how much of the bill can I not yet allocate?" from the billing ledger, not a guess.

This is the FinOps "Inform" loop made real. Every optimization later this week depends on this allocation existing.

## Prerequisites

- AWS CLI v2 configured (`aws sts get-caller-identity` returns your account).
- Permissions for `cur`/Data Exports, S3, Glue, Athena, and QuickSight.
- **You created the CUR on Monday** (this exercise's Step 1) so the data has landed by the time you do Steps 2+. If you're doing this all in one sitting, create the CUR first, then come back tomorrow for the query steps.
- Your `team`, `service`, `environment` cost allocation tags **activated** in the Billing console (Billing → Cost allocation tags). Activation is not retroactive.
- `jq` installed. Region for the CUR is **`us-east-1`** (CUR is a us-east-1-only API), even if your workloads run elsewhere.

## Acceptance criteria

- [ ] A Cost & Usage Report (`c19-wk14-cur`) delivers Parquet files to `s3://<your-cur-bucket>/cur/`.
- [ ] A Glue database and a crawler-created (or IaC) table over the CUR exist.
- [ ] An Athena query returns spend grouped by the `team` tag for the current billing period.
- [ ] You have recorded the **untagged spend** figure (the `NULL`/empty-`team` total) and what percent of the bill it is.
- [ ] A QuickSight dashboard (or Grafana panel) shows cost by `team` and a single "untagged" number.

---

## Step 1 — Create the CUR (do this Monday)

Create the bucket, attach the billing-service bucket policy, and define the report.

```bash
export REGION=us-east-1   # CUR is us-east-1 only
export ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CUR_BUCKET="c19-wk14-cur-${ACCOUNT}"
export RESULTS_BUCKET="c19-wk14-athena-results-${ACCOUNT}"

aws s3 mb "s3://${CUR_BUCKET}" --region "${REGION}"
aws s3 mb "s3://${RESULTS_BUCKET}" --region "${REGION}"

aws s3api put-public-access-block --bucket "${CUR_BUCKET}" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

The billing service principal must be allowed to write report objects into the bucket:

```bash
cat > cur-bucket-policy.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBillingReportsRead",
      "Effect": "Allow",
      "Principal": { "Service": "billingreports.amazonaws.com" },
      "Action": ["s3:GetBucketAcl", "s3:GetBucketPolicy"],
      "Resource": "arn:aws:s3:::${CUR_BUCKET}"
    },
    {
      "Sid": "AllowBillingReportsWrite",
      "Effect": "Allow",
      "Principal": { "Service": "billingreports.amazonaws.com" },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${CUR_BUCKET}/*"
    }
  ]
}
JSON

aws s3api put-bucket-policy --bucket "${CUR_BUCKET}" --policy file://cur-bucket-policy.json
```

Now define the report. `RESOURCES` adds the per-resource-ID column (needed for per-resource allocation); `Parquet` keeps Athena scans cheap; `OVERWRITE_REPORT` stops the bucket bloating with monthly copies.

```bash
aws cur put-report-definition --region "${REGION}" --report-definition "{
  \"ReportName\": \"c19-wk14-cur\",
  \"TimeUnit\": \"HOURLY\",
  \"Format\": \"Parquet\",
  \"Compression\": \"Parquet\",
  \"AdditionalSchemaElements\": [\"RESOURCES\"],
  \"S3Bucket\": \"${CUR_BUCKET}\",
  \"S3Prefix\": \"cur\",
  \"S3Region\": \"${REGION}\",
  \"AdditionalArtifacts\": [\"ATHENA\"],
  \"RefreshClosedReports\": true,
  \"ReportVersioning\": \"OVERWRITE_REPORT\"
}"
```

`"AdditionalArtifacts": ["ATHENA"]` tells AWS to also drop a ready-made Glue/Athena integration (a crawler and an `AWS::Glue` setup) alongside the data, which saves you writing the table by hand. **Now wait.** The first file lands within ~24 hours. Verify later with:

```bash
aws s3 ls "s3://${CUR_BUCKET}/cur/" --recursive | tail
```

## Step 2 — Catalogue the CUR with Glue (do this Tuesday, after data lands)

With the `ATHENA` artifact, AWS ships a crawler/Glue setup in the bucket; run it. (If you prefer, point a plain Glue crawler at the data prefix exactly as you did in Week 11 — the CUR is just Parquet in S3.)

```bash
# Option A: run the AWS-provided crawler that the ATHENA artifact created
# (its name is in the bucket's cur/.../crawler-cfn.yml or visible in the Glue console).
aws glue start-crawler --name "c19-wk14-cur-crawler" 2>/dev/null || \
  echo "If the named crawler doesn't exist, create one over s3://${CUR_BUCKET}/cur/ as in Week 11."

# Poll to READY:
while [ "$(aws glue get-crawler --name c19-wk14-cur-crawler --query 'Crawler.State' --output text 2>/dev/null)" = "RUNNING" ]; do
  echo "crawler running..."; sleep 15
done
```

Find the database and table name the crawler created:

```bash
aws glue get-databases --query "DatabaseList[?contains(Name, 'cur')].Name"
aws glue get-tables --database-name athenacurcfn_c19_wk14_cur \
  --query 'TableList[*].Name' 2>/dev/null
```

(The exact database/table names depend on the report name; substitute what your account shows. We'll call them `CURDB` and `CURTBL` below.)

```bash
export CURDB="athenacurcfn_c19_wk14_cur"   # adjust to your actual db
export CURTBL="c19_wk14_cur"               # adjust to your actual table
```

## Step 3 — Query spend by team, and find your untagged number

Set Athena's result location, then run the allocation query. **Column names differ between legacy CUR and CUR 2.0** — confirm yours with `SHOW COLUMNS` first.

```bash
# Inspect the columns so you use the right names for your CUR version.
QID=$(aws athena start-query-execution \
  --query-string "SHOW COLUMNS IN ${CURDB}.${CURTBL}" \
  --result-configuration "{\"OutputLocation\": \"s3://${RESULTS_BUCKET}/\"}" \
  --query 'QueryExecutionId' --output text)
sleep 5
aws athena get-query-results --query-execution-id "$QID" \
  --query 'ResultSet.Rows[*].Data[0].VarCharValue' --output text | grep -i team
```

You're looking for the tag column, which in legacy CUR is `resource_tags_user_team` and in CUR 2.0 is accessed as `resource_tags['user_team']`. The spend-by-team query (legacy CUR column form shown; adapt to yours):

```bash
read -r -d '' SQL <<SQL
SELECT
  COALESCE(NULLIF(resource_tags_user_team, ''), '(untagged)') AS team,
  ROUND(SUM(line_item_unblended_cost), 2)                     AS cost_usd
FROM ${CURDB}.${CURTBL}
WHERE line_item_line_item_type = 'Usage'
GROUP BY 1
ORDER BY cost_usd DESC
SQL

QID=$(aws athena start-query-execution \
  --query-string "$SQL" \
  --result-configuration "{\"OutputLocation\": \"s3://${RESULTS_BUCKET}/\"}" \
  --query 'QueryExecutionId' --output text)

while true; do
  STATE=$(aws athena get-query-execution --query-execution-id "$QID" \
    --query 'QueryExecution.Status.State' --output text)
  [ "$STATE" = "SUCCEEDED" ] && break
  [ "$STATE" = "FAILED" ] && { aws athena get-query-execution --query-execution-id "$QID" \
    --query 'QueryExecution.Status.StateChangeReason'; exit 1; }
  sleep 2
done

aws athena get-query-results --query-execution-id "$QID" \
  --query 'ResultSet.Rows[*].Data[*].VarCharValue' --output text
```

**Record the `(untagged)` row.** Divide it by the total to get your untagged percentage. This number is the headline of the exercise: it is the fraction of your bill you currently *cannot* allocate to a team, and it caps your FinOps maturity. The first time most people run this, the untagged share is alarming — data transfer, marketplace charges, and resources created before tagging discipline all land here.

## Step 4 — Build the QuickSight dashboard

In the QuickSight console:

1. **Connect a dataset** to Athena → select `CURDB.CURTBL` (or, better, a curated view you create from the Step-3 query with `CREATE VIEW`).
2. **SPICE vs direct query:** import a curated, aggregated view into SPICE (QuickSight's cache) so the dashboard is fast and doesn't re-scan the CUR on every render. Aggregating *before* import keeps both the Athena scan and the SPICE footprint small.
3. **Build three visuals:**
   - A **bar chart**: `cost_usd` by `team`.
   - A **stacked area** over `line_item_usage_start_date` (by day) split by `product_servicecode` — cost over time by service.
   - A **KPI / big number**: total `(untagged)` spend, so the tag-debt is impossible to ignore.
4. **Publish** the dashboard and note the URL. That dashboard is the FinOps deliverable the capstone reuses.

> **No QuickSight?** Use Grafana with the Athena data source plugin and build the same three panels against the same SQL. The point is the visualization on top of the CUR, not the specific tool.

## Expected output

```
(untagged)      412.55
ml              206.18
checkout        148.90
platform         97.42
web              61.07
```

Your teams and figures will differ, but the shape is what matters: a ranked list of per-team spend with an `(untagged)` bucket that is too large the first time. (Here untagged is ~$412 of a ~$926 total ≈ **45% untagged** — a typical, sobering first number.)

## Cleanup (end-of-session)

Keep the CUR and the Glue table — the mini-project reuses them, and the CUR keeps accumulating useful history. The only things to consider stopping:

```bash
# If you used a one-off crawler with a schedule, there isn't one (we ran on demand).
# QuickSight: if you only have a trial and want to stop billing, cancel the subscription
# from QuickSight -> Manage QuickSight -> Account settings before the trial converts.
echo "Leave the CUR running; it is cheap and the history is the point."
```

## Inline hints

- *The CUR bucket is empty after 24h* — re-check the bucket policy (the `billingreports.amazonaws.com` principal must have `s3:PutObject`), and confirm the report shows under Billing → Cost & Usage Reports. A bad policy silently drops deliveries.
- *Athena query "column does not exist"* — your CUR version uses different column names. Run `SHOW COLUMNS` and adapt; CUR 2.0 uses `resource_tags['user_team']` map access rather than a flat `resource_tags_user_team` column.
- *Untagged spend is ~100%* — your tags aren't *activated* as cost allocation tags (different from just existing on the resource), or you activated them after the data was generated (activation isn't retroactive). Activate now; the next period allocates.
- *QuickSight can't see Athena* — QuickSight needs permission to the Athena workgroup and the S3 results/CUR buckets; grant it under Manage QuickSight → Security & permissions.
- *The numbers don't match the AWS Console bill* — you probably included `Tax`/`Credit`/`Refund`/`Fee` line types. Filter to `line_item_line_item_type = 'Usage'` for "what running things cost," or sum all types for the gross invoice number.
