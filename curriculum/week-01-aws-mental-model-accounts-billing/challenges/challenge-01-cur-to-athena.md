# Challenge 1 — Cost & Usage Report → S3 → Athena

**Time estimate:** ~120 minutes.

**Cost:** A few cents, total. The S3 storage for the CUR is fractions of a cent. Athena charges per TB scanned (~$5/TB); your queries scan a few MB, so each query costs a small fraction of a cent. We tell you how to keep scans tiny.

## Problem statement

Prove billing observability *before any compute exists*. You will:

1. Configure a **Cost & Usage Report** (via the modern **Data Exports / CUR 2.0** path) that delivers to an **S3 bucket** you own, in **Parquet**, partitioned by month.
2. Register the CUR data in **Athena** using **partition projection** (so you do not run a crawler).
3. Write SQL that answers two questions:
   - **Spend by service** for the current month, descending.
   - **Spend by a cost-allocation tag** (e.g. `team` or `environment`), descending.

The deliverable is a short report (`challenge-01/REPORT.md`) containing your bucket name, your Athena DDL, your two queries, and the actual (tiny) numbers they returned, plus a paragraph on what you learned about your account's cost shape.

> **Why this matters.** When a later week's lab racks up an unexpected $30, this pipeline is how you find out *which service and which tagged resource* did it — in one SQL query, not by squinting at the console. This is the FinOps foundation. Week 14 turns it into a QuickSight dashboard; Week 1 builds the plumbing.

---

## Step 1 — Create the destination bucket

The CUR must land in an S3 bucket with a bucket policy that lets the billing service write to it. Create the bucket in the **management account** (it owns consolidated billing).

```bash
export AWS_PROFILE=mgmt-admin
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="cur-${ACCOUNT_ID}-$(date +%Y)"
REGION="eu-west-1"

aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$REGION" \
  --create-bucket-configuration LocationConstraint="$REGION"

# Block all public access (always, for any bucket).
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

The Data Exports console step (next) can attach the required bucket policy for you — accept that, or attach it yourself from the policy the console shows. The policy grants `billingreports.amazonaws.com` / `bcm-data-exports.amazonaws.com` permission to `s3:PutObject` into the bucket. Do **not** make the bucket public.

---

## Step 2 — Create the Cost & Usage Report (Data Exports)

The CUR is configured from the **Billing and Cost Management** console (Data Exports). Console is the supported path; the API exists but the console attaches the bucket policy and validates for you.

1. Console → **Billing and Cost Management** → **Data Exports** → **Create**.
2. Choose **Standard data export** (CUR 2.0).
3. Name it `crunch-cur`.
4. Include **resource IDs** and enable **split cost allocation data** if offered (you want resource-level granularity for tag breakdowns).
5. **Time granularity:** Daily (hourly is overkill and costs more to scan).
6. **Compression / format:** **Parquet** (much cheaper to scan in Athena than CSV/gzip).
7. **S3 destination:** the bucket from Step 1, prefix `cur/`.
8. Accept the bucket-policy snippet the console offers, or apply it yourself.
9. Create.

The first CUR file can take **up to 24 hours** to appear. AWS backfills the current month. **Start this step early in the week** — do not leave it for Friday afternoon, or you will have no data to query.

While you wait, you can build the Athena DDL (Step 3) so you're ready the moment data lands.

---

## Step 3 — Register the data in Athena with partition projection

Open **Athena** (same Region as the bucket). Set a query-results location once (Athena needs an S3 path to write results — a separate small prefix is fine):

```sql
-- Run once in the Athena console settings, or:
-- Settings -> Manage -> Query result location: s3://<your-bucket>/athena-results/
```

Create a database and an **external table** over the CUR Parquet, using **partition projection** so you never run a crawler. The column set below matches the CUR 2.0 schema; the exact columns AWS emits are listed in the `*-Manifest.json` next to your data — adjust names to match your manifest.

```sql
CREATE DATABASE IF NOT EXISTS crunch_billing;

CREATE EXTERNAL TABLE IF NOT EXISTS crunch_billing.cur (
  line_item_usage_account_id   string,
  line_item_product_code       string,
  line_item_line_item_type     string,
  line_item_usage_start_date   timestamp,
  line_item_unblended_cost     double,
  product_servicecode          string,
  -- one column per cost-allocation tag you activated, prefixed `resource_tags_`:
  resource_tags_user_team      string,
  resource_tags_user_environment string
)
PARTITIONED BY (
  billing_period string
)
STORED AS PARQUET
LOCATION 's3://REPLACE_WITH_YOUR_BUCKET/cur/crunch-cur/data/'
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.billing_period.type' = 'date',
  'projection.billing_period.format' = 'yyyy-MM',
  'projection.billing_period.range' = '2026-01,NOW',
  'projection.billing_period.interval' = '1',
  'projection.billing_period.interval.unit' = 'MONTHS',
  'storage.location.template' =
    's3://REPLACE_WITH_YOUR_BUCKET/cur/crunch-cur/data/BILLING_PERIOD=${billing_period}/'
);
```

> **Activate the tags first.** A CUR only contains the `resource_tags_user_*` columns for tags you have **activated** as cost-allocation tags (Billing console → Cost allocation tags → activate `team`, `environment`, etc.). Activation is not retroactive and takes ~24h to populate. If you have no tagged resources yet, the tag query will return one big `null`/`(untagged)` bucket — which is itself the correct, honest answer for an account with no compute. Tag something cheap (an S3 object's bucket, the CUR bucket itself) to see a non-null row.

---

## Step 4 — The two queries

**Spend by service, current month, descending:**

```sql
SELECT
  product_servicecode               AS service,
  ROUND(SUM(line_item_unblended_cost), 4) AS cost_usd
FROM crunch_billing.cur
WHERE billing_period = date_format(current_date, '%Y-%m')
  AND line_item_line_item_type = 'Usage'
GROUP BY product_servicecode
ORDER BY cost_usd DESC;
```

**Spend by the `team` tag, current month, descending (untagged rolled into one bucket):**

```sql
SELECT
  COALESCE(NULLIF(resource_tags_user_team, ''), '(untagged)') AS team,
  ROUND(SUM(line_item_unblended_cost), 4) AS cost_usd
FROM crunch_billing.cur
WHERE billing_period = date_format(current_date, '%Y-%m')
  AND line_item_line_item_type = 'Usage'
GROUP BY COALESCE(NULLIF(resource_tags_user_team, ''), '(untagged)')
ORDER BY cost_usd DESC;
```

Keep scans tiny by always filtering on `billing_period` (the projected partition) so Athena reads only the current month's Parquet, not the whole history.

---

## Acceptance criteria

- [ ] A CUR named `crunch-cur` delivers Parquet into your S3 bucket under `cur/`, partitioned by month. Block Public Access is **on**.
- [ ] An Athena external table (`crunch_billing.cur`) reads the CUR with **partition projection** — no Glue crawler.
- [ ] The **spend-by-service** query runs and returns rows (even if cents).
- [ ] The **spend-by-tag** query runs and returns rows, with untagged spend rolled into `(untagged)`.
- [ ] `challenge-01/REPORT.md` is committed and contains: bucket name (redact the account id if you like), the DDL, both queries, the actual returned numbers, and a paragraph interpreting your account's cost shape.
- [ ] You can state, in one sentence, why partition projection is cheaper than a crawler + full-table scan.

## Stretch

- Add a third query: **daily spend trend** for the month (`GROUP BY date_trunc('day', line_item_usage_start_date)`), and eyeball it for anomalies.
- Turn on **Cost Anomaly Detection** with a `$10` monitor and compare what it flags against your Athena trend.
- Express the whole pipeline as **IaC**: the bucket + bucket policy + the Data Export in CloudFormation or CDK (`AWS::CUR::ReportDefinition` or the BCM Data Exports resource), so a teammate can `cdk deploy` the billing observability stack. Commit it under `challenge-01/iac/`.
- Parameterize the table over **all** activated tags, not just `team`, and write a query that shows, per service, the top tagged owner.

## Hints

<details>
<summary>No data after I created the CUR</summary>

The first delivery can take up to 24 hours. Confirm files are landing with `aws s3 ls s3://<bucket>/cur/crunch-cur/data/ --recursive`. If the prefix is empty after a day, recheck the bucket policy (the billing service must be allowed `s3:PutObject`) and that the export status is "Healthy" in the Data Exports console.

</details>

<details>
<summary>Athena returns zero rows but files exist</summary>

Almost always a `LOCATION` / `storage.location.template` mismatch. Open one of the data files' paths with `aws s3 ls` and make the template's `BILLING_PERIOD=${billing_period}` segment match the actual S3 key layout exactly (CUR 2.0 uses `BILLING_PERIOD=YYYY-MM/`). Also confirm `projection.billing_period.range` starts at or before the month you're querying.

</details>

<details>
<summary>My tag columns don't exist</summary>

You must (1) activate the tags as cost-allocation tags in the Billing console, (2) wait ~24h, and (3) have resources actually carrying those tags. The column name is the tag key prefixed with `resource_tags_user_` and lowercased/underscored (e.g. tag `team` → `resource_tags_user_team`). Check your CUR manifest JSON for the exact emitted column names.

</details>

## Submission

Commit your `challenge-01/` folder (REPORT.md, the Athena DDL as a `.sql` file, and any IaC from the stretch) to your Week 1 GitHub repo. Redact your raw account id if you prefer. The graded artifact is the working pipeline and a report that demonstrates you can answer "what is this costing, and who owns it?" from data — the FinOps muscle the rest of the course relies on.

## Why this matters

Every later week ends with a cost report. The capstone is graded in part on a real dollar number with a tagged breakdown. The CUR → Athena pipeline you build here is the single source of truth for all of it. Teams that skip this discover, three weeks later, that they have no idea what their EKS cluster cost — and have to retrofit observability under pressure. You are building it now, calmly, before there is anything expensive to observe.
