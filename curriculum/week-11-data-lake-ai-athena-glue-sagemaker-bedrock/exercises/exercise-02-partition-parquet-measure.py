#!/usr/bin/env python3
"""
Exercise 2 — Partition the data by date, convert it to Parquet, then re-query
and MEASURE the cost-and-latency improvement.

Estimated time: ~75 minutes.   Cost: cents (sub-GB Athena scans + a little S3).

WHAT THIS DOES
--------------
Building on Exercise 1's raw NDJSON table `events_raw.events`, this script:

  1. Creates a Parquet-backed, date-partitioned copy of the data with Athena
     CTAS (CREATE TABLE AS SELECT). One statement, no Glue ETL, no Spark.
  2. Creates a second external table over the same Parquet location that uses
     PARTITION PROJECTION, so new days work with no crawler and no MSCK REPAIR.
  3. Runs the SAME analytical query against (a) the raw JSON table and (b) the
     Parquet table, and prints a side-by-side table of bytes-scanned, runtime,
     and estimated dollars.

The headline outcome is the measurement table at the end: you should see the
Parquet/partitioned query scan a small fraction of the bytes of the raw query.

HOW TO RUN
----------
    python -m venv .venv && source .venv/bin/activate
    pip install boto3            # boto3 is the only dependency
    export REGION=us-east-1
    export ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    export LAKE_BUCKET="c19-wk11-lake-${ACCOUNT}"
    export RESULTS_BUCKET="c19-wk11-athena-results-${ACCOUNT}"
    python exercise-02-partition-parquet-measure.py

PREREQUISITE
------------
Exercise 1 must have created `events_raw.events` and populated the lake bucket.

ACCEPTANCE CRITERIA
-------------------
  [ ] A Parquet table `events_raw.events_parquet` exists under
      s3://<lake>/events_parquet/ , partitioned by dt.
  [ ] A projected table `events_raw.events_parquet_proj` answers queries with
      no crawler / no MSCK after new data lands.
  [ ] The script prints a measurement table comparing raw vs Parquet on the
      SAME query, and the Parquet scan is materially smaller.
  [ ] You can explain WHY each number is what it is (partition + column pruning).

SMOKE OUTPUT (your numbers will differ)
---------------------------------------
    === Measurement: SELECT country, count(*) ... GROUP BY country ===
    variant                 scanned_mb   runtime_s   est_usd
    raw_json                      3.33       1.61    0.0000166
    parquet_partitioned           0.31       0.74    0.0000016   (10 MB min applies)
    improvement                  10.7x       2.2x        ~10x
"""

from __future__ import annotations

import datetime as dt
import os
import time

import boto3

REGION = os.environ.get("REGION", "us-east-1")
ACCOUNT = os.environ["ACCOUNT"]
LAKE_BUCKET = os.environ.get("LAKE_BUCKET", f"c19-wk11-lake-{ACCOUNT}")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", f"c19-wk11-athena-results-{ACCOUNT}")
DATABASE = "events_raw"
OUTPUT_LOCATION = f"s3://{RESULTS_BUCKET}/"

# Athena standard-engine price as of 2026: ~$5 per TB scanned, 10 MB minimum/query.
PRICE_PER_TB = 5.0
MIN_SCAN_BYTES = 10 * 1024 * 1024  # 10 MB billed minimum

athena = boto3.client("athena", region_name=REGION)


def run_query(sql: str) -> dict:
    """Run an Athena query to completion and return its execution stats."""
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": OUTPUT_LOCATION},
    )["QueryExecutionId"]

    while True:
        execu = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = execu["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1.5)

    if state != "SUCCEEDED":
        reason = execu["Status"].get("StateChangeReason", "(no reason given)")
        raise RuntimeError(f"Query {state}: {reason}\nSQL: {sql}")

    stats = execu["Statistics"]
    return {
        "qid": qid,
        "scanned_bytes": stats.get("DataScannedInBytes", 0),
        "runtime_ms": stats.get("TotalExecutionTimeInMillis", 0),
    }


def billed_usd(scanned_bytes: int) -> float:
    billed = max(scanned_bytes, MIN_SCAN_BYTES)
    return billed / (1024**4) * PRICE_PER_TB


def fetch_first_rows(qid: str, n: int = 6) -> list[list[str]]:
    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"][: n + 1]
    return [[c.get("VarCharValue", "") for c in r["Data"]] for r in rows]


# The single analytical question we run against BOTH tables. Touches two columns
# (country) and aggregates -- exactly the shape Parquet column-pruning rewards.
ANALYTICAL_SQL = (
    "SELECT country, count(*) AS hits FROM {table} "
    "GROUP BY country ORDER BY hits DESC"
)


def step_1_ctas_to_parquet() -> None:
    """CTAS: read raw JSON, write Snappy Parquet partitioned by dt."""
    print("Step 1: CTAS raw JSON -> partitioned Parquet ...")
    # Drop any prior run so the script is idempotent.
    try:
        run_query("DROP TABLE IF EXISTS events_parquet")
    except RuntimeError:
        pass
    # Athena CTAS will not write into a non-empty location; clear it first.
    s3 = boto3.client("s3", region_name=REGION)
    paginator = s3.get_paginator("list_objects_v2")
    to_delete = []
    for page in paginator.paginate(Bucket=LAKE_BUCKET, Prefix="events_parquet/"):
        for obj in page.get("Contents", []):
            to_delete.append({"Key": obj["Key"]})
    for i in range(0, len(to_delete), 1000):
        s3.delete_objects(Bucket=LAKE_BUCKET, Delete={"Objects": to_delete[i : i + 1000]})

    ctas = f"""
        CREATE TABLE events_parquet
        WITH (
            format = 'PARQUET',
            parquet_compression = 'SNAPPY',
            partitioned_by = ARRAY['dt'],
            external_location = 's3://{LAKE_BUCKET}/events_parquet/'
        ) AS
        SELECT
            user_id,
            country,
            page,
            session_ms,
            -- fix the type the crawler punted on: parse the ISO string to a timestamp
            from_iso8601_timestamp(ts) AS event_ts,
            dt
        FROM events
    """
    stats = run_query(ctas)
    print(f"  CTAS wrote Parquet; it scanned {stats['scanned_bytes'] / 1e6:.2f} MB "
          f"of source JSON in {stats['runtime_ms'] / 1000:.2f}s.")


def step_2_projected_table() -> None:
    """An external table over the Parquet with PARTITION PROJECTION."""
    print("Step 2: create a partition-projected external table ...")
    run_query("DROP TABLE IF EXISTS events_parquet_proj")
    today = dt.date.today().isoformat()
    ddl = f"""
        CREATE EXTERNAL TABLE events_parquet_proj (
            user_id    string,
            country    string,
            page       string,
            session_ms int,
            event_ts   timestamp
        )
        PARTITIONED BY (dt string)
        STORED AS PARQUET
        LOCATION 's3://{LAKE_BUCKET}/events_parquet/'
        TBLPROPERTIES (
            'projection.enabled'          = 'true',
            'projection.dt.type'          = 'date',
            'projection.dt.range'         = '2026-01-01,{today}',
            'projection.dt.format'        = 'yyyy-MM-dd',
            'projection.dt.interval'      = '1',
            'projection.dt.interval.unit' = 'DAYS',
            'storage.location.template'   = 's3://{LAKE_BUCKET}/events_parquet/dt=${{dt}}/',
            'parquet.compression'         = 'SNAPPY'
        )
    """
    run_query(ddl)
    # Prove projection works WITHOUT any MSCK REPAIR / crawler:
    proof = run_query("SELECT count(*) AS rows_visible FROM events_parquet_proj")
    rows = fetch_first_rows(proof["qid"], n=1)
    print(f"  projected table sees {rows[1][0]} rows with no MSCK/crawler. Good.")


def step_3_measure() -> None:
    """Run the SAME query on raw JSON vs Parquet and tabulate the difference."""
    print("\n=== Measurement: SELECT country, count(*) ... GROUP BY country ===")
    raw = run_query(ANALYTICAL_SQL.format(table="events"))
    par = run_query(ANALYTICAL_SQL.format(table="events_parquet_proj"))

    def row(name: str, s: dict) -> str:
        return (f"{name:<24}{s['scanned_bytes'] / 1e6:>10.2f}"
                f"{s['runtime_ms'] / 1000:>12.2f}"
                f"{billed_usd(s['scanned_bytes']):>14.7f}")

    print(f"{'variant':<24}{'scanned_mb':>10}{'runtime_s':>12}{'est_usd':>14}")
    print(row("raw_json", raw))
    print(row("parquet_partitioned", par))

    scan_improve = (raw["scanned_bytes"] / par["scanned_bytes"]) if par["scanned_bytes"] else float("inf")
    time_improve = (raw["runtime_ms"] / par["runtime_ms"]) if par["runtime_ms"] else float("inf")
    print(f"{'improvement':<24}{scan_improve:>9.1f}x{time_improve:>11.1f}x"
          f"{'  (10 MB min on small tables)':>0}")

    print("\nWhy: Parquet stores columns separately, so the GROUP BY country")
    print("query reads only the country column's data and row-group metadata,")
    print("not every field of every row as the JSON scan must. On small lab")
    print("data the 10 MB billed minimum hides some of the win; on real")
    print("multi-GB data the same shape produces 50-400x scan reductions.")


def main() -> None:
    print(f"Region={REGION}  Database={DATABASE}  Lake=s3://{LAKE_BUCKET}\n")
    step_1_ctas_to_parquet()
    step_2_projected_table()
    step_3_measure()
    print("\nDone. Record the measurement table in your cost report.")


if __name__ == "__main__":
    main()
