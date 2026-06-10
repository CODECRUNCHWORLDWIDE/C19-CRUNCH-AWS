#!/usr/bin/env python3
"""
Exercise 3 — DynamoDB Global Tables and Aurora Global Database: stand them up
across two Regions and MEASURE the cross-Region replication lag (your RPO floor).

Estimated time: ~90 minutes.
Cost: a DynamoDB Global Table (replicated write units) + an Aurora Global
      Database that runs a SECOND-REGION INSTANCE 24/7 while it exists -- the
      warm-standby cost, DOLLARS not cents. DELETE THE AURORA GLOBAL CLUSTER AND
      THE DYNAMODB REPLICA WHEN YOU FINISH MEASURING -- the script's last steps
      print the teardown; do not skip them.

WHAT THIS DOES
--------------
The headline outcome is two measured RPO numbers -- one for DynamoDB, one for
Aurora -- because RPO is a number, not an adjective (Lecture 2). This script:

  1. Creates a DynamoDB table in the primary Region and adds a REPLICA in the DR
     Region (making it a v2 Global Table). It writes an item in the primary and
     polls the replica until the item appears, timing the lag = your DynamoDB RPO.
  2. Prints the AWS CLI commands to join an existing Aurora cluster into a Global
     Database with a secondary Region, and a boto3 probe that measures
     AuroraGlobalDBReplicationLag from CloudWatch = your Aurora RPO.
  3. Tears the DynamoDB replica down (and tells you how to delete the Aurora
     global cluster, which you MUST do to stop the warm-standby bill).

We drive DynamoDB fully in code (cheap, fast). Aurora Global is expensive and
slow to create, so we drive it via documented CLI + a CloudWatch lag probe
rather than spinning a fresh cluster inside the script -- you attach it to the
Week-8 cluster you already have.

HOW TO RUN
----------
    python -m venv .venv && source .venv/bin/activate
    pip install boto3
    export PRIMARY_REGION=us-east-1
    export REPLICA_REGION=us-west-2
    # For the Aurora half, point at your Week-8 cluster (optional; DynamoDB half
    # runs without it):
    export AURORA_CLUSTER_ID=capstone-aurora     # your existing primary cluster
    python exercise-03-global-tables-aurora-global.py

ACCEPTANCE CRITERIA
-------------------
  [ ] A DynamoDB table exists in PRIMARY_REGION with a replica in REPLICA_REGION
      (a v2 Global Table).
  [ ] An item written in the primary appears in the replica; the script prints
      the measured replication lag (your DynamoDB RPO floor).
  [ ] You ran (or can explain) the Aurora Global Database join and read the
      AuroraGlobalDBReplicationLag metric (your Aurora RPO floor).
  [ ] You can state both RPO numbers and explain why DynamoDB's is typically
      sub-second and Aurora's is typically ~1s (storage-level redo shipping).
  [ ] You deleted the replica/global cluster so nothing is left billing.

SMOKE OUTPUT (your numbers will differ)
---------------------------------------
    Global Table c19-wk13-app ready in us-east-1 + us-west-2.
    Wrote pk=order#42 in us-east-1; appeared in us-west-2 after 0.83s.
      ^ DynamoDB RPO floor for this write: ~0.83s (multi-active, last-writer-wins).
    Aurora AuroraGlobalDBReplicationLag (last 5 min avg): 1.10 s
      ^ Aurora RPO floor: ~1.1s (storage-level redo shipping, us-east-1 -> us-west-2).
"""

from __future__ import annotations

import os
import time

import boto3
from botocore.exceptions import ClientError

PRIMARY_REGION = os.environ.get("PRIMARY_REGION", "us-east-1")
REPLICA_REGION = os.environ.get("REPLICA_REGION", "us-west-2")
AURORA_CLUSTER_ID = os.environ.get("AURORA_CLUSTER_ID", "")
TABLE = "c19-wk13-app"

ddb_primary = boto3.client("dynamodb", region_name=PRIMARY_REGION)
ddb_replica = boto3.client("dynamodb", region_name=REPLICA_REGION)


def step_1_create_global_table() -> None:
    """Create the table in the primary Region, then add a DR-Region replica."""
    print("Step 1: create the table and add a DR-Region replica ...")
    try:
        ddb_primary.create_table(
            TableName=TABLE,
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
            # Streams MUST be NEW_AND_OLD_IMAGES for Global Tables replication.
            StreamSpecification={"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
            Tags=[
                {"Key": "service", "Value": "capstone"},
                {"Key": "environment", "Value": "lab"},
            ],
        )
        print(f"  Creating table {TABLE} in {PRIMARY_REGION} ...")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceInUseException":
            raise
        print(f"  Table {TABLE} already exists in {PRIMARY_REGION}.")

    ddb_primary.get_waiter("table_exists").wait(TableName=TABLE)

    # Add the replica -> this makes it a v2 Global Table.
    desc = ddb_primary.describe_table(TableName=TABLE)["Table"]
    existing = {r["RegionName"] for r in desc.get("Replicas", [])}
    if REPLICA_REGION not in existing:
        try:
            ddb_primary.update_table(
                TableName=TABLE,
                ReplicaUpdates=[{"Create": {"RegionName": REPLICA_REGION}}],
            )
            print(f"  Adding replica in {REPLICA_REGION} (this takes a few minutes) ...")
        except ClientError as e:
            if e.response["Error"]["Code"] != "ValidationException":
                raise

    # Wait for the replica to become ACTIVE in the DR Region.
    for _ in range(60):
        try:
            d = ddb_replica.describe_table(TableName=TABLE)["Table"]
            if d["TableStatus"] == "ACTIVE":
                break
        except ClientError:
            pass
        time.sleep(10)
    print(f"  Global Table {TABLE} ready in {PRIMARY_REGION} + {REPLICA_REGION}.")


def step_2_measure_dynamodb_rpo() -> float:
    """Write in the primary; poll the replica until it appears; time the lag."""
    print("Step 2: measure DynamoDB cross-Region replication lag (RPO floor) ...")
    pk = "order#42"
    sk = f"v#{int(time.time())}"
    payload = {"pk": {"S": pk}, "sk": {"S": sk}, "status": {"S": "created"}}

    t0 = time.perf_counter()
    ddb_primary.put_item(TableName=TABLE, Item=payload)

    lag = None
    for _ in range(200):  # up to ~20s of polling at 0.1s
        resp = ddb_replica.get_item(
            TableName=TABLE,
            Key={"pk": {"S": pk}, "sk": {"S": sk}},
            ConsistentRead=False,  # cross-Region reads are eventually consistent
        )
        if "Item" in resp:
            lag = time.perf_counter() - t0
            break
        time.sleep(0.1)

    if lag is None:
        print("  Item did not appear in the replica within 20s -- check replica status.")
        return float("inf")
    print(f"  Wrote pk={pk} in {PRIMARY_REGION}; appeared in {REPLICA_REGION} after {lag:.2f}s.")
    print(f"    ^ DynamoDB RPO floor for this write: ~{lag:.2f}s "
          "(multi-active, last-writer-wins).")
    return lag


def step_3_aurora_global_instructions() -> None:
    """Aurora Global Database join (CLI) + CloudWatch lag probe (boto3)."""
    print("\nStep 3: Aurora Global Database (the relational RPO floor) ...")
    print("  Aurora Global is expensive and slow to create, so attach your Week-8")
    print("  cluster rather than spinning a new one. The CLI join is:\n")
    print("    # 1) create a global cluster from your existing primary:")
    print(f"    aws rds create-global-cluster --region {PRIMARY_REGION} \\")
    print("      --global-cluster-identifier capstone-global \\")
    print(f"      --source-db-cluster-identifier {AURORA_CLUSTER_ID or '<your-cluster>'}\n")
    print("    # 2) add a read-only SECONDARY cluster in the DR Region:")
    print(f"    aws rds create-db-cluster --region {REPLICA_REGION} \\")
    print("      --db-cluster-identifier capstone-aurora-dr \\")
    print("      --global-cluster-identifier capstone-global \\")
    print("      --engine aurora-postgresql\n")
    print("    # 3) add one instance to the DR cluster (this is the warm-standby cost):")
    print(f"    aws rds create-db-instance --region {REPLICA_REGION} \\")
    print("      --db-instance-identifier capstone-aurora-dr-1 \\")
    print("      --db-cluster-identifier capstone-aurora-dr \\")
    print("      --db-instance-class db.r6g.large --engine aurora-postgresql\n")

    if not AURORA_CLUSTER_ID:
        print("  (AURORA_CLUSTER_ID not set -- skipping the live lag probe. Set it to")
        print("   your Week-8 cluster to measure AuroraGlobalDBReplicationLag.)")
        return

    print("  Probing AuroraGlobalDBReplicationLag from CloudWatch (DR Region) ...")
    cw = boto3.client("cloudwatch", region_name=REPLICA_REGION)
    import datetime as dt

    end = dt.datetime.utcnow()
    start = end - dt.timedelta(minutes=5)
    resp = cw.get_metric_statistics(
        Namespace="AWS/RDS",
        MetricName="AuroraGlobalDBReplicationLag",
        Dimensions=[{"Name": "DBClusterIdentifier", "Value": "capstone-aurora-dr"}],
        StartTime=start,
        EndTime=end,
        Period=60,
        Statistics=["Average"],
        Unit="Milliseconds",
    )
    points = sorted(resp.get("Datapoints", []), key=lambda p: p["Timestamp"])
    if points:
        avg_ms = sum(p["Average"] for p in points) / len(points)
        print(f"  Aurora AuroraGlobalDBReplicationLag (last 5 min avg): {avg_ms/1000:.2f} s")
        print(f"    ^ Aurora RPO floor: ~{avg_ms/1000:.2f}s (storage-level redo shipping, "
              f"{PRIMARY_REGION} -> {REPLICA_REGION}).")
    else:
        print("  No datapoints yet -- the secondary may still be bootstrapping. Re-run in a few minutes.")


def step_4_cleanup_hints(dynamo_lag: float) -> None:
    print("\nStep 4: TEAR DOWN so nothing is left billing ...")
    print("  Remove the DynamoDB replica (stops replicated write charges):")
    print(f"    aws dynamodb update-table --region {PRIMARY_REGION} --table-name {TABLE} \\")
    print(f"      --replica-updates '[{{\"Delete\":{{\"RegionName\":\"{REPLICA_REGION}\"}}}}]'")
    print("  Then delete the table itself when done with the week:")
    print(f"    aws dynamodb delete-table --region {PRIMARY_REGION} --table-name {TABLE}")
    print("\n  CRITICAL -- the Aurora Global secondary runs an instance 24/7. Delete it:")
    print(f"    aws rds delete-db-instance --region {REPLICA_REGION} "
          "--db-instance-identifier capstone-aurora-dr-1 --skip-final-snapshot")
    print(f"    aws rds delete-db-cluster --region {REPLICA_REGION} "
          "--db-cluster-identifier capstone-aurora-dr --skip-final-snapshot")
    print(f"    aws rds remove-from-global-cluster --region {PRIMARY_REGION} "
          "--global-cluster-identifier capstone-global "
          f"--db-cluster-identifier capstone-aurora-dr")
    print(f"    aws rds delete-global-cluster --region {PRIMARY_REGION} "
          "--global-cluster-identifier capstone-global")
    print(f"\n  Record in your cost report: DynamoDB RPO ~{dynamo_lag:.2f}s, "
          "Aurora RPO from the probe above. These are the numbers the Friday drill targets.")


def main() -> None:
    print(f"Primary={PRIMARY_REGION}  Replica={REPLICA_REGION}  Table={TABLE}\n")
    step_1_create_global_table()
    dynamo_lag = step_2_measure_dynamodb_rpo()
    step_3_aurora_global_instructions()
    step_4_cleanup_hints(dynamo_lag)


if __name__ == "__main__":
    main()
