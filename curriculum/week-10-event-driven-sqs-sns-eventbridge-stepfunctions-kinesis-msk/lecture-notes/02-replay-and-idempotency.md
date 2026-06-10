# Lecture 2 — Replay and Idempotency: DLQs, EventBridge Archive, and Poison-Pill Handling

> Every distributed message system is at-least-once unless you pay for less, and at-least-once means your consumers must be idempotent or your data will be wrong. This is not an advanced topic you bolt on later. It is the load-bearing wall. We build it first.

---

## 0. The contract nobody reads but everybody signs

When you `SendMessage` to SQS, `Publish` to SNS, `PutEvents` to EventBridge, or `PutRecord` to Kinesis, you are signing an **at-least-once delivery** contract. Read it carefully because every word costs you:

- **At-least-once** means a message will be delivered *one or more* times. Not exactly once. One *or more*.
- SQS standard explicitly delivers duplicates — it is in the docs as a first-class behaviour, not a bug.
- SNS retries on transient subscriber failure and can deliver the same notification twice.
- EventBridge retries failed target deliveries for up to **24 hours** with exponential backoff — every retry is a potential duplicate.
- A Lambda event-source mapping that processes a batch of 10 SQS messages and throws on message 7 will, by default, **re-deliver all 10** — including the 6 you already processed successfully.

The consequence is blunt: **if processing a message twice does something different from processing it once, your system is wrong, and at-least-once will eventually expose it.** Charging a card twice. Shipping an order twice. Incrementing a counter twice. Sending two "your order shipped" emails. These are not edge cases you might hit; they are the *default behaviour* of the platform you are building on.

There are exactly two ways to survive this:

1. **Make the operation naturally idempotent** — design it so applying it twice equals applying it once (a `SET balance = 100`, not a `balance = balance - 10`).
2. **Add an idempotency layer** — record that you have seen this message's idempotency key, and on a repeat, skip the side effect.

Most real operations are not naturally idempotent (charging a card is fundamentally "do this once"), so you build the layer. The rest of this lecture is how.

---

## 1. The idempotency key — choosing it is the hard part

An **idempotency key** is the stable identifier that says "these two messages are the same logical operation." The whole scheme lives or dies on choosing it well.

Bad keys:

- **The message ID** (SQS `MessageId`, EventBridge `id`). These are *per-delivery*, so a re-delivery has a *different* ID. Using them as the idempotency key makes every duplicate look unique — useless.
- **A hash of the entire payload** including timestamps. The same logical order re-sent a second later hashes differently because the timestamp moved.

Good keys:

- **A business identifier that is stable across re-deliveries**: `order#7781`, `payment-intent-abc123`, `userId#42:signup`. The producer assigns it; it survives every retry and replay because it is part of the *meaning* of the event, not the *transport*.
- **A deterministic hash of the idempotent subset** of the payload — the business fields, excluding transport metadata and timestamps — when no natural business ID exists.

In this week's pipeline, the producer (the API Gateway → Lambda front door) generates an `orderId` and puts it in the event `detail`. *That* is the idempotency key. It rides through EventBridge, into SQS, into the consumer, and into a replay six days later — unchanged. That stability is what makes replay safe.

---

## 2. The DynamoDB conditional-write pattern (by hand)

The mechanical core of idempotency on AWS is a **DynamoDB conditional write** — the same primitive you learned in Week 9. The consumer, before doing the side effect, tries to *claim* the idempotency key:

```python
import boto3
import time
from botocore.exceptions import ClientError

ddb = boto3.client("dynamodb")
TABLE = "idempotency"
TTL_SECONDS = 7 * 24 * 3600  # keep claims for 7 days, then let TTL expire them


def claim(idempotency_key: str) -> bool:
    """Return True if we just claimed the key (first time we've seen it),
    False if it was already claimed (a duplicate)."""
    now = int(time.time())
    try:
        ddb.put_item(
            TableName=TABLE,
            Item={
                "pk": {"S": f"idem#{idempotency_key}"},
                "status": {"S": "IN_PROGRESS"},
                "createdAt": {"N": str(now)},
                "expiresAt": {"N": str(now + TTL_SECONDS)},
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False  # someone (maybe us, a duplicate) already claimed it
        raise


def complete(idempotency_key: str, result: str) -> None:
    ddb.update_item(
        TableName=TABLE,
        Key={"pk": {"S": f"idem#{idempotency_key}"}},
        UpdateExpression="SET #s = :done, #r = :result",
        ExpressionAttributeNames={"#s": "status", "#r": "result"},
        ExpressionAttributeValues={
            ":done": {"S": "COMPLETED"},
            ":result": {"S": result},
        },
    )


def process_order(event_detail: dict) -> None:
    key = event_detail["orderId"]  # the stable business key
    if not claim(key):
        print(f"idempotency hit for key {key} -> skipped (already processed)")
        return
    # ---- the side effect that must happen exactly once ----
    charge_card(event_detail["customerId"], event_detail["amount"])
    complete(key, "charged")
    print(f"processed {key}")
```

The `attribute_not_exists(pk)` condition is the whole trick: only the *first* writer of a given key succeeds; every subsequent writer gets `ConditionalCheckFailedException` and knows it is a duplicate. DynamoDB serializes the conditional write, so even two concurrent deliveries of the same message race safely — exactly one wins the claim.

Two refinements that separate a toy from production:

- **The `IN_PROGRESS` → `COMPLETED` lifecycle** handles the consumer that claims the key, starts the side effect, then crashes before completing. A naive "key exists → skip" would mark a *failed* operation as done. By recording status, a recovery path can detect a stale `IN_PROGRESS` claim (older than the visibility timeout) and safely retry.
- **TTL on `expiresAt`** keeps the idempotency table from growing forever. Set it to comfortably longer than your replay window — if you might replay 7-day-old events, keep claims at least 7 days, or the replay sees no claim and re-does the side effect.

---

## 3. Powertools `@idempotent` — the same pattern, productized

Hand-rolling the conditional write is good for understanding it. In production we use **Powertools for AWS Lambda (Python)**, which packages exactly this pattern — claim, status lifecycle, response caching, TTL — behind a decorator:

```python
from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer,
    IdempotencyConfig,
    idempotent_function,
)

persistence = DynamoDBPersistenceLayer(table_name="idempotency")
config = IdempotencyConfig(
    event_key_jmespath="orderId",   # extract the idempotency key from the payload
    expires_after_seconds=7 * 24 * 3600,
    use_local_cache=True,           # in-process cache for same-invocation duplicates
)


@idempotent_function(
    data_keyword_argument="order",
    persistence_store=persistence,
    config=config,
)
def process_order(order: dict) -> dict:
    charge_card(order["customerId"], order["amount"])
    return {"orderId": order["orderId"], "status": "charged"}
```

`event_key_jmespath="orderId"` tells Powertools which field is the idempotency key. The decorator does the conditional claim, and crucially **caches the return value**: a duplicate invocation does not re-run the body — it returns the *stored result* of the first run. That last property matters for synchronous callers (API Gateway, Step Functions) that expect a consistent response even on a retry. This is the mechanism the exercises and mini-project use; the hand-rolled version above is so you know what it is doing under the hood.

---

## 4. Dead-letter queues on *every* consumer

A **dead-letter queue** is where a message goes after it has failed the maximum number of retries. Without one, a poison pill — a message that will *never* succeed — loops forever (burning money and retry budget) or, on an ordered source, blocks every message behind it. DLQs are not optional decoration; they are the failure boundary that keeps one bad message from taking down the pipeline.

Every consumer in this week's pipeline gets a DLQ. The mechanics differ by source:

### SQS → Lambda

The DLQ goes on the **SQS queue** via its redrive policy (Lecture 1). After `maxReceiveCount` failed receives, SQS itself moves the message to the DLQ. The Lambda mapping should also use **partial batch response** (`ReportBatchItemFailures`) so a single bad record in a batch does not re-deliver the whole batch:

```python
def handler(event, context):
    batch_item_failures = []
    for record in event["Records"]:
        try:
            process(record)
        except Exception:
            batch_item_failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": batch_item_failures}
```

Only the failed `messageId`s are returned to SQS for retry; the successful ones are deleted. Without this, message 7 failing re-delivers messages 1–10 and your idempotency layer earns its salary on the six you already processed.

### SNS → (subscriber)

SNS subscriptions take a **redrive policy** pointing at an SQS DLQ. If SNS exhausts its delivery retries to a subscriber (e.g. a Lambda that keeps erroring, or an HTTP endpoint returning 500), the undeliverable notification lands in that DLQ instead of vanishing.

### EventBridge rule → target

Each EventBridge **target** can specify a **DLQ** (an SQS queue) and a **retry policy** (`MaximumRetryAttempts`, `MaximumEventAgeInSeconds`). If EventBridge cannot deliver to the target within those bounds, the event goes to the target's DLQ. Configure it per target — a flaky target should not silently drop events.

### Lambda event-source mapping (Kinesis / DynamoDB streams)

Stream sources are ordered, so a poison record blocks the whole shard. Three knobs save you:

- **`BisectBatchOnFunctionError`** — on failure, split the batch in half and retry each half, recursively, until the poison record is isolated to a batch of one. The good records get processed; the bad one is isolated.
- **`MaximumRecordAgeInSeconds`** — discard records older than this so a stuck poison record cannot block the shard forever.
- **`MaximumRetryAttempts`** — cap retries per record.
- **`DestinationConfig.OnFailure`** — send the metadata of the failed record to an SQS or SNS **on-failure destination** (the stream's DLQ) so you can inspect it.

```python
# CDK: a Kinesis event source with poison-pill defenses
fn.add_event_source(
    KinesisEventSource(
        stream,
        starting_position=StartingPosition.TRIM_HORIZON,
        batch_size=100,
        bisect_batch_on_error=True,
        retry_attempts=3,
        max_record_age=Duration.hours(1),
        on_failure=SqsDlq(stream_dlq),
        report_batch_item_failures=True,
    )
)
```

---

## 5. The poison-pill drill

A **poison pill** is a message that will fail every time it is processed — a malformed payload, a missing required field, a reference to a resource that no longer exists. The drill proves your DLQs work *before* a real one shows up at 3 a.m.

The drill, end to end:

1. Send a deliberately malformed order to the pipeline — an `OrderPlaced` event with no `customerId`. The validator Lambda will throw `ValidationError` every time.
2. Watch it get received and fail, received and fail, received and fail — `maxReceiveCount` times.
3. Watch it land in the DLQ named for the consumer that rejected it — `order-validator-dlq`, *not* some generic catch-all. The name tells the on-call engineer *which* consumer choked.
4. Confirm the message in the DLQ has its **full original payload** intact, so it can be inspected and (after a fix) redriven back to the source queue with the SQS console's "Start DLQ redrive" or `aws sqs start-message-move-task`.
5. Confirm the *rest* of the pipeline kept running — good orders flowed through while the poison pill was dying.

The output you are looking for:

```
[order-validator] processing msg 3f2a... attempt 1/3 -> ValidationError: missing customerId
[order-validator] processing msg 3f2a... attempt 2/3 -> ValidationError: missing customerId
[order-validator] processing msg 3f2a... attempt 3/3 -> ValidationError: missing customerId
[order-validator] msg 3f2a... exceeded maxReceiveCount=3 -> moved to order-validator-dlq
[order-validator] (meanwhile) processed 4,812 good orders, 0 blocked
```

A pipeline that only works on the happy path is a demo. A pipeline where the poison pill dies *quietly, in the right place, with its payload intact, without blocking anything else* is a system.

---

## 6. The EventBridge archive replay drill

Now the other half — replaying good history through an idempotent consumer.

The scenario: a bug shipped at 14:00, you rolled it back at 16:00, and during those two hours the consumer silently dropped 1,284 valid `OrderPlaced` events on the floor. Those orders never got charged. You need to reprocess them, *without* re-charging any order that somehow did get through, and *without* double-charging any order you replay that was actually fine.

The steps:

1. **Create the archive ahead of time** (you cannot replay what you did not archive). Scope it to the custom bus and a pattern covering your order events:

   ```bash
   aws events create-archive \
     --archive-name orders-archive \
     --event-source-arn arn:aws:events:eu-west-1:111122223333:event-bus/crunch-orders-bus \
     --retention-days 30 \
     --event-pattern '{"source":["com.crunch.orders"]}'
   ```

2. **Start a replay** over the exact window of the incident:

   ```bash
   aws events start-replay \
     --replay-name reprocess-2026-06-08 \
     --event-source-arn arn:aws:events:eu-west-1:111122223333:archive/orders-archive \
     --event-start-time 2026-06-08T14:00:00Z \
     --event-end-time   2026-06-08T16:00:00Z \
     --destination '{"Arn":"arn:aws:events:eu-west-1:111122223333:event-bus/crunch-orders-bus","FilterArns":["arn:aws:events:eu-west-1:111122223333:rule/crunch-orders-bus/order-validator-rule"]}'
   ```

   The replay re-emits the archived events onto the bus, re-evaluating the rules you target with `FilterArns`. Your consumers receive them exactly as if they were live.

3. **Watch idempotency do its job.** Every replayed event whose `orderId` was *already* successfully processed hits the idempotency table's claimed key and is skipped — no second charge. Every event that was genuinely dropped finds no claim, processes, and charges exactly once.

   ```
   [replay] EventBridge replay 'reprocess-2026-06-08' STARTING
   [order-validator] idempotency hit for key order#7781 -> skipped (already processed)
   [order-validator] processed order#8123 (was dropped during incident) -> charged
   [order-validator] idempotency hit for key order#7782 -> skipped (already processed)
   [replay] EventBridge replay 'reprocess-2026-06-08' COMPLETED · 1,284 events
   ```

This is why idempotency is the *first* thing you build, not the last. The replay is only safe because the consumer was idempotent from commit one. Build the consumer naively and a replay turns a two-hour outage into a finance incident — every customer who ordered during the window, charged twice.

---

## 7. Ordering and replay across the five primitives

A note on how replay and ordering interact per service, because the challenge will make you compare them:

| | Replay mechanism | Ordering during replay |
|---|---|---|
| **SQS standard** | none (deleted after processing) | n/a |
| **SQS FIFO** | none | n/a |
| **SNS** | none (no retention) | n/a |
| **EventBridge** | archive → `start-replay` over a time window | **no ordering** — replay re-emits roughly chronologically but with no guarantee |
| **Kinesis** | re-read shard from a sequence number / timestamp | **per-shard order preserved** on replay |
| **MSK** | re-read partition from an offset | **per-partition order preserved** on replay |

This is a genuine trade-off the challenge forces you to defend. EventBridge replay is *operationally* the easiest — one CLI call, a time window, done — but it gives you **no ordering guarantee**, so it only works when your consumers are idempotent *and* order-independent. Kinesis and MSK replay preserve order (within a shard/partition) because you replay by *offset*, but you own more machinery to do it. If your reprocessing must happen in order — say, a sequence of balance adjustments — EventBridge replay is the wrong tool and you need Kinesis/MSK. For independent, idempotent order events, EventBridge replay is exactly right.

---

## 7a. Redrive — getting a fixed message *out* of the DLQ

A DLQ is not a graveyard; it is an inspection-and-recovery queue. Messages land there *because they failed*, and the operational story does not end there — once you understand *why* they failed and ship a fix, you redrive them back to the source queue to be processed normally.

SQS has a first-class **DLQ redrive** for exactly this. From the console it is the "Start DLQ redrive" button; from the CLI it is a message-move task:

```bash
# Find the ARNs
SRC=$(aws sqs get-queue-attributes --queue-url "$VALIDATOR_QUEUE_URL" \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)
DLQ=$(aws sqs get-queue-attributes --queue-url "$VALIDATOR_DLQ_URL" \
  --attribute-names QueueArn --query Attributes.QueueArn --output text)

# Move everything from the DLQ back to the source queue (after you've shipped the fix)
aws sqs start-message-move-task \
  --source-arn "$DLQ" \
  --destination-arn "$SRC" \
  --max-number-of-messages-per-second 50
```

The discipline: **never redrive blindly.** A poison pill that is still poison will just loop back to the DLQ. The workflow is (1) inspect the DLQ messages, (2) identify the root cause, (3) ship the fix to the consumer, (4) *then* redrive. The `--max-number-of-messages-per-second` throttle exists so a redrive of 100k messages does not stampede a downstream that just recovered. Redrive at a rate the downstream can absorb.

For EventBridge target DLQs and Lambda on-failure destinations the message that lands is *metadata about the failure* (the original event plus error context), not always the raw original — read it to learn what happened, then replay the *source* (the archive) once you have fixed the consumer, rather than redriving the metadata.

## 7b. Why "exactly-once" is mostly a marketing word

You will hear "exactly-once" thrown around — SQS FIFO advertises "exactly-once *processing*," Kafka has "exactly-once *semantics*." Read the qualifier every time, because the honest engineering statement is narrower than the slide.

- **SQS FIFO "exactly-once processing"** holds *within the 5-minute deduplication window* and only deduplicates *producer sends* (by `MessageDeduplicationId` or content hash). It does not make your *consumer* exactly-once — if your consumer reads, does the side effect, then crashes before deleting the message, the message reappears after the visibility timeout and is processed again. The dedupe is on the *send*, not the *effect*.
- **Kafka "exactly-once semantics"** is real but scoped: it covers Kafka-to-Kafka transactional writes (consume-process-produce within Kafka). The moment your side effect leaves Kafka — charging a card, writing to an external DB — you are back to at-least-once and you need idempotency.

The durable truth: **the only exactly-once you actually get is the one you build, with an idempotency key and a conditional write at the boundary where the side effect happens.** Every "exactly-once" feature reduces the *rate* of duplicates; none of them eliminates the *need* for idempotency at the side-effect boundary. Treat the platform features as defense-in-depth, not as a reason to skip the idempotency layer.

## 7c. Ordering, retries, and the interaction nobody warns you about

One subtle trap when you combine ordering with retries: **retrying out of order breaks the ordering you paid for.** On an SQS FIFO queue, if message 3 in a group fails and goes back for retry while messages 4 and 5 succeed, FIFO *blocks* the group — 4 and 5 will not be delivered until 3 is resolved or dead-lettered, precisely to preserve order. That is correct behaviour, but it means a single poison pill in a FIFO group **stalls the entire group** until `maxReceiveCount` redrives it. Size `maxReceiveCount` low on FIFO groups where head-of-line blocking is expensive, and make sure the DLQ is wired, or one bad message holds up every message behind it in that customer's stream.

On a Kinesis shard the same physics apply: a poison record at the head of a shard blocks every record behind it until `bisectBatchOnFunctionError` isolates it or `maxRecordAge` ages it out. This is why the stream-source poison-pill defenses are not optional — without them, one bad record can freeze a shard indefinitely. Ordering is a feature you pay for not just in throughput but in *failure-domain coupling*: ordered things fail together.

## 8. The checklist you ship with

Before you call an event-driven pipeline "done," walk this list. The mini-project's rubric is this list:

- [ ] Every consumer has a DLQ **named for that consumer** (not a shared catch-all).
- [ ] `maxReceiveCount` is tuned to plausibly-recoverable retries (3 is a sane default).
- [ ] Visibility timeout = 6× the consumer's p99.
- [ ] Long polling on (`ReceiveMessageWaitTimeSeconds = 20`).
- [ ] Lambda SQS mappings return **partial batch failures** (`ReportBatchItemFailures`).
- [ ] Stream (Kinesis) mappings have `bisectBatchOnFunctionError`, `maxRecordAge`, and an on-failure destination.
- [ ] Every side-effecting consumer is **idempotent** on a stable business key (not a delivery ID).
- [ ] The idempotency table TTL is **longer than the replay window**.
- [ ] An EventBridge **archive** exists, scoped to the custom bus.
- [ ] You have **run the poison-pill drill** and watched the message land in the right DLQ while the rest of the pipeline kept flowing.
- [ ] You have **run the replay drill** and watched idempotency reject the duplicates.

If you cannot tick every box, the pipeline is not done — it is a happy-path demo waiting for at-least-once to find the gap. Build for replay and idempotency from the first commit, and the day you actually need them, they just work.

## 9. A short word on observability of all this

You cannot operate failure boundaries you cannot see. Two CloudWatch metrics are the minimum bar for this week (full tracing is Week 12):

- **`ApproximateNumberOfMessagesVisible` on every DLQ.** This should be **zero** in steady state. A non-zero DLQ depth means messages are dying and nobody noticed. Alarm on `> 0` for any DLQ — it is the single highest-signal alert in an event-driven system, because a message in a DLQ is, by definition, a thing your pipeline could not handle.
- **`ApproximateAgeOfOldestMessage` on every work queue.** Rising age means consumers are falling behind ingest — the SQS analogue of Kinesis's `IteratorAgeMilliseconds`. A queue whose oldest message keeps getting older is a queue heading for a back-pressure incident.

Add one more for the idempotency layer: a metric (or a structured log field) counting **idempotency hits** — how often the conditional write found an existing claim. A sudden spike in idempotency hits with no replay running is a signal that something upstream is re-delivering far more than usual — a retry storm, a stuck consumer re-reading, a misconfigured `maxReceiveCount`. The idempotency table is not just protecting you; instrumented, it is also *telling you* about duplicate-delivery pathologies you would otherwise never see. Wire these three signals now and Week 12's tracing has something to hang off; skip them and you are flying a distributed system blind.

The thread running through this whole lecture: **at-least-once is the contract, idempotency is the discipline that survives it, DLQs are the failure boundary, and replay is the recovery tool — and none of them are optional.** They are the difference between a pipeline that survives the day a real poison pill arrives and one that becomes a finance incident. Build them in from commit one.
