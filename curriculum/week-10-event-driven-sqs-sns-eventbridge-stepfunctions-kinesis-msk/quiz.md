# Week 10 — Quiz

Thirteen questions on the eventing layer. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 11. Answer key with explanations at the bottom — don't peek.

---

**Q1.** A teammate sets an SQS queue's visibility timeout to the default 30 seconds. The consumer's p99 processing time is 45 seconds. What goes wrong, and what is the rule of thumb?

- A) Nothing; SQS extends the timeout automatically when the consumer is busy.
- B) The message becomes visible again at 30 s while the first consumer is still working, so a second consumer picks it up and processes it twice. Rule: visibility timeout ≈ 6× the consumer's p99 (or use a `ChangeMessageVisibility` heartbeat).
- C) The message is deleted after 30 s regardless of processing. Rule: never set a visibility timeout below 60 s.
- D) SQS moves the message straight to the DLQ at 30 s. Rule: disable the DLQ for slow consumers.

---

**Q2.** You need per-customer ordering at high aggregate throughput. Which design is correct?

- A) SQS FIFO with a single `MessageGroupId` for all messages.
- B) SQS FIFO with `MessageGroupId = customerId` — ordering within each customer, parallelism across customers.
- C) SQS standard, because standard preserves insertion order.
- D) SNS FIFO with no group id; SNS orders globally.

---

**Q3.** Why insert an SQS queue between SNS and each Lambda consumer instead of subscribing the Lambda directly to the SNS topic?

- A) SNS cannot invoke Lambda directly; the queue is mandatory.
- B) The queue gives each consumer its own buffer and retry domain, so a slow or failing consumer absorbs its own back-pressure without affecting the others.
- C) It is cheaper — SNS-to-Lambda is billed at a premium rate.
- D) It is required for message filtering; SNS filter policies only work on SQS subscriptions.

---

**Q4.** What does an SNS subscription **filter policy** save you, and where should filtering happen?

- A) Nothing measurable; it is cosmetic.
- B) It filters at the topic so non-matching messages are never delivered — saving delivery cost, consumer invocations, and idempotency work. Filter at the topic, not in every consumer.
- C) It compresses messages to reduce egress cost.
- D) It guarantees exactly-once delivery to matching subscribers.

---

**Q5.** Your team needs content-based routing of application events to four reactors, the ability to replay a window of events after a bad deploy, and a schema registry. Which primitive, and what is the main tax you accept?

- A) SNS; the tax is no message attributes.
- B) Kinesis Data Streams; the tax is shard management.
- C) EventBridge custom bus; the tax is ~500 ms of routing latency and no ordering guarantee.
- D) SQS FIFO; the tax is the 300 msg/s ceiling.

---

**Q6.** What is the correct idempotency key for an order event delivered at-least-once, possibly replayed days later?

- A) The SQS `MessageId`, because it uniquely identifies the message.
- B) The EventBridge event `id`, because EventBridge guarantees it is unique.
- C) A stable business identifier the producer assigns (e.g. `orderId`), because it survives every re-delivery and replay unchanged.
- D) A hash of the full payload including the `time` field, so each delivery is distinct.

---

**Q7.** Which DynamoDB operation is the mechanical core of the idempotency layer?

- A) A `Scan` with a filter expression for the key.
- B) A `PutItem` with `ConditionExpression="attribute_not_exists(pk)"` — only the first writer of a key succeeds; duplicates get `ConditionalCheckFailedException`.
- C) A `Query` on a GSI keyed by the idempotency key.
- D) A `BatchWriteItem` with `ReturnValues=ALL_OLD`.

---

**Q8.** A Lambda consumes a batch of 10 SQS messages and throws on message 7. With the default settings, what happens, and what fixes it?

- A) Only message 7 is retried automatically; nothing to fix.
- B) All 10 messages are re-delivered (including the 6 already processed). Fix: return partial batch failures (`ReportBatchItemFailures` / `batchItemFailures`) so only the failed `messageId`s are retried.
- C) The whole batch is sent straight to the DLQ. Fix: raise `maxReceiveCount`.
- D) Lambda silently drops the batch. Fix: enable CloudWatch logging.

---

**Q9.** On a Kinesis (or DynamoDB-stream) Lambda event-source mapping, which setting isolates a single poison record so the good records in its batch still get processed?

- A) `MaximumBatchingWindowInSeconds`
- B) `BisectBatchOnFunctionError` — split the batch in half on failure and retry each half recursively until the bad record is isolated to a batch of one.
- C) `ParallelizationFactor`
- D) `StartingPosition = LATEST`

---

**Q10.** You replay a window of `OrderPlaced` events from the EventBridge archive against your idempotent consumer. What is the expected result, and what property makes the replay safe?

- A) Every replayed event is processed again, re-charging customers; this is unavoidable.
- B) Events already processed hit the idempotency table's claimed key and are skipped; only genuinely-unprocessed events run. The consumer being idempotent on a stable key is what makes replay safe.
- C) EventBridge automatically deduplicates replays, so the consumer needs no idempotency.
- D) The replay fails because archives cannot be replayed onto the same bus.

---

**Q11.** Choose Step Functions Standard vs Express for: (a) a per-order saga that runs in ~200 ms at high volume, and (b) a monthly billing reconciliation that waits days for human approval.

- A) (a) Standard, (b) Express.
- B) (a) Express, (b) Standard — Express is sub-second/high-volume billed per execution-duration; Standard is durable/long-running billed per state transition.
- C) Both Express; Standard is deprecated.
- D) Both Standard; Express cannot do retries.

---

**Q12.** Map the Kafka concept onto its Kinesis Data Streams equivalent: **topic, partition, offset**.

- A) topic→shard, partition→stream, offset→partition key.
- B) topic→stream, partition→shard, offset→sequence number.
- C) topic→consumer group, partition→KCL app, offset→checkpoint table.
- D) topic→delivery stream, partition→buffer, offset→S3 prefix.

---

**Q13.** You need to "land event data in S3 so Athena can query it tomorrow," with Parquet conversion and date partitioning, and you don't want to run a consumer. Which service, and why not raw Kinesis Data Streams?

- A) Raw Kinesis Data Streams; it writes to S3 natively.
- B) SQS with an S3 redrive policy.
- C) Amazon Data Firehose — it is managed delivery that batches, converts to Parquet via a Glue table, and dynamically partitions, with no consumer to run. Raw Data Streams would make you write the batching, conversion, and S3 writer yourself.
- D) SNS with an S3 subscription.

---

---

## Answer key

**Q1 — B.** Visibility timeout is how long a received message stays invisible waiting for `DeleteMessage`. Set it below the consumer's processing time and the message reappears mid-flight and gets double-processed. Rule: ~6× p99, or extend the lease with a `ChangeMessageVisibility` heartbeat for long jobs.

**Q2 — B.** You almost never need a *global* order — you need order per entity. `MessageGroupId = customerId` gives strict ordering within each customer and parallelism across customers, which is the high-throughput shape. A single group id (A) serializes everything and caps you at the per-group ceiling.

**Q3 — B.** The queue is a shock absorber: each consumer gets its own buffer and retry domain, so a failing consumer fills *its* queue and drains later without harming the others. (SNS *can* invoke Lambda directly — A is false — but you lose the buffer.)

**Q4 — B.** Filter policies stop non-matching messages from ever being delivered. Filtering at the topic saves delivery cost, consumer invocations, and idempotency work versus delivering everything and dropping in each consumer.

**Q5 — C.** Content routing + replay + schema registry is the EventBridge custom-bus sweet spot. The taxes: ~500 ms routing latency and no ordering guarantee. SNS lacks replay and a schema registry; Kinesis lacks content routing.

**Q6 — C.** The key must be stable across re-deliveries and replays. Delivery IDs (A, B) change per delivery, so duplicates look unique — useless. A payload hash including `time` (D) changes per send. A producer-assigned business id like `orderId` is the right choice.

**Q7 — B.** `PutItem` with `attribute_not_exists(pk)` is the conditional claim: exactly one writer of a key wins; duplicates get `ConditionalCheckFailedException` and know to skip. This is what Powertools' `@idempotent` does internally.

**Q8 — B.** By default a single failure re-delivers the whole batch. `ReportBatchItemFailures` (returning `{"batchItemFailures":[{"itemIdentifier": id}, ...]}`) tells SQS to delete the successes and retry only the failed ids.

**Q9 — B.** `BisectBatchOnFunctionError` recursively halves a failing batch until the poison record is alone in a batch of one, so the good records still process. Pair it with `MaximumRecordAgeInSeconds`, `MaximumRetryAttempts`, and an on-failure destination.

**Q10 — B.** Replay re-emits archived events; the idempotency table skips any key already processed, so only genuinely-dropped events run, exactly once. Idempotency on a stable key is the property that makes replay safe — EventBridge does *not* dedupe replays for you (C is false).

**Q11 — B.** Express: sub-second, ≤5 min, billed per execution-duration, very high throughput → the per-order saga. Standard: durable, up to a year, billed per state transition, full history → the human-in-the-loop reconciliation.

**Q12 — B.** topic→stream, partition→shard, offset→sequence number. (consumer group→KCL app and producer key→partition key are the other rows of the map.)

**Q13 — C.** Amazon Data Firehose is managed delivery: buffering hints, Parquet conversion via a Glue table, dynamic partitioning, no consumer to run. Raw Data Streams hands you records and makes you build the writer yourself.

---

**Scoring:** 13/13 you can run the design review. 11–12 solid. 9–10 re-read Lecture 1's decision table and Lecture 2's idempotency section. Below 9, do the exercises again before the mini-project — the drills teach what the quiz tests.
