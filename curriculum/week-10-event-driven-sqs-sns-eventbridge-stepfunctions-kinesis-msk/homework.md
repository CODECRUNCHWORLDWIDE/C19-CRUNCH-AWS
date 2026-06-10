# Week 10 — Homework

Six problems. They are smaller than the mini-project and each one drills a single muscle the mini-project assumes. Do them in your `dev` account, tear down what bills, and keep the artifacts — several feed straight into the mini-project.

Each problem lists a **deliverable** (what you hand in) and **acceptance criteria** (when it's done). The rubric at the bottom is how they're graded.

---

## HW1 — Size a visibility timeout from real numbers

**Deliverable:** a one-paragraph note and the CDK/CLI snippet that sets the timeout.

A consumer's processing latency over 1,000 invocations is: p50 = 1.2 s, p95 = 3.8 s, p99 = 5.1 s, max = 9.7 s. The queue currently has the default 30 s visibility timeout.

- Compute the visibility timeout you'd set using the 6×-p99 rule.
- Explain in two sentences why you size on p99, not the mean, and what the `ChangeMessageVisibility` heartbeat is for given that max = 9.7 s.
- Provide the one line of CDK (`visibilityTimeout: cdk.Duration.seconds(...)`) and the one `aws sqs set-queue-attributes` CLI equivalent.

**Acceptance:** the number is 6 × 5.1 = ~31 s (round to 35 s); the note correctly explains that p99 covers the slow tail without over-leasing, and the heartbeat handles the rare 9.7 s outlier without padding every message's lease.

---

## HW2 — Write three EventBridge event patterns

**Deliverable:** three JSON event patterns, each with the test event it matches and one it rejects.

Given `OrderPlaced` events with `source: "com.crunch.orders"` and a `detail` of `{ orderId, customerId, amount, region, channel }`, write patterns that match:

1. Orders with `amount >= 1000` from any region **except** `eu-west-1`.
2. Orders whose `channel` is `web` **or** `mobile` (not `partner`).
3. Orders where `customerId` exists **and** starts with `vip#`.

**Acceptance:** each pattern uses the correct operator (`numeric`, `anything-but`, `$or` or array-of-values, `exists`, `prefix`); each is accompanied by a matching and a non-matching sample event; patterns validate with `aws events test-event-pattern --event-pattern file://p1.json --event file://e1.json`.

---

## HW3 — Build the idempotency layer two ways

**Deliverable:** two short Python files that pass the same test.

Implement an idempotent `charge(order)` function:

1. **By hand** — DynamoDB `PutItem` with `attribute_not_exists(pk)`, an `IN_PROGRESS`/`COMPLETED` status lifecycle, and a TTL attribute.
2. **With Powertools** — the `@idempotent_function` decorator with a `DynamoDBPersistenceLayer` and `event_key_jmespath`.

Then write a test that calls each `charge` twice with the same `order` and asserts the side effect (an append to a `charges` list, or a counter) fires **exactly once**.

**Acceptance:** both implementations pass the double-call test; the hand-rolled one handles the `ConditionalCheckFailedException` path; both set a TTL ≥ 7 days; you can explain in one sentence what Powertools caches that the hand-rolled version doesn't (the stored *result* of the first run).

---

## HW4 — Wire a DLQ on three different sources

**Deliverable:** CDK snippets attaching a DLQ to (a) an SQS queue, (b) an EventBridge rule target, and (c) a Kinesis Lambda event-source mapping, plus a two-sentence note per source on *where* the DLQ lives and *what* triggers the move.

**Acceptance:** (a) uses `deadLetterQueue: { queue, maxReceiveCount }`; (b) uses the target's `deadLetterQueue` + `retryAttempts`/`maxEventAge`; (c) uses `onFailure: new SqsDlq(...)` + `bisectBatchOnError` + `maxRecordAge`; the notes correctly distinguish "SQS moves after maxReceiveCount receives" from "EventBridge moves after exhausting target retries" from "Lambda mapping sends failed-record metadata to the on-failure destination."

---

## HW5 — The Standard-vs-Express crossover

**Deliverable:** a short spreadsheet or Python script and a one-line conclusion.

A workflow has **8 states**. Compute the monthly cost on **Standard** (billed per state transition) and **Express** (billed per execution-duration; assume 250 ms at 256 MB) at three volumes: **1,000/day, 100,000/day, 10,000,000/day**. Use the current Step Functions pricing (Standard ~$25 per million state transitions; Express ~$1.00 per million requests + GB-second duration — confirm on the pricing page).

- Produce a 3×2 table of monthly costs.
- State the approximate crossover volume where Express becomes cheaper than Standard.

**Acceptance:** the table is computed (not guessed); the crossover is stated with the assumption that drives it (state count and duration); the conclusion names which side of the crossover the mini-project's per-order saga sits on (Express).

---

## HW6 — The decision table from memory

**Deliverable:** the five-primitives decision table (SQS std, SQS FIFO, SNS, EventBridge, Kinesis, MSK) reproduced **from memory**, then checked against Lecture 1.

Fill the rows: point-to-point, fan-out, ordering, replay, content routing, schema registry, throughput ceiling, latency, pay-when-idle, operational burden. Then, in three sentences each, defend a choice for these scenarios:

1. A work queue for thumbnail generation; duplicates are harmless; one consumer.
2. Notify billing, shipping, and analytics independently of an order; no replay needed; low latency.
3. An ordered stream of IoT telemetry that three independent teams replay for their own models.

**Acceptance:** the table matches Lecture 1 (allow per-group/per-shard nuance); the three defenses name the primitive *and* the disqualifier for the runner-up (e.g. "SQS not SNS because thumbnails need a work queue, not fan-out"; "SNS not EventBridge because no replay needed and we want lower latency"; "Kinesis not SNS because three teams need independent replay of an ordered stream").

---

## Rubric (30 points)

| Criterion | Points |
|---|---|
| HW1 — visibility timeout sized correctly + heartbeat reasoning | 4 |
| HW2 — three patterns correct, each with match/reject samples, all validate | 5 |
| HW3 — both idempotency implementations pass the double-call test | 6 |
| HW4 — three DLQ wirings correct + accurate per-source notes | 5 |
| HW5 — crossover table computed + correct conclusion | 5 |
| HW6 — decision table accurate + three defended choices | 5 |
| **Total** | **30** |

**Passing is 24/30.** Below that, the gap is almost always HW3 (idempotency) or HW6 (the decision table) — the two things the mini-project and the capstone lean on hardest. Re-read Lecture 2 for the first and Lecture 1 for the second, then resubmit.

## Submission

One folder, one `README.md` indexing the six deliverables, each in its own file or subfolder. Tear down any queues, tables, or streams you created — homework should leave no billing footprint overnight.
