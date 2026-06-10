#!/usr/bin/env python3
"""
Exercise 3 — Add write-sharding to defeat the hot partition.

Builds directly on exercise 2. Same low-capacity table, same hammer, but now
the writes are spread across N synthetic shard keys (TENANT#whale#0 ..
TENANT#whale#N-1) so they hash to N different partitions. The per-partition
ceiling is lifted by ~N×, and the throttle rate collapses.

It runs BOTH cases back to back and prints a before/after table:

  - UNSHARDED: every write -> PK=TENANT#whale            (one partition, throttles)
  - SHARDED:   every write -> PK=TENANT#whale#<0..N-1>   (N partitions, survives)

It then demonstrates the read-side cost of sharding: to read "all events for
the tenant" you must scatter-query all N shards and gather/merge the results.

Run (dynamodb-local recommended):

    docker run -d --name ddb-local -p 8000:8000 amazon/dynamodb-local
    export DDB_ENDPOINT=http://localhost:8000
    export AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local
    python exercise-03-write-sharding.py

Expected output (numbers vary; the trend is the lesson):

    === UNSHARDED (1 partition) ===
    attempted 2000  succeeded 318  throttled 1682  -> throttle rate 84.1%

    === SHARDED (10 partitions) ===
    attempted 2000  succeeded 2000  throttled 0    -> throttle rate 0.0%

    === Read-side cost of sharding ===
    Reading all events: 10 shard Queries (scatter) -> 2000 items gathered, merged.
    One unsharded Query would have been 1 call; sharding traded 1 read call
    for 10 in exchange for surviving the write load.

    Recommendation: shard the write-heavy, rarely-fully-read keys (audit logs,
    event streams). Do NOT shard keys you read in full constantly.

    Cleaned up table exercise3-sharding.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

TABLE = "exercise3-sharding"
TENANT = "whale"
WRITES = 2000
CONCURRENCY = 50
SHARD_COUNT = 10  # ceil(needed_wcu / 1000) on real AWS; here it just spreads load


def clients():
    endpoint = os.environ.get("DDB_ENDPOINT")
    cfg = Config(retries={"max_attempts": 0, "mode": "standard"})
    return (boto3.client("dynamodb", endpoint_url=endpoint, config=cfg),
            boto3.resource("dynamodb", endpoint_url=endpoint, config=cfg))


def create_table(c) -> None:
    if TABLE in c.list_tables()["TableNames"]:
        c.delete_table(TableName=TABLE)
        c.get_waiter("table_not_exists").wait(TableName=TABLE)
    c.create_table(
        TableName=TABLE,
        BillingMode="PROVISIONED",
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


def unsharded_pk() -> str:
    return f"TENANT#{TENANT}"


def sharded_pk(i: int) -> str:
    # Random/round-robin shard suffix. Spreads writes across SHARD_COUNT
    # partitions. We use i % N here for determinism in the exercise; in
    # production a random.randint(0, N-1) is the usual choice.
    return f"TENANT#{TENANT}#{i % SHARD_COUNT}"


def hammer(table, key_fn) -> tuple[int, int]:
    succeeded = throttled = 0

    def one(i: int) -> str:
        try:
            table.put_item(Item={
                "PK": key_fn(i),
                "SK": f"EVENT#{time.time_ns()}#{i}",
                "correlationId": f"corr-{i:06d}",
                "payload": "x" * 800,
            })
            return "ok"
        except ClientError as e:
            if e.response["Error"]["Code"] in (
                "ProvisionedThroughputExceededException", "ThrottlingException"):
                return "throttled"
            raise

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        for f in as_completed([pool.submit(one, i) for i in range(WRITES)]):
            if f.result() == "ok":
                succeeded += 1
            else:
                throttled += 1
    return succeeded, throttled


def report(label: str, succeeded: int, throttled: int) -> None:
    total = succeeded + throttled
    rate = 100.0 * throttled / total if total else 0.0
    print(f"=== {label} ===")
    print(f"attempted {total}  succeeded {succeeded}  throttled {throttled}  "
          f"-> throttle rate {rate:.1f}%\n")


def read_all_sharded(c) -> int:
    """Scatter-gather: query every shard, merge, sort by SK. Returns count."""
    from boto3.dynamodb.conditions import Key  # noqa: F401 (doc reference)
    items: list[dict] = []
    for s in range(SHARD_COUNT):
        resp = c.query(
            TableName=TABLE,
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": {"S": f"TENANT#{TENANT}#{s}"}},
        )
        items.extend(resp["Items"])
    items.sort(key=lambda it: it["SK"]["S"], reverse=True)
    return len(items)


def main() -> None:
    c, r = clients()

    # --- UNSHARDED ---
    create_table(c)
    table = r.Table(TABLE)
    s1, t1 = hammer(table, lambda i: unsharded_pk())
    report("UNSHARDED (1 partition)", s1, t1)

    # --- SHARDED ---
    create_table(c)  # fresh table, same tiny capacity
    table = r.Table(TABLE)
    s2, t2 = hammer(table, sharded_pk)
    report(f"SHARDED ({SHARD_COUNT} partitions)", s2, t2)

    # --- read-side cost ---
    print("=== Read-side cost of sharding ===")
    n = read_all_sharded(c)
    print(f"Reading all events: {SHARD_COUNT} shard Queries (scatter) -> "
          f"{n} items gathered, merged.")
    print("One unsharded Query would have been 1 call; sharding traded 1 read")
    print(f"call for {SHARD_COUNT} in exchange for surviving the write load.\n")

    print("Recommendation: shard the write-heavy, rarely-fully-read keys (audit")
    print("logs, event streams). Do NOT shard keys you read in full constantly —")
    print("the scatter-gather read cost would dominate.\n")

    c.delete_table(TableName=TABLE)
    print(f"Cleaned up table {TABLE}.")


if __name__ == "__main__":
    main()
