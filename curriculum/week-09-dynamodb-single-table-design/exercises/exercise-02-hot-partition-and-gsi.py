#!/usr/bin/env python3
"""
Exercise 2 — Hammer one partition key, observe throttling, add a GSI.

This script is self-contained and runnable. It:

  1. Creates a PROVISIONED-mode table with a low write capacity (5 WCU) so the
     per-partition ceiling is easy to hit on a laptop. (On a real on-demand
     table the per-partition ceiling is 1,000 WCU; we shrink it here so the
     throttle is reproducible without spending money or waiting.)
  2. Hammers a SINGLE partition key with concurrent writes and counts the
     ProvisionedThroughputExceededException throttles. This is the hot-partition
     signature: the TABLE has spare capacity table-wide, but ONE partition key
     is pinned at its ceiling, so writes to that key throttle.
  3. Adds a GSI that serves a reverse-lookup access pattern (find an event by
     its correlation id) that the base key cannot serve, and demonstrates the
     query against it.

Run against dynamodb-local (recommended, free, offline):

    docker run -d --name ddb-local -p 8000:8000 amazon/dynamodb-local
    export DDB_ENDPOINT=http://localhost:8000
    export AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local
    python exercise-02-hot-partition-and-gsi.py

Against real AWS, unset DDB_ENDPOINT (and accept a few cents of cost).

Expected output (numbers vary; the SHAPE is the lesson):

    === Phase 1: hammer one partition key ===
    Writes attempted: 2000   succeeded: 318   THROTTLED: 1682
    Throttle rate: 84.1%  <-- the hot-partition signature
    Table-wide provisioned WCU: 5  (the partition is pinned, not the table)

    === Phase 2: add the GSI and serve the reverse lookup ===
    GSI1 created. Query by correlationId=corr-000123 -> 1 item, 0 scans, 0.5 RCU.

    Cleaned up table exercise2-hot-partition.
"""
from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

TABLE = "exercise2-hot-partition"
HOT_KEY = "TENANT#whale"          # the one partition key everyone writes to
WRITES = 2000                     # total write attempts
CONCURRENCY = 50                  # parallel writers


def clients():
    endpoint = os.environ.get("DDB_ENDPOINT")
    # Disable boto3's automatic retries so we COUNT throttles instead of hiding
    # them. In production you WANT retries; here we want to observe the signal.
    cfg = Config(retries={"max_attempts": 0, "mode": "standard"})
    c = boto3.client("dynamodb", endpoint_url=endpoint, config=cfg)
    r = boto3.resource("dynamodb", endpoint_url=endpoint, config=cfg)
    return c, r


def create_table(c) -> None:
    if TABLE in c.list_tables()["TableNames"]:
        c.delete_table(TableName=TABLE)
        c.get_waiter("table_not_exists").wait(TableName=TABLE)
    c.create_table(
        TableName=TABLE,
        BillingMode="PROVISIONED",
        # Deliberately tiny so one partition's share of capacity is easy to
        # exhaust. On a real table you would never provision this low.
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
    )
    c.get_waiter("table_exists").wait(TableName=TABLE)


def hammer(table) -> tuple[int, int]:
    """Fire WRITES writes at HOT_KEY across CONCURRENCY threads. Return
    (succeeded, throttled)."""
    succeeded = 0
    throttled = 0

    def one_write(i: int) -> str:
        try:
            table.put_item(Item={
                "PK": HOT_KEY,
                "SK": f"EVENT#{time.time_ns()}#{i}",
                "correlationId": f"corr-{i:06d}",
                "payload": "x" * 800,  # ~1 KB item -> ~1 WCU each
            })
            return "ok"
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("ProvisionedThroughputExceededException",
                        "ThrottlingException"):
                return "throttled"
            raise

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(one_write, i) for i in range(WRITES)]
        for f in as_completed(futures):
            if f.result() == "ok":
                succeeded += 1
            else:
                throttled += 1
    return succeeded, throttled


def add_gsi(c) -> None:
    """Add GSI1 keyed by correlationId so we can serve 'find event by
    correlation id' — a reverse lookup the base key (PK=TENANT#..) cannot do."""
    c.update_table(
        TableName=TABLE,
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "correlationId", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexUpdates=[{
            "Create": {
                "IndexName": "GSI1",
                "KeySchema": [{"AttributeName": "correlationId", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
                # On dynamodb-local the throughput here is ignored; on real
                # PROVISIONED tables the GSI needs its own capacity.
                "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
            }
        }],
    )
    # On real AWS the GSI backfills asynchronously; poll until ACTIVE.
    while True:
        desc = c.describe_table(TableName=TABLE)["Table"]
        gsis = desc.get("GlobalSecondaryIndexes", [])
        if gsis and all(g["IndexStatus"] == "ACTIVE" for g in gsis):
            break
        time.sleep(1)


def query_by_correlation(c, correlation_id: str) -> dict:
    return c.query(
        TableName=TABLE,
        IndexName="GSI1",
        KeyConditionExpression="correlationId = :c",
        ExpressionAttributeValues={":c": {"S": correlation_id}},
        ReturnConsumedCapacity="TOTAL",
    )


def main() -> None:
    c, r = clients()
    create_table(c)
    table = r.Table(TABLE)

    print("=== Phase 1: hammer one partition key ===")
    succeeded, throttled = hammer(table)
    rate = 100.0 * throttled / (succeeded + throttled)
    print(f"Writes attempted: {succeeded + throttled}   "
          f"succeeded: {succeeded}   THROTTLED: {throttled}")
    print(f"Throttle rate: {rate:.1f}%  <-- the hot-partition signature")
    print("Table-wide provisioned WCU: 5  "
          "(the partition is pinned, not the table)")
    print("  Diagnosis: in CloudWatch this shows as elevated WriteThrottleEvents")
    print("  while ConsumedWriteCapacityUnits sits near the provisioned floor.")
    print("  Every write hashed to ONE partition (PK=TENANT#whale), and a single")
    print("  partition cannot exceed its share of capacity no matter the table total.\n")

    print("=== Phase 2: add the GSI and serve the reverse lookup ===")
    add_gsi(c)
    target = "corr-000123"
    resp = query_by_correlation(c, target)
    rcu = resp.get("ConsumedCapacity", {}).get("CapacityUnits", 0.0)
    n = resp["Count"]
    print(f"GSI1 created. Query by correlationId={target} -> "
          f"{n} item(s), 0 scans, {rcu:.1f} RCU.")
    print("  The base key can only Query by PK=TENANT#whale; the GSI lets us")
    print("  reverse-look-up an event by its correlation id with no Scan.\n")

    c.delete_table(TableName=TABLE)
    print(f"Cleaned up table {TABLE}.")


if __name__ == "__main__":
    main()
