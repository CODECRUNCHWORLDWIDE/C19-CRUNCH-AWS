# Week 10 — Event-Driven AWS: SQS, SNS, EventBridge, Step Functions, Kinesis, MSK

Welcome to **C19 · Crunch AWS**, Week 10. Week 8 gave you Aurora and the relational mental model. Week 9 gave you DynamoDB single-table and the hardest data-modelling muscle in the catalog. This week we wire those data stores together with the part of AWS that nobody draws correctly on a whiteboard the first time: the **messaging and eventing layer**. By Friday you should be able to stand up an order-processing pipeline — API Gateway → Lambda → an EventBridge custom bus → SQS for retry-able work, Step Functions Express for orchestration, and Kinesis Firehose for analytics-to-S3 — with dead-letter queues on every consumer, a poison-pill message that lands in the *correct* DLQ, and an EventBridge archive you can replay through an idempotent consumer without double-charging a customer.

This is the eventing week, and it is the week that the rest of the course leans on. The EventBridge custom bus you build here is the **capstone's event spine** (see the capstone spec in `SYLLABUS.md`). It is the system you will **instrument with OpenTelemetry in Week 12** and the system you will **chaos-test in Week 15** — poison-pill storms, DLQ back-pressure, Lambda concurrency exhaustion bleeding into SQS. Build it carefully now and those weeks are a victory lap. Build it sloppily now and you will rebuild it twice.

The first thing to internalize is that **AWS has at least five services that all "move messages around," and they are not interchangeable**. SQS is a queue (point-to-point, pull, at-least-once). SNS is a fan-out bus (pub/sub, push, no retention). EventBridge is a *routing* bus (content-based rules, schema registry, archive/replay) that is slower and richer than SNS. Kinesis Data Streams is an ordered, replayable, sharded log (Kafka-shaped). MSK *is* Kafka, managed. Each one solves a problem the others solve badly, and the single most valuable thing you will leave this week with is **the decision table you can defend in a design review** when a staff engineer asks "why EventBridge here and not SNS?" The honest answer is never "because the tutorial used it."

The second thing to internalize is that **every distributed message system is at-least-once unless you pay for less, and at-least-once means your consumers must be idempotent or your data will be wrong**. SQS standard delivers duplicates. SNS retries on HTTP 500 and delivers duplicates. EventBridge retries for 24 hours and delivers duplicates. Lambda event-source mappings re-deliver a whole batch if one record in it throws. The poison-pill message — the one record that will *never* succeed no matter how many times you retry it — will block an ordered shard or burn your retry budget and eventually drown a queue, unless you give it somewhere to die: a dead-letter queue, a `maxReceiveCount`, a `bisectBatchOnFunctionError`. Replay and idempotency are not advanced topics you bolt on later. They are the load-bearing wall of every event-driven system, and we treat them that way starting in Lecture 2.

The third thing to internalize is that **ordering, replay, throughput, and cost are a four-way trade-off, and you cannot have all four maxed at once**. SQS FIFO gives you ordering and dedupe but caps at 300–3,000 msg/s per message group and costs more per million. Kinesis gives you ordering *within a shard* and 24-hour-to-365-day replay, but you provision shards and pay per shard-hour whether traffic flows or not. EventBridge gives you the richest routing and archive/replay but adds ~half a second of latency and has no ordering guarantee at all. MSK gives you Kafka's full ordering-and-replay model and the highest throughput ceiling, at the price of running broker infrastructure (or paying MSK Serverless's per-partition premium). The challenge this week makes you *swap the EventBridge spine for MSK* and write up exactly what changed — ordering, replay, throughput, cost — because that is the conversation you will have for real, with a budget attached, inside two years.

## Learning objectives

By the end of this week, you will be able to:

- **Choose** the correct AWS messaging primitive — SQS standard, SQS FIFO, SNS, EventBridge, Kinesis Data Streams, or MSK — for a given ordering, replay, throughput, fan-out, and cost requirement, and defend the choice against a skeptical reviewer using a decision table you can reproduce from memory.
- **Configure** SQS correctly: visibility timeout sized to 6× the consumer's p99, long polling (`ReceiveMessageWaitTimeSeconds = 20`) to kill empty-receive cost, a redrive policy with a tuned `maxReceiveCount`, and a FIFO queue with the right `MessageGroupId` and content-based deduplication.
- **Build** SNS fan-out with subscription filter policies so each subscriber receives only the message attributes it cares about, and explain why filtering at the topic beats filtering in every consumer.
- **Stand up** an EventBridge custom bus with content-based rules, a schema registry with code bindings, an archive with a retention window, and an EventBridge **Pipe** (source → filter → enrichment → target) replacing hand-rolled glue Lambda.
- **Decide** between Step Functions **Standard** (long-running, durable, billed per state transition) and **Express** (sub-second, billed per execution-duration), and implement an Express state machine with `Retry`, `Catch`, and a `Map` over a batch.
- **Operate** Kinesis Data Streams (shards, partition keys, the hot-shard problem, enhanced fan-out) and Kinesis **Firehose** (managed buffered delivery to S3 with Parquet conversion and dynamic partitioning), and know which one you actually want for analytics.
- **Reason** about MSK and MSK Serverless versus self-managed Kafka, and map every Kafka concept (topic, partition, consumer group, offset, ISR) onto its Kinesis equivalent and back.
- **Design for replay and idempotency**: dead-letter queues on every consumer, a `bisectBatchOnFunctionError` Lambda mapping, an idempotency table in DynamoDB with a conditional write, an EventBridge archive replay, and a poison-pill drill that proves a bad message lands in the right DLQ instead of taking the system down.
- **Compare** the AWS primitives honestly against their open-source equivalents — NATS, RabbitMQ, Kafka, and Temporal — so you can advise a team that is *not* all-in on AWS.

## Prerequisites

- **Weeks 1 through 9 of C19 complete.** You have a multi-account org with IAM Identity Center (Weeks 1–2), a working CDK app in both TypeScript and Python with `cdk bootstrap` done in `dev` (Week 3), a production-shape VPC with endpoints (Week 4), Lambda and API Gateway fluency (Weeks 5, 7), an S3 bucket with KMS and lifecycle rules (Week 6), and a DynamoDB single-table you can read and write from a Lambda (Week 9). This week assumes you are no longer fighting the deploy loop.
- **CDK v2 (`aws-cdk-lib` 2.160.0 or later) and the CDK CLI 2.160+** on your PATH. We pin to a 2.16x line; the constructs used here (`aws-cdk-lib/aws-pipes`, L2 EventBridge Pipes, the `aws-stepfunctions-tasks` Express integrations) are stable in that range.
- **The AWS CLI v2** configured with an `aws sso login` profile into your `dev` account. Most of this week's drills are CLI-driven (`aws sqs`, `aws events`, `aws kinesis`, `aws stepfunctions`).
- **Python 3.12** for the Lambda handlers (we use `aws-lambda-powertools` for idempotency and structured logging) and **Node 20** for the CDK TypeScript app. One exercise reimplements a stack in **OpenTofu 1.8+** so you can see the same topology expressed without CDK's magic.
- **A clear head about at-least-once delivery.** If "exactly-once" still sounds like something you can just turn on, re-read the Week 9 notes on conditional writes first. Idempotency this week is built on the same conditional-write primitive.
- An AWS `dev` account you control. Everything this week fits inside or near the free tier if you tear down the Kinesis stream and the MSK Serverless cluster each night. **MSK Serverless is the one line item that will surprise you** — it bills per-hour even idle. The challenge has an explicit teardown step; do not skip it.

## Topics covered

- **SQS standard vs FIFO.** At-least-once vs exactly-once-processing, the 300/3,000 msg/s FIFO ceiling, `MessageGroupId` and per-group ordering, content-based deduplication and the 5-minute dedupe window, visibility timeout sizing, the `ChangeMessageVisibility` heartbeat for long jobs, long polling vs short polling and the empty-receive cost, the redrive policy and `maxReceiveCount`, and redrive-allow-policy to control who can DLQ into a queue.
- **SNS.** Standard vs FIFO topics, fan-out to SQS/Lambda/HTTP/email, **message filtering** with filter policies (attribute-based and the newer payload-based `MessageBody` scope), message attributes, delivery retry policy and the SNS DLQ, and the SNS-to-SQS fan-out pattern that is the single most common AWS messaging shape.
- **EventBridge.** The default bus vs custom buses vs partner event sources, event structure (`source`, `detail-type`, `detail`), **content-based rules** with the event pattern language, **input transformers**, **archive and replay**, the **schema registry** and code bindings, **EventBridge Pipes** (source → filter → enrichment → target as a managed construct), and **Scheduler** as the modern replacement for CloudWatch Events rules-on-a-cron.
- **Step Functions.** Standard vs Express (the durability/latency/cost trade-off), the Amazon States Language (`Task`, `Choice`, `Map`, `Parallel`, `Wait`, `Pass`, `Fail`, `Succeed`), `Retry` with backoff and jitter, `Catch` and error names, **distributed Map** for large fan-out, direct SDK integrations (call DynamoDB without a Lambda), and Express synchronous vs asynchronous invocation.
- **Kinesis Data Streams.** Shards and the 1 MB/s-in / 2 MB/s-out per-shard limit, partition keys and the hot-shard problem, the KCL and checkpointing, **enhanced fan-out** (a dedicated 2 MB/s pipe per consumer), on-demand vs provisioned capacity mode, and the iterator-age metric that tells you you are falling behind.
- **Kinesis Firehose.** Buffered managed delivery to S3/Redshift/OpenSearch/Splunk, buffering hints (size and interval), **record format conversion** to Parquet via a Glue table, **dynamic partitioning** by a JSON field, and why Firehose — not raw Data Streams — is what you want for "land events in S3 for Athena."
- **MSK and MSK Serverless.** Managed Apache Kafka, broker sizing and storage, the difference between provisioned MSK and MSK Serverless (per-partition, per-hour pricing), IAM auth vs SASL/SCRAM vs mTLS, MSK Connect for sink/source connectors, and the Kafka-to-Kinesis concept map (topic↔stream, partition↔shard, consumer group↔KCL app, offset↔sequence number).
- **Replay and idempotency.** At-least-once as the default contract, the idempotency key and the DynamoDB conditional-write pattern (and `aws-lambda-powertools`' `@idempotent` decorator), dead-letter queues on SQS / SNS / EventBridge / Lambda event-source mappings, Lambda `bisectBatchOnFunctionError` and `maxRecordAge` / `maxRetryAttempts`, the poison-pill message and where it should die, and EventBridge archive replay against an idempotent consumer.
- **Open-source comparators.** NATS (and JetStream) as the "lightweight EventBridge+SQS," RabbitMQ as the "SQS+SNS with richer routing," Apache Kafka as the thing MSK manages, and Temporal as the durable-execution engine that competes with Step Functions Standard. When each is the honest answer instead of the AWS-native one.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract. The Kinesis and MSK work bills by the hour even when idle — schedule it in a single block and tear it down the same day.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Reading + the five-primitives decision table (Lecture 1)    |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | SQS/SNS/EventBridge deep dive; build the pipeline spine     |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0h      |     5.5h    |
| Wednesday | Step Functions Express + Kinesis Firehose; replay/idempotency (Lecture 2) |  1.5h |  2h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | DLQs everywhere + poison-pill drill + archive replay        |    0.5h  |    2h     |     1.5h   |    0.5h   |   1h     |     0h       |    0h      |     5.5h    |
| Friday    | MSK swap challenge; start the mini-project                  |    0h    |    0h     |     1.5h   |    0.5h   |   1h     |     3h       |    0.5h    |     6.5h    |
| Saturday  | Mini-project deep work — pipeline + MSK comparison writeup  |    0h    |    0h     |     0h     |    0h     |   1h     |     3h       |    0h      |     4h      |
| Sunday    | Quiz, review, cost report, teardown                         |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                             | **6h**   | **7.5h**  | **4.5h**   | **3.5h**  | **6h**   | **10h**      | **2.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | AWS docs, re:Invent talks, books, and open-source comparators — current to 2026, one line each |
| [lecture-notes/01-five-overlapping-primitives-decision-table.md](./lecture-notes/01-five-overlapping-primitives-decision-table.md) | SQS, SNS, EventBridge, Kinesis, MSK — what each is, what each is *not*, and the decision table you defend in a design review |
| [lecture-notes/02-replay-and-idempotency.md](./lecture-notes/02-replay-and-idempotency.md) | At-least-once, idempotency keys, DLQs on every consumer, EventBridge archive replay, poison-pill handling, and the drill |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-build-the-order-pipeline.md](./exercises/exercise-01-build-the-order-pipeline.md) | Guided build: API GW → Lambda → EventBridge bus → SQS + Step Functions Express + Firehose-to-S3, in CDK TypeScript |
| [exercises/exercise-02-dlqs-and-poison-pill.py](./exercises/exercise-02-dlqs-and-poison-pill.py) | Add DLQs everywhere, fire a poison-pill message, assert it lands in the correct DLQ (runnable, boto3) |
| [exercises/exercise-03-archive-replay-idempotent.py](./exercises/exercise-03-archive-replay-idempotent.py) | Replay an event from the EventBridge archive and prove the consumer reprocesses idempotently (runnable, boto3 + DynamoDB) |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-swap-eventbridge-for-msk.md](./challenges/challenge-01-swap-eventbridge-for-msk.md) | Replace the EventBridge spine with MSK; write up what changed in ordering, replay, throughput, and cost |
| [quiz.md](./quiz.md) | 13 questions with an answer key |
| [homework.md](./homework.md) | Six practice problems with acceptance criteria and a rubric |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the **Event-Driven Order Pipeline** — the capstone's event spine |

## The "it survived the poison pill" promise

C19 has a recurring marker for every week that ends in a working system. Week 1's was the budget alert email. Week 9's was the hot-partition graph flattening after you added write-sharding. Week 10's is this: you fire a deliberately malformed order into the pipeline, and instead of the whole thing falling over, you watch the bad message get retried the configured number of times, then land — quietly, with its full payload intact — in the dead-letter queue named for the consumer that rejected it. Then you replay yesterday's good events from the EventBridge archive and watch the idempotency table reject the duplicates so no customer gets charged twice.

```
[order-validator] processing msg 3f2a... attempt 1/3 → ValidationError: missing customerId
[order-validator] processing msg 3f2a... attempt 2/3 → ValidationError: missing customerId
[order-validator] processing msg 3f2a... attempt 3/3 → ValidationError: missing customerId
[order-validator] msg 3f2a... exceeded maxReceiveCount=3 → moved to order-validator-dlq
[replay] EventBridge replay 'reprocess-2026-06-08' COMPLETED · 1,284 events
[order-validator] idempotency hit for key order#7781 → skipped (already processed)
```

If your pipeline cannot do both of those things — die gracefully on a poison pill, and reprocess a replay without duplicating side effects — you are not done. A pipeline that only works on the happy path is a demo, not a system.

## A note on what's not here

Week 10 introduces the eventing layer. It does **not** introduce:

- **OpenTelemetry / X-Ray tracing across the pipeline.** That is Week 12. We will emit structured logs and a couple of CloudWatch metrics this week, but distributed tracing across EventBridge → SQS → Step Functions is a Week 12 topic and a hard one.
- **Multi-region eventing (EventBridge global endpoints, cross-region replication).** That is Week 13 (DR). This week is single-region.
- **The full data-lake build on top of Firehose-to-S3 (Glue crawlers, Athena partition projection, Iceberg).** Firehose lands Parquet in S3 this week; querying it properly is Week 11.
- **SageMaker / Bedrock consumers off the stream.** Week 11. The Firehose tap this week is the seam those consumers will attach to later.
- **The capstone-grade security pass (KMS-CMK on every queue, resource policies, VPC-only endpoints).** We use KMS where it is free and obvious; the full hardening is Week 13. Do not let that stop you from encrypting the queues now — it is one line of CDK.

The point of Week 10 is one sharp capability: build an event-driven system you can *defend*, with replay and idempotency designed in from the first commit, and a decision table that explains every primitive you chose and every one you rejected.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **AWS Event-Driven Architecture** guidance on the AWS Architecture Center and the **EventBridge** section of the Serverless Land patterns library: <https://serverlessland.com/patterns>. Pick three patterns and explain when each beats the obvious alternative.
- Re-implement the Step Functions Express state machine as a **Standard** state machine and compare the cost at 1, 100, and 10,000 executions/day. Find the crossover point where Standard becomes cheaper.
- Replace the Lambda enrichment in your EventBridge Pipe with a **Step Functions Express** enrichment, and the SQS source with a **Kinesis** source. Note how Pipes abstracts the poller you would otherwise hand-write.
- Stand up **NATS JetStream** locally in Docker and reproduce the SQS-DLQ + replay behaviour. Write a one-page note on what NATS makes easy that EventBridge makes hard, and vice versa.
- Read the **MSK pricing page** and the **Kinesis Data Streams on-demand pricing page** and build a spreadsheet that finds the throughput at which MSK Serverless becomes cheaper than Kinesis on-demand. Bring the number to the architectural review.

## Up next

Continue to **Week 11 — Data Lake & AI: S3 + Athena + Glue, OpenSearch, SageMaker, Bedrock** once you have shipped the order pipeline with DLQs, archive replay, and the MSK comparison. Week 11 attaches a Glue crawler and Athena to the Parquet that your Firehose tap is already landing in S3, then hangs a SageMaker inference endpoint and a Bedrock comparison off the same event stream. The Firehose-to-S3 seam you build this week is the on-ramp to the data lake; the EventBridge bus is the on-ramp to the AI consumers. Build the seam clean now and Week 11 plugs straight in.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
