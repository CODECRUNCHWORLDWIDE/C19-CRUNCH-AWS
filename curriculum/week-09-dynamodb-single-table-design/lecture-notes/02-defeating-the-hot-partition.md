# Lecture 2 — Defeating the Hot Partition: Write-Sharding, Sparse Indexes, and Capacity-Unit Math

> **Reading time:** ~80 minutes. **Hands-on time:** ~90 minutes (you build a GSI, a sparse index, a write-sharded partition, and do the RCU/WCU math by hand).

Lecture 1 gave you a table that serves eight access patterns with single operations. This lecture covers everything that makes that table survive contact with production: the secondary indexes that serve the remaining patterns, the sparse-index trick that serves status filters for almost free, the write-sharding that keeps a popular partition from throttling, and the capacity math that lets you choose on-demand or provisioned with a dollar figure instead of a guess. The throughline is a single physical fact you must hold onto the entire week: **DynamoDB throttles per partition, not per table.** Almost every "DynamoDB is slow / DynamoDB is throttling" story is a hot-partition story, and almost every fix is one of the three in this lecture.

## 2.1 — The partition is the unit of throughput

DynamoDB stores your table on physical partitions — internal storage nodes you never see. The partition key is hashed; the hash decides which partition an item lands on. Each physical partition has a hard ceiling: it can serve up to **3,000 read capacity units (RCU)** and **1,000 write capacity units (WCU)** per second, and it can hold up to **10 GB** of data. When a partition fills past 10 GB or gets hotter than its throughput ceiling, DynamoDB splits it. But the split takes time, and it splits by *key range*, which does you no good if all your traffic targets a single key value — there is no range to split a single key across.

That is the hot partition. You can have a table provisioned for 40,000 WCU, sitting at 5% utilization table-wide, and still get `ProvisionedThroughputExceededException` (provisioned mode) or throttled requests with elevated `ThrottledRequests` (on-demand mode) — because all your writes are hammering one partition key and that one partition is pinned at its 1,000 WCU ceiling. The table is cold; one partition is on fire. CloudWatch tells the story: table-level `ConsumedWriteCapacityUnits` is low, but `ThrottledRequests` is climbing and a `WriteThrottleEvents` metric is non-zero. You diagnose a hot partition by the *gap* between table-level consumption and throttling.

DynamoDB does fight back on your behalf. **Adaptive capacity** lets a hot partition borrow unused capacity from sibling partitions, and **burst capacity** banks up to 300 seconds of unused throughput for short spikes. Adaptive capacity also performs *automatic key-range splitting* for a key range that stays hot. These features absorb moderate skew transparently — which is exactly why a hot partition often does not show up until you are at real volume. But adaptive capacity cannot split a *single* key value across partitions; if one partition key gets 2,000 writes/second, no amount of adaptiveness helps, because every one of those writes hashes to the same partition. For that you need write-sharding (2.5). Know the order: design good keys first, lean on adaptive capacity for moderate skew, shard only when a single key is genuinely the bottleneck.

## 2.2 — RCU and WCU, defined and computed

You cannot reason about throttling or cost without the capacity-unit definitions. Memorize these; they are quiz material and they are the entire challenge.

**Write capacity unit (WCU).** One WCU = one write of an item up to **1 KB**, per second. An item of 1.5 KB costs 2 WCU (round *up* to the next KB). A 4.2 KB item costs 5 WCU. Transactional writes cost **2× WCU** (a 1 KB transactional write is 2 WCU). Item size for WCU is the *total* size of all attribute names and values.

**Read capacity unit (RCU).** One RCU = one **strongly consistent** read of an item up to **4 KB**, per second. An **eventually consistent** read costs **half** an RCU per 4 KB — so an eventually consistent read of a 4 KB item is 0.5 RCU. A strongly consistent read of a 6 KB item is 2 RCU (round up to 8 KB = 2 × 4 KB). A transactional read costs **2× RCU**. Rounding for RCU is always up to the next 4 KB.

Worked examples — do these by hand until they are reflexive:

- Write a 3 KB item: `ceil(3/1) = 3 WCU`.
- Write a 3 KB item in a transaction: `3 × 2 = 6 WCU`.
- Eventually consistent read of a 10 KB item: `ceil(10/4) = 3` blocks × 0.5 = `1.5 RCU`.
- Strongly consistent read of a 10 KB item: `ceil(10/4) = 3 RCU`.
- A `Query` returning 20 items of 2 KB each, eventually consistent: total bytes = 40 KB; `ceil(40/4) = 10` blocks × 0.5 = `5 RCU`. **The Query is billed on total bytes read, not per item** — this is why a `Query` of a tight partition is cheap and a `Scan` of a big table is ruinous.

The per-partition ceiling restated in these units: 1,000 WCU/s and 3,000 RCU/s per partition. If a single partition key needs to sustain 1,500 writes/second of 1 KB items, that is 1,500 WCU against a 1,000 WCU ceiling — it *will* throttle, in any billing mode, until you shard it.

## 2.3 — Global Secondary Indexes (GSIs)

A GSI is a *separate*, *automatically maintained* copy of your table with a *different* partition and sort key. It serves access patterns the base table's key cannot. From Lecture 1 we owe three patterns to a GSI: user-by-email (3), comment-by-id (8), orgs-a-user-belongs-to (11). We serve all three from one **overloaded** GSI called `GSI1`, with generic key attributes `GSI1PK` / `GSI1SK` — the same overloading trick as the base table.

You populate the GSI by writing the `GSI1PK`/`GSI1SK` attributes onto the relevant items:

- A **user** item carries `GSI1PK = EMAIL#<email>` so user-by-email is `Query(GSI1, GSI1PK=EMAIL#alice@acme.com)`.
- A **comment** item carries `GSI1PK = COMMENT#<id>` so comment-by-id is `Query(GSI1, GSI1PK=COMMENT#c_abc)`.
- A **membership** item carries `GSI1PK = USER#<id>`, `GSI1SK = ORG#<org>` so "orgs a user belongs to" is `Query(GSI1, GSI1PK=USER#u_001, GSI1SK begins_with ORG#)`.

Four facts about GSIs you must know:

1. **Eventual consistency only.** A GSI is updated asynchronously after the base item is written. There is a propagation lag (usually milliseconds, occasionally longer under load). You cannot do a strongly consistent read from a GSI. Never read-after-write from a GSI and expect to see your own write immediately.
2. **Separate capacity.** A GSI has its own RCU/WCU (or its own share of on-demand). If the GSI's partition key is hotter than the base table's, the *GSI* can throttle and — critically — a throttled GSI *back-pressures writes to the base table*. A hot GSI is a real outage source.
3. **Projection controls cost.** `KEYS_ONLY` projects only the keys (cheapest, but you must fetch the full item from the base table after). `INCLUDE` projects the keys plus a named list of attributes. `ALL` projects everything (most storage, most write cost, but the GSI query is self-sufficient). Choose `ALL` only when the query needs the whole item; choose `INCLUDE` when it needs a few attributes; choose `KEYS_ONLY` when you only need the keys to then `BatchGetItem` the base.
4. **Up to 20 GSIs per table.** You rarely need more than two or three for one service if you overload them.

## 2.4 — Local Secondary Indexes (LSIs), and why you almost never want one

An LSI shares the base table's *partition* key but uses a *different sort* key. It can be read strongly consistently, which is its one genuine advantage. It also has three disqualifying constraints that make it almost always the wrong choice in 2026:

1. **It must be created at table-creation time and can never be added or removed.** A GSI you add or drop with an `UpdateTable` call any time. An LSI is forever. This alone is a near-disqualifier — your access patterns will change, and a key design you cannot evolve is a liability.
2. **It binds you to a 10 GB item-collection limit.** All items sharing a partition key — across the base table *and* all its LSIs — must fit in 10 GB total. With a GSI there is no such ceiling. A partition that grows past 10 GB and has an LSI starts throwing `ItemCollectionSizeLimitExceeded` and you cannot fix it without rebuilding the table.
3. **It shares the base table's throughput** rather than having its own, which couples failure domains.

The strong-consistency advantage is real but narrow. In practice the answer is: **use a GSI.** Reach for an LSI only when you have a hard requirement for strongly-consistent reads on an alternate sort key *and* you are certain the item collection stays under 10 GB *and* you can commit to the index at creation time. That conjunction is rare. We use zero LSIs this week, deliberately.

## 2.5 — Sparse indexes: the cheapest filter in DynamoDB

Here is the trick that feels like cheating the first time you see it. **A GSI only contains items that carry the GSI's key attributes.** If you write the `GSI1PK` attribute onto only *some* of your items, the GSI is *sparse* — it indexes only those items. A `Query` or `Scan` against a sparse GSI touches only the items that matter, not the whole table.

The canonical use: model a "needs attention" worklist. Say comments can be flagged for moderation. Add a *second* GSI, `GSI2`, whose key is set **only on flagged comments**:

```python
def flag_comment_for_review(project_id: str, sk: str) -> None:
    # Setting GSI2PK adds this item to the sparse review index. Unflagged
    # comments never carry GSI2PK and therefore never appear in GSI2.
    table.update_item(
        Key={"PK": keys.project_pk(project_id), "SK": sk},
        UpdateExpression="SET GSI2PK = :g, GSI2SK = :s, reviewStatus = :r",
        ExpressionAttributeValues={
            ":g": "REVIEW#pending",
            ":s": keys.now_iso(),
            ":r": "pending",
        },
    )

def clear_review(project_id: str, sk: str) -> None:
    # REMOVE-ing GSI2PK drops the item out of the sparse index entirely.
    table.update_item(
        Key={"PK": keys.project_pk(project_id), "SK": sk},
        UpdateExpression="REMOVE GSI2PK, GSI2SK SET reviewStatus = :r",
        ExpressionAttributeValues={":r": "cleared"},
    )
```

Now "list all comments pending review, oldest first, across the whole table" is one `Query(GSI2, GSI2PK=REVIEW#pending, ScanIndexForward=True)` that reads *only* the flagged items. You have built a moderation queue with no extra table, no scan, and no cost for the millions of comments that are not flagged — because they are not in the index at all. Sparse indexes are how you model queues, status filters, "incomplete" lists, and any "find the few items in state X" pattern. When `REMOVE` drops the key attribute, the item leaves the index; you self-clean the queue by clearing the flag.

## 2.6 — Write-sharding: spreading a hot partition

When a single partition key is genuinely the bottleneck — adaptive capacity has done all it can and one key still needs more than 1,000 WCU — you shard it. Write-sharding spreads what *was* one partition key across N synthetic keys by appending a shard suffix, so the writes hash to N different physical partitions.

There are two flavors:

**Random sharding.** Append a random suffix `0..N-1` at write time. Writes spread evenly across N partitions, lifting the ceiling to `N × 1,000` WCU. The cost is on the read side: to read "all of it" you must `Query` all N shards (a scatter) and merge the results (a gather). Use random sharding when you write far more than you read, or when you never need to read a single logical partition in full.

```python
import random
SHARD_COUNT = 10

def audit_pk_sharded(org_id: str) -> str:
    shard = random.randint(0, SHARD_COUNT - 1)
    return f"ORG#{org_id}#AUDIT#{shard}"

def write_audit(org_id: str, event: dict) -> None:
    # Spread audit writes across 10 partitions -> 10x the write ceiling.
    table.put_item(Item={
        "PK": audit_pk_sharded(org_id),
        "SK": keys.audit_sk(keys.now_iso()),
        "entityType": "AuditEntry",
        **event,
    })

def read_all_audit(org_id: str, limit_per_shard: int = 100) -> list[dict]:
    # Scatter: query every shard. Gather: merge and sort by timestamp.
    items: list[dict] = []
    for shard in range(SHARD_COUNT):
        resp = table.query(
            KeyConditionExpression=Key("PK").eq(f"ORG#{org_id}#AUDIT#{shard}"),
            ScanIndexForward=False,
            Limit=limit_per_shard,
        )
        items.extend(resp["Items"])
    items.sort(key=lambda it: it["SK"], reverse=True)
    return items
```

**Calculated sharding.** Derive the shard from an attribute you already have, so you can target the right shard on read without scattering. If you shard by `hash(comment_id) % N`, then a read that knows the `comment_id` can compute its shard and `Query` exactly one partition — no scatter. Calculated sharding trades the read-side scatter for a constraint: you can only do targeted reads when you know the sharding attribute.

The decision: **shard only when a single key is the proven bottleneck.** Sharding is not free — it complicates every read of that key and multiplies your `Query` calls. The audit log is a good sharding candidate (write-heavy, rarely read in full, and when it is read you can tolerate the scatter). A project's comments are usually *not* a sharding candidate — you read them constantly and the scatter cost would dominate. Choose N from the math: if a key needs 4,500 WCU, you need `ceil(4500/1000) = 5` shards minimum; round up to 10 for headroom. Picking N too high wastes read calls; too low leaves you throttling. The exercises walk you through proving the throttle disappears.

## 2.7 — TTL: the free garbage collector

Time-to-live deletes items automatically. You designate one **Number** attribute holding a Unix epoch timestamp in *seconds* (not milliseconds — a classic bug). When that time passes, DynamoDB deletes the item, usually within 48 hours of expiry (it is best-effort background work, not a precise timer). TTL deletes are free — no WCU charged. They flow through Streams as `REMOVE` records with a `userIdentity` of `dynamodb.amazonaws.com`, so your Stream consumer can distinguish a TTL expiry from an application delete.

```python
import time
def write_ephemeral_session(user_id: str, ttl_hours: int = 24) -> None:
    table.put_item(Item={
        "PK": f"SESSION#{user_id}",
        "SK": f"SESSION#{int(time.time())}",
        # expiresAt is epoch SECONDS. DynamoDB deletes after this passes.
        "expiresAt": int(time.time()) + ttl_hours * 3600,
        "entityType": "Session",
    })
```

Two cautions: a TTL-expired item may still appear in reads for up to 48 hours after expiry (filter on `expiresAt > now` in your `FilterExpression` if you cannot tolerate that), and TTL is best-effort — never use it where exact-time deletion is a correctness requirement.

## 2.8 — Conditional writes, optimistic concurrency, transactions

These are the consistency primitives. They are how you keep the *duplicated* project row (Lecture 1) consistent and how you avoid lost updates.

**Conditional writes** attach a `ConditionExpression` to a write; the write only happens if the condition is true, atomically. `attribute_not_exists(PK)` makes a `PutItem` an insert-only "create" that fails if the key already exists. `attribute_exists(PK)` makes an update fail if the item was deleted.

**Optimistic concurrency** uses a `version` attribute. Read the item, get its `version`, write back with `ConditionExpression="version = :expected"` and `SET version = version + 1`. If someone else wrote in between, your condition fails with `ConditionalCheckFailedException`, you re-read and retry. No locks, no blocking — you detect the conflict at commit time.

```python
from botocore.exceptions import ClientError

def update_project_name(project_id: str, new_name: str, expected_version: int) -> bool:
    try:
        table.update_item(
            Key={"PK": keys.project_pk(project_id), "SK": keys.project_pk(project_id)},
            UpdateExpression="SET #n = :name, version = version + :one",
            ConditionExpression="version = :expected",
            ExpressionAttributeNames={"#n": "name"},
            ExpressionAttributeValues={
                ":name": new_name, ":one": 1, ":expected": expected_version,
            },
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False  # lost the race; caller re-reads and retries
        raise
```

**Transactions** (`TransactWriteItems`) give you all-or-nothing across up to 100 items in one or more tables. Either every write commits or none do. Each transactional write costs 2× WCU. Use it for the duplicated project row: write the row into the org partition *and* the project partition in one transaction, so they never drift. Pass a `ClientRequestToken` to make the transaction idempotent — a retried call with the same token does not double-apply.

```python
client = boto3.client("dynamodb")

def create_project_consistently(org_id: str, project_id: str, name: str, idem_token: str):
    item_attrs = {
        "name": {"S": name}, "entityType": {"S": "Project"},
        "projectId": {"S": project_id}, "version": {"N": "1"},
    }
    client.transact_write_items(
        ClientRequestToken=idem_token,  # idempotent retry guard
        TransactItems=[
            {"Put": {  # row in the org partition (for "list projects in org")
                "TableName": "saas-single-table",
                "Item": {"PK": {"S": f"ORG#{org_id}"}, "SK": {"S": f"PROJ#{project_id}"}, **item_attrs},
                "ConditionExpression": "attribute_not_exists(PK)",
            }},
            {"Put": {  # anchor row in the project's own partition
                "TableName": "saas-single-table",
                "Item": {"PK": {"S": f"PROJ#{project_id}"}, "SK": {"S": f"PROJ#{project_id}"}, **item_attrs},
                "ConditionExpression": "attribute_not_exists(PK)",
            }},
        ],
    )
```

## 2.9 — Streams → Lambda fan-out

DynamoDB Streams is a 24-hour ordered log of item-level changes. With `StreamViewType = NEW_AND_OLD_IMAGES` each record carries the item before and after the change. A Stream has one shard per table partition, and records within a shard are strictly ordered. You attach a Lambda via an **event-source mapping**, which polls the Stream and invokes your function in batches.

The fan-out pattern: one Lambda consumes every change and does the downstream bookkeeping — maintain a denormalized projection, write the immutable audit log, push to EventBridge (Week 10). Key event-source-mapping knobs: `BatchSize` (records per invoke), `MaximumBatchingWindowInSeconds` (latency/throughput trade), `ParallelizationFactor` (concurrent invokes per shard, up to 10), `BisectBatchOnFunctionError` (on failure, split the batch and retry halves to isolate the poison pill), `FilterCriteria` (server-side filtering so you only pay for invokes you care about), and `FunctionResponseTypes: [ReportBatchItemFailures]` for partial-batch-failure handling.

```python
"""stream_handler.py — Streams -> Lambda fan-out with partial-batch-failure."""
from boto3.dynamodb.types import TypeDeserializer
_d = TypeDeserializer()

def deserialize(image: dict) -> dict:
    return {k: _d.deserialize(v) for k, v in image.items()}

def handler(event, _ctx):
    failures = []
    for record in event["Records"]:
        try:
            name = record["eventName"]               # INSERT | MODIFY | REMOVE
            new = record["dynamodb"].get("NewImage")
            old = record["dynamodb"].get("OldImage")
            is_ttl = record.get("userIdentity", {}).get("principalId") == "dynamodb.amazonaws.com"
            if name in ("INSERT", "MODIFY") and new:
                project_audit_entry(deserialize(new), deserialize(old) if old else None)
            elif name == "REMOVE" and old:
                record_deletion(deserialize(old), via_ttl=is_ttl)
        except Exception:
            # Report only the failed record so the rest of the batch commits.
            failures.append({"itemIdentifier": record["dynamodb"]["SequenceNumber"]})
    return {"batchItemFailures": failures}
```

The CDK to wire it, with the production knobs set:

```typescript
import { StartingPosition } from 'aws-cdk-lib/aws-lambda';
import { DynamoEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';

fanoutFn.addEventSource(new DynamoEventSource(table, {
  startingPosition: StartingPosition.TRIM_HORIZON,
  batchSize: 100,
  maxBatchingWindow: cdk.Duration.seconds(5),
  parallelizationFactor: 2,
  bisectBatchOnError: true,
  retryAttempts: 3,
  reportBatchItemFailures: true,   // pairs with the handler's batchItemFailures
}));
```

## 2.10 — On-demand vs provisioned, with the dollar figures

This is the decision the Friday challenge makes you defend with numbers. The two modes, at 2026 us-east-1 list prices (always re-check `aws.amazon.com/dynamodb/pricing` — the numbers move):

**On-demand (pay-per-request).** You pay per request: roughly **$1.25 per million WCU** and **$0.25 per million RCU** (eventually consistent). No capacity to manage, scales instantly to any volume, scales to zero when idle (you pay nothing for an idle table beyond storage). The trade: per-request cost is ~6–7× the per-request cost of fully-utilized provisioned capacity.

**Provisioned.** You pay per *provisioned* capacity-hour whether you use it or not: roughly **$0.00065 per WCU-hour** and **$0.00013 per RCU-hour**. With Application Auto Scaling, the provisioned floor tracks demand within a target-utilization band (default 70%). Reserved capacity buys a further discount (up to ~50–75%) for a 1- or 3-year commitment on a steady baseline.

The break-even rule of thumb: **provisioned wins for steady, predictable, high-utilization workloads; on-demand wins for spiky, unpredictable, or low-utilization workloads.** The crossover is roughly *if your sustained utilization exceeds ~15–20% of peak, provisioned-with-autoscaling is cheaper.* Worked profiles for the challenge:

- **Steady-state** (constant 500 WCU, 24/7): provisioned at 500 WCU = `500 × $0.00065 × 730h ≈ $237/mo`. On-demand for the same volume = `500 × 3600 × 730 / 1e6 × $1.25 ≈ $1,642/mo`. **Provisioned wins ~7×.** Add reserved capacity and provisioned wins ~15×.
- **Idle** (table provisioned but ~0 traffic): provisioned still bills the floor (autoscaling minimum, say 5 WCU = ~$2.40/mo). On-demand bills ~$0. **On-demand wins.**
- **Burst** (1 hour/day at 5,000 WCU, near-zero otherwise): on-demand bills only the burst hour ≈ `5000 × 3600 × 30 / 1e6 × $1.25 ≈ $675/mo`. Provisioned must either provision for the peak (`5000 × $0.00065 × 730 ≈ $2,372/mo`, mostly wasted) or rely on autoscaling, which lags spiky load and throttles during the ramp. **On-demand wins on cost *and* on not-throttling.**

The senior answer is rarely "pick one for the whole table." It is: **on-demand while you are learning the traffic shape, then provisioned-with-autoscaling once the baseline is known and steady, then reserved capacity on the proven floor.** You can switch modes once every 24 hours, so the migration is operationally cheap. The challenge has you measure each profile and write that recommendation.

## 2.11 — Global Tables and DAX, briefly

**Global Tables** replicate your table to multiple regions, active-active, with last-writer-wins conflict resolution (each replica adds a region attribute and the highest timestamp wins). You write to any region, reads are local and fast, replication lag is typically under a second. It is the multi-region DR answer (Week 13). The cost: replicated writes are billed in *every* region, and you pay cross-region data transfer. Design your keys for it now — a Global Table is a one-line change *if* your keys are region-agnostic, and a full re-model if you baked a region into a key.

**DAX** (DynamoDB Accelerator) is a write-through, in-memory cache that sits in front of the table and serves cached reads in *microseconds* instead of milliseconds. It earns its keep for read-heavy workloads with hot keys and repeated reads of the same items. It does *not* help write-heavy workloads, it adds cluster cost (you run DAX nodes), and it introduces a cache-coherence surface. Reach for DAX only after you have proven a read-latency or read-cost problem that caching actually solves — not as a default.

## 2.12 — The comparators: Scylla, Cassandra, FoundationDB

You will be asked, in a design review, "why not Cassandra?" Have the answer.

- **Apache Cassandra** is the wide-column ancestor. Same query-first modeling discipline (you design tables per query, denormalize aggressively), but *you* run the cluster — nodes, repair, compaction, tuning. DynamoDB is Cassandra's modeling philosophy as a fully-managed, serverless service. Choose Cassandra when you need to self-host (on-prem, sovereignty), choose DynamoDB when you want AWS to run it.
- **ScyllaDB** is Cassandra rewritten in C++ with a shard-per-core architecture, and its **Alternator** mode speaks the DynamoDB API. It is dramatically more throughput-per-node than Cassandra and is the go-to when you have outgrown DynamoDB's pricing at extreme scale and are willing to operate infrastructure. The migration path is real: the same single-table model runs against Scylla Alternator.
- **FoundationDB** is a different animal — an ordered, transactional key-value store with full ACID multi-key transactions, on top of which you build "layers" (a document layer, a SQL layer). Apple and Snowflake run it at scale. Choose it when you need strict serializable transactions across arbitrary keys, which DynamoDB's 100-item `TransactWriteItems` does not give you.

The instinct to develop: DynamoDB is the *managed* choice with the best operational story on AWS; the open-source comparators are what you reach for when you have outgrown the price, need to self-host, or need stronger transactional semantics. Name the trade-off you took.

## 2.13 — Diagnosing a throttle from CloudWatch — a runbook

The exercises and the mini-project ask you to *prove* a hot partition into existence and then prove the mitigation. "Prove" means metrics, not vibes. Here is the runbook you will follow, and the one you'll carry into the capstone chaos drill in Week 15.

**The metrics that matter.** DynamoDB publishes these to CloudWatch under `AWS/DynamoDB`, dimensioned by `TableName` (and, for index metrics, `GlobalSecondaryIndexName`):

| Metric | What it tells you | What "bad" looks like |
| --- | --- | --- |
| `ConsumedWriteCapacityUnits` | Actual WCU consumed | Flat-lined at a ceiling while offered load climbs → partition wall |
| `WriteThrottleEvents` | Individual writes that got throttled | Any sustained non-zero value is a problem |
| `ThrottledRequests` | Requests rejected for throughput | The first alarm you should wire |
| `ReadThrottleEvents` | Throttled reads | Same story on the read side |
| `OnlineIndexThrottleEvents` | A GSI throttling independently of the base table | A GSI under-provisioned relative to the base table |

The trap beginners fall into: they look at *table-level* `ConsumedWriteCapacityUnits`, see it well under the provisioned ceiling, and conclude "we have headroom, why are we throttling?" The answer is that table-level consumption is an **average across all partitions**. One partition can be melting at 1,000 WCU while the table average sits at 200. The table metric hides the hot partition. This is the single most important thing to internalize about throttling diagnosis: **the table is fine; one partition is on fire.**

**Finding *which* key is hot.** Enable **CloudWatch Contributor Insights for DynamoDB** on the table (one toggle in CDK: `contributorInsights: true` on the table props, or per-GSI). It publishes "most accessed keys" and "most throttled keys" rules, and within minutes of a throttle you can read the actual partition-key value that is hot — no guessing. Turn it on *before* you run the exercise-2 hammer; it makes the diagnosis a screenshot instead of a hunch.

```typescript
this.table = new TableV2(this, 'SaasTable', {
  // ...keys, billing, stream as before...
  contributorInsights: true, // surfaces the hottest and most-throttled keys
});
```

**The alarm you wire.** A production table gets a CloudWatch alarm on `ThrottledRequests > 0` sustained over a few minutes, routed to your on-call channel. In CDK:

```typescript
import { Alarm, ComparisonOperator, TreatMissingData } from 'aws-cdk-lib/aws-cloudwatch';

new Alarm(this, 'ThrottleAlarm', {
  metric: this.table.metricThrottledRequestsForOperations({
    operations: [Operation.PUT_ITEM, Operation.QUERY, Operation.GET_ITEM],
    period: cdk.Duration.minutes(1),
  }),
  threshold: 0,
  evaluationPeriods: 3,
  comparisonOperator: ComparisonOperator.GREATER_THAN_THRESHOLD,
  treatMissingData: TreatMissingData.NOT_BREACHING,
  alarmDescription: 'DynamoDB is throttling — likely a hot partition. Check Contributor Insights.',
});
```

**The decision tree once it fires.** When that alarm pages you:

1. **Open Contributor Insights** → read the hot key. Is it one key, or a uniform spread? One key → hot partition; uniform spread → genuinely under-provisioned, raise capacity (or it's on-demand and you've hit an account-level limit — open a support ticket for a limit increase).
2. **Is the hot key write-heavy or read-heavy?** Write-heavy → write-sharding (§2.6). Read-heavy and cacheable → DAX (§2.11), or split the read across an eventually-consistent GSI replica. Read-heavy and *not* cacheable → you may need to re-think the access pattern.
3. **Is it a GSI throttling, not the base table?** (`OnlineIndexThrottleEvents`.) The GSI is under-provisioned relative to its write volume — raise the GSI's capacity, or reduce its projection so writes to it are cheaper.
4. **Is it transient (a launch spike) or structural (a whale tenant)?** Transient → on-demand absorbs it; let adaptive capacity catch up. Structural → it will recur; fix the key design, do not just raise the ceiling.

The whole point of exercise 2 → exercise 3 is to walk this tree once with your own hands so that when it pages you at 2am in Week 15, the muscle memory is already there.

One last habit: after any mitigation, re-run the load and confirm `ThrottledRequests` returns to zero *and* `ConsumedWriteCapacityUnits` now climbs past the old ceiling. A fix you cannot see in the metrics is a fix you cannot defend in a review.

## 2.14 — Where this goes

You now have the full toolkit: GSIs for the patterns the base key cannot serve, sparse indexes for status filters, write-sharding for the hot partition, TTL for ephemera, conditional writes and transactions for consistency, Streams for fan-out, and the capacity math to pick a billing mode with a dollar figure. The exercises put each into practice: build the single-table app, hammer a partition until it throttles and add a GSI, then shard it and prove the throttle disappears. The challenge makes you do the cost comparison for real. The mini-project assembles all of it into the capstone's DynamoDB store.

The bar, restated: every read is one `GetItem` or `Query`, no scans in the hot path, the hot partition is provably mitigated, and you can defend your billing mode with the math. That is the hardest mental model in the AWS catalog. Once you have it, you have it.

---

*Next: the exercises. Build it, break it, fix it.*
