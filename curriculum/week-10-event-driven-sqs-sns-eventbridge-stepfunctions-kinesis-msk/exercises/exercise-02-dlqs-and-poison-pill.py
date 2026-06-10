#!/usr/bin/env python3
"""
Exercise 2 -- DLQs everywhere + the poison-pill drill.

Prerequisite: the Week10OrderPipeline stack from exercise 1 is deployed.

What this drill does, end to end:
  1. Reads the deployed stack's resource names from CloudFormation outputs.
  2. Sends a batch of GOOD orders through the pipeline (via EventBridge PutEvents).
  3. Sends ONE poison-pill order -- an OrderPlaced event with no customerId --
     which the order-validator Lambda throws on, every single time.
  4. Polls the order-validator-dlq and asserts the poison pill landed there,
     with its full payload intact, after exceeding maxReceiveCount=3.
  5. Asserts the GOOD orders did NOT land in the DLQ -- i.e. one bad message
     did not poison the good ones.

The point: prove the failure boundary works BEFORE a real poison pill shows up
at 3 a.m. Run it, watch the bad message die quietly in the right place.

Usage:
    pip install boto3
    export AWS_PROFILE=crunch-dev AWS_REGION=eu-west-1
    python3 exercise-02-dlqs-and-poison-pill.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid

import boto3

STACK_NAME = "Week10OrderPipeline"
BUS_SOURCE = "com.crunch.orders"
DETAIL_TYPE = "OrderPlaced"
GOOD_ORDER_COUNT = 5
# maxReceiveCount=3 + visibility timeout 30s means the pill needs ~90s of
# retries before SQS redrives it. We poll generously.
DLQ_POLL_ATTEMPTS = 30
DLQ_POLL_INTERVAL_SECONDS = 10

cfn = boto3.client("cloudformation")
events = boto3.client("events")
sqs = boto3.client("sqs")


def stack_outputs(stack_name: str) -> dict[str, str]:
    """Return {OutputKey: OutputValue} for a deployed stack."""
    resp = cfn.describe_stacks(StackName=stack_name)
    outputs = resp["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def put_order(bus_name: str, detail: dict) -> None:
    """Publish one OrderPlaced event to the custom bus."""
    events.put_events(
        Entries=[
            {
                "Source": BUS_SOURCE,
                "DetailType": DETAIL_TYPE,
                "Detail": json.dumps({"detail": detail}),
                "EventBusName": bus_name,
            }
        ]
    )


def make_good_order() -> dict:
    return {
        "orderId": f"order#{uuid.uuid4().hex[:8]}",
        "customerId": f"cust#{uuid.uuid4().hex[:4]}",
        "amount": 1299,
        "items": ["sku-1"],
    }


def make_poison_order() -> dict:
    """A poison pill: valid envelope, but NO customerId -> validator throws
    ValidationError every time it sees it."""
    return {
        "orderId": "order#POISON",
        # customerId deliberately omitted
        "amount": 1299,
        "items": ["sku-bad"],
    }


def drain_dlq(dlq_url: str, want_order_id: str) -> dict | None:
    """Long-poll the DLQ looking for the poison pill by its orderId.
    Returns the parsed detail of the matching message, or None if not found
    within the polling budget."""
    print(f"[drill] polling {dlq_url} for {want_order_id} ...")
    for attempt in range(1, DLQ_POLL_ATTEMPTS + 1):
        resp = sqs.receive_message(
            QueueUrl=dlq_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=DLQ_POLL_INTERVAL_SECONDS,  # long polling
            VisibilityTimeout=5,
        )
        for msg in resp.get("Messages", []):
            body = json.loads(msg["Body"])
            detail = body.get("detail", {})
            if detail.get("orderId") == want_order_id:
                print(
                    f"[drill] FOUND poison pill in DLQ on poll attempt "
                    f"{attempt}: {want_order_id}"
                )
                return detail
            # Not ours -- leave it (don't delete) for inspection.
        print(f"[drill] poll attempt {attempt}/{DLQ_POLL_ATTEMPTS}: not yet in DLQ")
    return None


def assert_good_orders_absent(dlq_url: str, good_ids: set[str]) -> None:
    """Confirm none of the good orders leaked into the DLQ."""
    resp = sqs.receive_message(
        QueueUrl=dlq_url, MaxNumberOfMessages=10, WaitTimeSeconds=2
    )
    leaked = []
    for msg in resp.get("Messages", []):
        detail = json.loads(msg["Body"]).get("detail", {})
        if detail.get("orderId") in good_ids:
            leaked.append(detail["orderId"])
    if leaked:
        raise AssertionError(
            f"FAIL: good orders leaked into the DLQ: {leaked}. "
            "A poison pill should not poison good messages."
        )
    print("[drill] confirmed: no good orders in the DLQ -- poison pill was isolated")


def main() -> int:
    print(f"[drill] reading outputs from stack {STACK_NAME}")
    outputs = stack_outputs(STACK_NAME)
    bus_name = outputs["BusName"]
    dlq_url = outputs["ValidatorDlqUrl"]

    # 1. Send the good orders.
    good = [make_good_order() for _ in range(GOOD_ORDER_COUNT)]
    good_ids = {o["orderId"] for o in good}
    for order in good:
        put_order(bus_name, order)
    print(f"[drill] published {len(good)} good orders: {sorted(good_ids)}")

    # 2. Send the poison pill.
    poison = make_poison_order()
    put_order(bus_name, poison)
    print(f"[drill] published 1 POISON order: {poison['orderId']} (no customerId)")
    print(
        "[drill] the validator will throw ValidationError 3x, then SQS will "
        "redrive it to order-validator-dlq. Watch the Lambda logs:\n"
        "        aws logs tail /aws/lambda/order-validator --follow"
    )

    # 3. Wait for the poison pill to land in the DLQ.
    found = drain_dlq(dlq_url, poison["orderId"])
    if found is None:
        print(
            "[drill] FAIL: poison pill never reached the DLQ within the polling "
            "budget. Check maxReceiveCount on order-validator-queue and the "
            "validator's reportBatchItemFailures setting."
        )
        return 1

    # 4. Assert the payload is intact.
    assert found["orderId"] == "order#POISON", "DLQ message lost its orderId"
    assert "customerId" not in found, "poison pill payload was mutated"
    assert found["items"] == ["sku-bad"], "DLQ message lost its payload"
    print("[drill] confirmed: poison pill payload is intact in the DLQ")

    # 5. Assert the good orders did not leak into the DLQ.
    assert_good_orders_absent(dlq_url, good_ids)

    print(
        "\n[drill] PASS -- the poison pill died quietly in order-validator-dlq, "
        "payload intact, while good orders flowed through untouched."
    )
    print(
        "[drill] to redrive after a fix:\n"
        f"        aws sqs start-message-move-task --source-arn "
        f"<dlq-arn> --destination-arn <source-queue-arn>"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"\n[drill] ASSERTION FAILED: {exc}")
        sys.exit(1)
