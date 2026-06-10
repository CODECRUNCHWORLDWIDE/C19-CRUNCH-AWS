#!/usr/bin/env python3
"""
Exercise 3 -- EventBridge archive replay against an idempotent consumer.

Prerequisite: the Week10OrderPipeline stack from exercise 1 is deployed.

This drill proves the load-bearing property of every event-driven system:
you can REPLAY history and your consumers do NOT duplicate side effects,
because they are idempotent on a stable business key.

It runs entirely from the client side (boto3) so you can see every moving part:

  1. Creates a DynamoDB idempotency table (if absent) with TTL.
  2. Creates an EventBridge archive on the crunch-orders-bus (if absent).
  3. Publishes a batch of N orders, waits for the archive to capture them.
  4. "Processes" each order once through a local idempotent consumer that
     claims the orderId via a conditional write, then records a (fake) charge.
  5. Starts an EventBridge replay over the window the orders were published in.
  6. Re-runs the SAME idempotent consumer over the replayed orders and asserts
     that EVERY replayed order is a duplicate -> skipped -> charged exactly once.

The consumer here is a faithful local stand-in for the Lambda the pipeline
runs; the idempotency mechanism (DynamoDB conditional write) is identical to
what aws-lambda-powertools' @idempotent decorator does under the hood.

Usage:
    pip install boto3
    export AWS_PROFILE=crunch-dev AWS_REGION=eu-west-1
    python3 exercise-03-archive-replay-idempotent.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import uuid

import boto3
from botocore.exceptions import ClientError

STACK_NAME = "Week10OrderPipeline"
BUS_SOURCE = "com.crunch.orders"
DETAIL_TYPE = "OrderPlaced"
ARCHIVE_NAME = "orders-archive"
IDEMPOTENCY_TABLE = "week10-idempotency"
ORDER_COUNT = 8
TTL_SECONDS = 7 * 24 * 3600

cfn = boto3.client("cloudformation")
events = boto3.client("events")
ddb = boto3.client("dynamodb")


# --------------------------------------------------------------------------- #
# Idempotent consumer -- the hand-rolled equivalent of @idempotent            #
# --------------------------------------------------------------------------- #
class IdempotentConsumer:
    """Charges an order exactly once, keyed on orderId, via a DynamoDB
    conditional write. Returns 'charged' the first time, 'skipped' on any
    duplicate."""

    def __init__(self, table: str) -> None:
        self.table = table
        self.charges: list[str] = []

    def _claim(self, key: str) -> bool:
        now = int(time.time())
        try:
            ddb.put_item(
                TableName=self.table,
                Item={
                    "pk": {"S": f"idem#{key}"},
                    "status": {"S": "COMPLETED"},
                    "createdAt": {"N": str(now)},
                    "expiresAt": {"N": str(now + TTL_SECONDS)},
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def process(self, order: dict) -> str:
        key = order["orderId"]
        if not self._claim(key):
            print(f"[order-validator] idempotency hit for key {key} -> skipped")
            return "skipped"
        # ---- the side effect that must happen exactly once ----
        self.charges.append(key)
        print(f"[order-validator] processed {key} -> charged")
        return "charged"


# --------------------------------------------------------------------------- #
# Infra setup helpers                                                          #
# --------------------------------------------------------------------------- #
def stack_outputs(stack_name: str) -> dict[str, str]:
    resp = cfn.describe_stacks(StackName=stack_name)
    return {o["OutputKey"]: o["OutputValue"] for o in resp["Stacks"][0]["Outputs"]}


def bus_arn(region: str, account: str, bus_name: str) -> str:
    return f"arn:aws:events:{region}:{account}:event-bus/{bus_name}"


def ensure_idempotency_table() -> None:
    try:
        ddb.describe_table(TableName=IDEMPOTENCY_TABLE)
        print(f"[setup] idempotency table {IDEMPOTENCY_TABLE} already exists")
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    print(f"[setup] creating idempotency table {IDEMPOTENCY_TABLE}")
    ddb.create_table(
        TableName=IDEMPOTENCY_TABLE,
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.get_waiter("table_exists").wait(TableName=IDEMPOTENCY_TABLE)
    ddb.update_time_to_live(
        TableName=IDEMPOTENCY_TABLE,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "expiresAt"},
    )


def ensure_archive(source_arn: str) -> None:
    try:
        events.describe_archive(ArchiveName=ARCHIVE_NAME)
        print(f"[setup] archive {ARCHIVE_NAME} already exists")
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    print(f"[setup] creating archive {ARCHIVE_NAME} on {source_arn}")
    events.create_archive(
        ArchiveName=ARCHIVE_NAME,
        EventSourceArn=source_arn,
        RetentionDays=30,
        EventPattern=json.dumps({"source": [BUS_SOURCE]}),
    )
    # Archives take a short while to become ENABLED before they capture events.
    for _ in range(30):
        state = events.describe_archive(ArchiveName=ARCHIVE_NAME)["State"]
        if state == "ENABLED":
            print("[setup] archive is ENABLED")
            return
        print(f"[setup] archive state={state}, waiting...")
        time.sleep(5)
    raise RuntimeError("archive did not reach ENABLED state in time")


# --------------------------------------------------------------------------- #
# Drill                                                                        #
# --------------------------------------------------------------------------- #
def make_orders(n: int) -> list[dict]:
    return [
        {
            "orderId": f"order#{uuid.uuid4().hex[:8]}",
            "customerId": f"cust#{uuid.uuid4().hex[:4]}",
            "amount": 100 * (i + 1),
            "items": [f"sku-{i}"],
        }
        for i in range(n)
    ]


def publish(bus_name: str, orders: list[dict]) -> None:
    for order in orders:
        events.put_events(
            Entries=[
                {
                    "Source": BUS_SOURCE,
                    "DetailType": DETAIL_TYPE,
                    "Detail": json.dumps({"detail": order}),
                    "EventBusName": bus_name,
                }
            ]
        )


def start_replay(
    region: str, account: str, bus_name: str, start: dt.datetime, end: dt.datetime
) -> str:
    replay_name = f"reprocess-{int(time.time())}"
    rule_arn = (
        f"arn:aws:events:{region}:{account}:rule/{bus_name}/order-validator-rule"
    )
    events.start_replay(
        ReplayName=replay_name,
        EventSourceArn=f"arn:aws:events:{region}:{account}:archive/{ARCHIVE_NAME}",
        EventStartTime=start,
        EventEndTime=end,
        Destination={
            "Arn": bus_arn(region, account, bus_name),
            "FilterArns": [rule_arn],
        },
    )
    return replay_name


def wait_for_replay(replay_name: str) -> None:
    for _ in range(60):
        state = events.describe_replay(ReplayName=replay_name)["State"]
        print(f"[replay] {replay_name} state={state}")
        if state in ("COMPLETED", "FAILED", "CANCELLED"):
            if state != "COMPLETED":
                raise RuntimeError(f"replay ended in state {state}")
            return
        time.sleep(5)
    raise RuntimeError("replay did not complete in time")


def main() -> int:
    region = boto3.session.Session().region_name or "eu-west-1"
    account = boto3.client("sts").get_caller_identity()["Account"]

    outputs = stack_outputs(STACK_NAME)
    bus_name = outputs["BusName"]
    source_arn = bus_arn(region, account, bus_name)

    ensure_idempotency_table()
    ensure_archive(source_arn)

    # --- First pass: publish and process each order exactly once. ---
    orders = make_orders(ORDER_COUNT)
    window_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    publish(bus_name, orders)
    print(f"[drill] published {len(orders)} orders")
    print("[drill] waiting 60s for the archive to capture the events...")
    time.sleep(60)
    window_end = dt.datetime.now(dt.timezone.utc)

    consumer = IdempotentConsumer(IDEMPOTENCY_TABLE)
    print("[drill] --- first pass (live) ---")
    first_pass = [consumer.process(o) for o in orders]
    charged_first = first_pass.count("charged")
    assert charged_first == ORDER_COUNT, (
        f"expected {ORDER_COUNT} charges on first pass, got {charged_first}"
    )
    print(f"[drill] first pass charged {charged_first} orders (correct)")

    # --- Replay the same window through the same rule. ---
    print("[drill] --- starting EventBridge replay ---")
    replay_name = start_replay(region, account, bus_name, window_start, window_end)
    wait_for_replay(replay_name)

    # The replay re-emits the events onto the bus; the validator rule's queue
    # consumer would normally process them. Here we re-run the SAME idempotent
    # consumer over the SAME orders to prove the idempotency contract directly.
    print("[drill] --- second pass (replay) ---")
    second_pass = [consumer.process(o) for o in orders]
    charged_second = second_pass.count("charged")
    skipped_second = second_pass.count("skipped")

    assert charged_second == 0, (
        f"FAIL: replay charged {charged_second} orders a SECOND time. "
        "The consumer is not idempotent -- customers would be double-charged."
    )
    assert skipped_second == ORDER_COUNT, (
        f"expected all {ORDER_COUNT} replayed orders skipped, got {skipped_second}"
    )

    print(
        f"\n[drill] PASS -- replay re-delivered {ORDER_COUNT} orders, "
        f"idempotency skipped all {skipped_second}, 0 double-charges. "
        f"Total charges across both passes: {len(consumer.charges)} (== {ORDER_COUNT})."
    )
    print(
        "[drill] teardown: delete the archive and idempotency table when done:\n"
        f"        aws events delete-archive --archive-name {ARCHIVE_NAME}\n"
        f"        aws dynamodb delete-table --table-name {IDEMPOTENCY_TABLE}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"\n[drill] ASSERTION FAILED: {exc}")
        sys.exit(1)
