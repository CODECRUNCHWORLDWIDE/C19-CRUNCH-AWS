# Exercise 1 — Firehose → Glue → Athena

> **Estimated time:** ~75 minutes. **Cost:** a few cents (S3 storage, < 1 GB Firehose ingest, one short Glue crawler, sub-GB Athena scans).

## Goal

Land newline-delimited JSON (NDJSON) clickstream events into S3 through a Kinesis Data Firehose delivery stream, catalogue the raw data with a Glue crawler, and run your first Athena queries against it. The headline outcome: you read the **Data scanned** number on the Athena query footer and understand that it is your bill.

This is the "raw lake" baseline. Exercise 2 makes it cheap; this exercise makes it *exist* and gives you the expensive number to improve on.

## Prerequisites

- AWS CLI v2 configured (`aws sts get-caller-identity` returns your account).
- Permissions for S3, Firehose, Glue, and Athena.
- `jq` installed (for reading CLI JSON output).
- Region `us-east-1` assumed; substitute consistently if you use another.

## Acceptance criteria

- [ ] A Firehose delivery stream delivers records to `s3://<your-lake>/events/dt=YYYY-MM-DD/...`.
- [ ] A Glue database `events_raw` and a crawler-created table exist over the raw prefix.
- [ ] You can run an Athena `SELECT count(*)` and a `GROUP BY country` over the table.
- [ ] You have recorded the **Data scanned** figure for a full-table aggregation. (You'll beat it in Exercise 2.)
- [ ] You read the crawler's inferred schema and noted at least one type it got "wrong" (e.g. a timestamp typed as `string`).

---

## Step 1 — Create the lake bucket and an Athena results bucket

Athena needs somewhere to write query results; keep it separate from the data prefix.

```bash
export REGION=us-east-1
export ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export LAKE_BUCKET="c19-wk11-lake-${ACCOUNT}"
export RESULTS_BUCKET="c19-wk11-athena-results-${ACCOUNT}"

aws s3 mb "s3://${LAKE_BUCKET}" --region "${REGION}"
aws s3 mb "s3://${RESULTS_BUCKET}" --region "${REGION}"

# Block public access on the lake bucket (always).
aws s3api put-public-access-block \
  --bucket "${LAKE_BUCKET}" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## Step 2 — Create the Firehose delivery role and stream

Firehose needs a role it can assume to write to your bucket. Create the trust policy and a least-privilege write policy.

```bash
cat > firehose-trust.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "firehose.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
JSON

aws iam create-role \
  --role-name c19-wk11-firehose-role \
  --assume-role-policy-document file://firehose-trust.json

cat > firehose-policy.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetBucketLocation", "s3:ListBucket"],
    "Resource": [
      "arn:aws:s3:::${LAKE_BUCKET}",
      "arn:aws:s3:::${LAKE_BUCKET}/*"
    ]
  }]
}
JSON

aws iam put-role-policy \
  --role-name c19-wk11-firehose-role \
  --policy-name s3-write \
  --policy-document file://firehose-policy.json

export FIREHOSE_ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/c19-wk11-firehose-role"
```

Now create the delivery stream with a Hive-style date prefix so Athena can partition later. (IAM role propagation can lag a few seconds; if the next call errors with "cannot assume role," wait 10 seconds and retry.)

```bash
aws firehose create-delivery-stream \
  --delivery-stream-name c19-wk11-events \
  --delivery-stream-type DirectPut \
  --extended-s3-destination-configuration "{
    \"RoleARN\": \"${FIREHOSE_ROLE_ARN}\",
    \"BucketARN\": \"arn:aws:s3:::${LAKE_BUCKET}\",
    \"Prefix\": \"events/dt=!{timestamp:yyyy-MM-dd}/\",
    \"ErrorOutputPrefix\": \"errors/!{firehose:error-output-type}/dt=!{timestamp:yyyy-MM-dd}/\",
    \"BufferingHints\": { \"SizeInMBs\": 1, \"IntervalInSeconds\": 60 },
    \"CompressionFormat\": \"UNCOMPRESSED\"
  }"
```

We use a tiny 1 MB / 60 s buffer here *only* so the lab data lands fast. In Lecture 1 we said small buffers make tiny files — that is fine for the lab, deliberately not fine for production.

## Step 3 — Generate and push events

Here is a generator that pushes NDJSON click events into Firehose. Save it as `gen_events.py`.

```python
import json
import random
import time
import boto3

fh = boto3.client("firehose", region_name="us-east-1")
STREAM = "c19-wk11-events"

COUNTRIES = ["US", "JP", "DE", "BR", "IN", "GB"]
PAGES = ["/", "/pricing", "/docs", "/blog", "/signup", "/checkout"]

def make_event() -> dict:
    return {
        "user_id": f"u{random.randint(1, 5000):05d}",
        "country": random.choice(COUNTRIES),
        "page": random.choice(PAGES),
        "session_ms": random.randint(50, 30000),
        # NDJSON record: one JSON object + newline so Athena reads it as one row.
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

def main(n: int = 20000, batch: int = 500) -> None:
    sent = 0
    while sent < n:
        records = [
            {"Data": (json.dumps(make_event()) + "\n").encode("utf-8")}
            for _ in range(min(batch, n - sent))
        ]
        fh.put_record_batch(DeliveryStreamName=STREAM, Records=records)
        sent += len(records)
        print(f"sent {sent}/{n}")
    print("done; allow up to ~60s for Firehose to flush to S3")

if __name__ == "__main__":
    main()
```

Run it, then wait for the buffer to flush:

```bash
python gen_events.py
# wait ~70 seconds for the 60s buffer interval to trigger a flush
aws s3 ls "s3://${LAKE_BUCKET}/events/" --recursive | head
```

You should see objects under `events/dt=YYYY-MM-DD/`. If you see nothing after 90 seconds, check `errors/` — a delivery failure landed there, and the error-output type tells you why.

## Step 4 — Crawl with Glue

Create a Glue database and a crawler over the raw prefix. The crawler needs its own role.

```bash
cat > glue-trust.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "glue.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
JSON

aws iam create-role --role-name c19-wk11-glue-role \
  --assume-role-policy-document file://glue-trust.json
aws iam attach-role-policy --role-name c19-wk11-glue-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole
aws iam put-role-policy --role-name c19-wk11-glue-role \
  --policy-name lake-read --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:GetObject\", \"s3:ListBucket\"],
      \"Resource\": [\"arn:aws:s3:::${LAKE_BUCKET}\", \"arn:aws:s3:::${LAKE_BUCKET}/*\"]
    }]
  }"

aws glue create-database --database-input '{"Name": "events_raw"}'

aws glue create-crawler \
  --name c19-wk11-crawler \
  --role "arn:aws:iam::${ACCOUNT}:role/c19-wk11-glue-role" \
  --database-name events_raw \
  --targets "{\"S3Targets\": [{\"Path\": \"s3://${LAKE_BUCKET}/events/\"}]}" \
  --schema-change-policy '{"UpdateBehavior":"LOG","DeleteBehavior":"LOG"}'

aws glue start-crawler --name c19-wk11-crawler

# Poll until it returns to READY (usually 1-2 minutes).
while [ "$(aws glue get-crawler --name c19-wk11-crawler --query 'Crawler.State' --output text)" != "READY" ]; do
  echo "crawler running..."; sleep 15
done
echo "crawler done"
```

Inspect the inferred schema. **Read it critically.**

```bash
aws glue get-tables --database-name events_raw \
  --query 'TableList[0].StorageDescriptor.Columns'
```

You will see `ts` typed as `string`, not `timestamp` — the crawler could not be sure the string was a timestamp, so it played safe. Note that down; it is the kind of thing you fix by hand in Exercise 2. You will also see `dt` recognized as a partition key because of the `dt=` prefix.

## Step 5 — Query with Athena and read the footer

Point Athena at the results bucket and run a query. The CLI flow is: start the query, poll for completion, read the stats.

```bash
QID=$(aws athena start-query-execution \
  --query-string "SELECT country, count(*) AS hits FROM events_raw.events GROUP BY country ORDER BY hits DESC;" \
  --query-execution-context '{"Database": "events_raw"}' \
  --result-configuration "{\"OutputLocation\": \"s3://${RESULTS_BUCKET}/\"}" \
  --query 'QueryExecutionId' --output text)

# Poll
while true; do
  STATE=$(aws athena get-query-execution --query-execution-id "$QID" \
    --query 'QueryExecution.Status.State' --output text)
  [ "$STATE" = "SUCCEEDED" ] && break
  [ "$STATE" = "FAILED" ] && { echo "query failed"; aws athena get-query-execution --query-execution-id "$QID" --query 'QueryExecution.Status.StateChangeReason'; exit 1; }
  sleep 2
done

# The number that matters:
aws athena get-query-execution --query-execution-id "$QID" \
  --query 'QueryExecution.Statistics.{DataScannedBytes:DataScannedInBytes, RuntimeMs:TotalExecutionTimeInMillis}'

# The results:
aws athena get-query-results --query-execution-id "$QID" \
  --query 'ResultSet.Rows[*].Data[*].VarCharValue' --output text
```

**Record the `DataScannedBytes`.** Because the raw data is uncompressed JSON and the table is read in full for a `GROUP BY` with no partition filter, you are scanning essentially the whole dataset. Convert it to dollars: `bytes / 1e12 × $5`. That is your baseline.

## Expected output

```
{
    "DataScannedBytes": 3489120,
    "RuntimeMs": 1640
}
US      3402
JP      3361
DE      3340
IN      3309
GB      3299
BR      3289
```

Your exact byte count and counts will differ (the generator is random and Firehose batches vary), but the shape is: a full-table scan in the low single-digit megabytes for 20k events, run time around 1–2 seconds. Hold this number. In Exercise 2 you will run the *same* analytical question for a fraction of the bytes.

## Cleanup (end-of-session)

Leave the lake bucket and table — Exercise 2 needs them. But stop the data faucet and the crawler schedule:

```bash
# There is no schedule on the crawler (we ran it on demand), so nothing to disable.
# Optionally delete the Firehose stream so it can't be re-triggered:
aws firehose delete-delivery-stream --delivery-stream-name c19-wk11-events
```

## Inline hints

- *"Cannot assume role" on Firehose create* — IAM propagation lag. Wait 10 seconds, retry the `create-delivery-stream`.
- *Crawler created zero tables* — Firehose hadn't flushed yet, so the prefix was empty when you crawled. Confirm objects exist with `aws s3 ls`, then re-run the crawler.
- *Athena query "FAILED: database does not exist"* — you passed the wrong database name; it is `events_raw`, and the table name is whatever the crawler chose (usually `events`). Check with `aws glue get-tables --database-name events_raw --query 'TableList[*].Name'`.
- *`ts` is a string and you want to do date math* — `CAST(from_iso8601_timestamp(ts) AS timestamp)`. We fix the type properly in Exercise 2.
