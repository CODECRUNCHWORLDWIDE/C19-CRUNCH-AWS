# Lecture 1 — SQS, SNS, EventBridge, Kinesis, MSK: Five Overlapping Primitives and the Decision Table You'll Defend in a Design Review

> "Why EventBridge here and not SNS?" is the question a staff engineer asks in the design review. The wrong answer is "because the tutorial used it." The right answer is a sentence about ordering, replay, fan-out, latency, and cost. This lecture builds the table that turns the wrong answer into the right one.

---

## 0. The shape of the problem

AWS sells you at least five services whose one-line description is "moves messages around":

- **SQS** — Simple Queue Service. A queue.
- **SNS** — Simple Notification Service. A pub/sub topic.
- **EventBridge** — a content-routing event bus with archive and replay.
- **Kinesis Data Streams** — an ordered, sharded, replayable log.
- **MSK** — Managed Streaming for Apache Kafka. Kafka, run by AWS.

Plus **Step Functions** (orchestration, not transport, but it lives in this family because it consumes and emits events) and **Firehose** (managed delivery, a sink not a bus). Seven things in the catalog that all show up on the same whiteboard.

They are not interchangeable. Each one is excellent at the thing it was built for and mediocre-to-dangerous at the things the others were built for. The senior skill is not memorizing the feature lists — the docs do that. The senior skill is holding **five axes** in your head and snapping any new requirement onto them fast enough to answer the design-review question in one breath.

The five axes:

1. **Delivery model** — point-to-point (one consumer takes the message) vs fan-out (every subscriber gets a copy).
2. **Ordering** — none, per-group, or per-partition/shard.
3. **Replay / retention** — can a consumer re-read history, and for how long?
4. **Throughput ceiling** — what is the per-unit limit and how do you scale past it?
5. **Cost shape** — per-message, per-shard-hour, per-partition-hour, or per-execution; and crucially, *do you pay when idle?*

Hold those five. Everything else is detail you can look up. Let us walk each service against the five axes, then assemble the table.

---

## 1. SQS — the queue

SQS is a **point-to-point queue**. A producer sends a message; *one* consumer receives it, processes it, and deletes it. If you want two consumers to each get the message, SQS is the wrong tool — that is fan-out, and that is SNS or EventBridge.

### Standard vs FIFO

There are two flavours, and the difference is the whole story:

- **Standard** — effectively unlimited throughput, **at-least-once** delivery (you *will* see duplicates), **best-effort ordering** (you *will* see reordering). This is the default and the right default for ~90% of work queues.
- **FIFO** — strict ordering *within a message group*, **exactly-once processing** within the 5-minute dedup window, and a throughput ceiling: **300 messages/second** per API call without batching, **3,000 messages/second** with batching of 10, *per message group*. You pay more per million requests.

The trap: people reach for FIFO because "I need ordering" without asking *ordering of what?* You almost never need a global total order. You need orders for *one customer* processed in sequence, while a different customer's orders process in parallel. That is exactly what `MessageGroupId` gives you — order within the group, parallelism across groups. Set `MessageGroupId = customerId` and you get per-customer ordering at high aggregate throughput.

### Visibility timeout — the bug everyone ships once

When a consumer receives a message, SQS does not delete it. It makes it **invisible** for the *visibility timeout* and waits for the consumer to call `DeleteMessage`. If the consumer crashes or is slow, the timeout expires and the message becomes visible again for another consumer to retry.

The bug: you set the visibility timeout to 30 seconds (the default), your consumer's p99 processing time is 45 seconds, and now SQS hands the *same message* to a second consumer while the first is still working on it. You process it twice and your idempotency had better be real, or you ship the order twice.

The rule we use: **visibility timeout = 6× the consumer's p99 processing time.** If p99 is 5 seconds, set it to 30. If a job legitimately runs long and unpredictably, have the consumer call `ChangeMessageVisibility` periodically — a *heartbeat* — to extend the lease while it works.

### Long polling — stop paying for empty receives

`ReceiveMessage` with the default short polling returns immediately, often with zero messages, and you pay for the request. At a poll loop running every 100 ms against an idle queue, that is 36,000 billed empty receives an hour, for nothing.

`ReceiveMessageWaitTimeSeconds = 20` turns on **long polling**: the call blocks up to 20 seconds waiting for a message, returning the instant one arrives. Empty-receive cost drops by orders of magnitude and latency *improves* because you get the message the moment it lands. There is no reason to run short polling in production. Set it to 20.

### Dead-letter queues and the redrive policy

A **redrive policy** on the queue says: after a message has been received `maxReceiveCount` times without being deleted, move it to *this other queue* — the **dead-letter queue (DLQ)**. The DLQ is where poison pills go to be inspected instead of looping forever.

```json
{
  "deadLetterTargetArn": "arn:aws:sqs:eu-west-1:111122223333:order-validator-dlq",
  "maxReceiveCount": 3
}
```

Tune `maxReceiveCount` to the number of retries that could *plausibly* succeed. A transient downstream blip might clear in one retry; a malformed payload will never clear. Three is a sane default for transient-failure tolerance. The companion **redrive-allow-policy** on the DLQ controls *which* source queues are allowed to use it as a DLQ — a guard against a noisy neighbour dumping into your inspection queue.

---

## 2. SNS — the fan-out topic

SNS is **pub/sub fan-out**. A producer publishes to a *topic*; every *subscription* on that topic gets a copy. Subscriptions can be SQS queues, Lambda functions, HTTP/HTTPS endpoints, email, SMS, or mobile push. There is **no retention** — SNS pushes, and if a subscriber is down (subject to its retry policy and optional DLQ), the message can be lost. SNS is a delivery mechanism, not a store.

### The canonical pattern: SNS → SQS fan-out

The single most common AWS messaging shape is **SNS fanned out to several SQS queues**:

```
                    ┌──> SQS: billing-queue   ──> billing consumer
producer ──> SNS ───┼──> SQS: shipping-queue  ──> shipping consumer
                    └──> SQS: analytics-queue ──> analytics consumer
```

Why insert SQS between SNS and each consumer instead of subscribing Lambda directly to SNS? Because SQS gives each consumer its own **buffer and retry domain**. If the shipping consumer falls over, its queue fills up and drains later — billing and analytics are unaffected. Subscribe Lambda directly to SNS and a slow consumer means SNS retries (with its own, less controllable policy) and you have no buffer to absorb a burst. The queue is the shock absorber.

### Message filtering — filter at the topic, not the consumer

A **filter policy** on a subscription means that subscriber only receives messages matching the filter. The naive design sends every message to every consumer and each consumer drops the ones it does not care about — wasting invocations, delivery cost, and consumer CPU. The senior design filters at the subscription so the message is never delivered in the first place:

```json
{
  "eventType": ["order.placed", "order.cancelled"],
  "region": [{ "anything-but": ["eu-west-1"] }],
  "amount": [{ "numeric": [">=", 1000] }]
}
```

Filtering can match on **message attributes** (the default scope) or, since the payload-scope feature, on the **message body** itself (`FilterPolicyScope = MessageBody`). Filter at the topic. Every message you don't deliver is money you don't spend and a consumer invocation you don't have to make idempotent.

### SNS vs EventBridge — the question that actually decides it

People agonize over SNS vs EventBridge because they overlap on "fan-out with filtering." The deciding questions are three: **Do you need replay?** (SNS: no; EventBridge: yes, via archive.) **Do you need a schema registry / typed contracts?** (SNS: no; EventBridge: yes.) **Is sub-50 ms latency a hard requirement?** (SNS: yes, it's a thin notifier; EventBridge: no, budget ~500 ms.) If you need replay or a schema registry, it's EventBridge and the latency tax is the price. If you need raw low-latency fan-out and nothing else — mobile push, a high-volume notification firehose, A/B event mirroring — SNS is the right, cheaper, faster tool. SNS is also the only one of the two with FIFO topics, so if you need *ordered* fan-out with dedupe, SNS FIFO → SQS FIFO is the shape; EventBridge has no ordering at all. Decide on replay/schema/latency, not on which one you used last time.

---

## 3. EventBridge — the routing bus

EventBridge is what you get if SNS grew up: a **content-routing event bus** with a rich pattern language, a **schema registry**, **archive and replay**, **input transformers**, **Pipes**, and a built-in **Scheduler**. It is the right backbone for *application events* — "an order was placed", "a user signed up" — that many independent services want to react to in different ways.

### Event structure and the default vs custom bus

Every EventBridge event has a fixed envelope:

```json
{
  "version": "0",
  "id": "7bf73129-1428-4cd3-a780-95db273d1602",
  "detail-type": "OrderPlaced",
  "source": "com.crunch.orders",
  "account": "111122223333",
  "time": "2026-06-09T14:00:00Z",
  "region": "eu-west-1",
  "detail": {
    "orderId": "order#7781",
    "customerId": "cust#42",
    "amount": 1299
  }
}
```

The **default bus** receives AWS service events (an EC2 instance changed state, an S3 object landed). For *your* application events, create a **custom bus** — `crunch-orders-bus` — so your events are isolated from the firehose of AWS service noise and you can attach an archive scoped to exactly your traffic. The capstone's event spine is a custom bus; build it that way from day one.

### Rules and the pattern language

A **rule** matches events against an **event pattern** and routes matches to up to five targets. The pattern language matches on any field with operators including `prefix`, `suffix`, `anything-but`, `numeric`, `exists`, `cidr`, and `$or`:

```json
{
  "source": ["com.crunch.orders"],
  "detail-type": ["OrderPlaced"],
  "detail": {
    "amount": [{ "numeric": [">=", 1000] }]
  }
}
```

This is the same content-based routing SNS filter policies give you, but at the *bus* level and with a richer operator set — and EventBridge can route the *same* event to a Step Functions execution, an SQS queue, a Lambda, *and* a Firehose stream from one rule with five targets.

### Archive and replay — the feature this week is built on

An **archive** captures every event that matches a pattern and retains it for a window you choose (days, or indefinite). A **replay** re-emits archived events onto the bus, *re-evaluating all current rules*, over a time range you pick. This is the AWS-native answer to "we deployed a bug, dropped 1,284 orders on the floor for two hours, and need to reprocess them" — you replay the archive for that window and your (idempotent!) consumers reprocess. Lecture 2 makes this drill concrete. The catch and the reason idempotency is non-negotiable: a replay re-delivers events your consumers may have *already* processed, because the boundary between "dropped" and "processed" is rarely clean.

### Pipes — the managed source-to-target glue

**EventBridge Pipes** is `source → filter → enrichment → target` as a managed construct. Before Pipes you hand-wrote a Lambda that polled SQS, filtered, called an enrichment API, and forwarded to a target — and you owned the poller, the batching, the error handling, the DLQ. A Pipe is that poller, declared not coded:

```
Pipe: SQS (source) → [filter: detail-type=OrderPlaced]
                    → [enrich: Lambda that fetches customer tier]
                    → Step Functions Express (target)
```

Use Pipes when the glue is "poll a streaming/queue source, optionally filter and enrich, hand to one target." Use a rule when the routing is "this event matched a pattern, fan it to several targets." They are complementary, not competing.

### Input transformers — reshape the event before it hits the target

A frequently-missed EventBridge feature: a rule target can apply an **input transformer** that reshapes the event before delivery. Without it, every target receives the full EventBridge envelope and has to dig `$.detail.orderId` out of a nested structure. With an input transformer you declare a path map and a template, and the target receives exactly the shape it wants:

```json
{
  "InputPathsMap": { "id": "$.detail.orderId", "amt": "$.detail.amount" },
  "InputTemplate": "{ \"order\": \"<id>\", \"total\": <amt> }"
}
```

Now a Step Functions target receives `{ "order": "order#7781", "total": 1299 }` instead of the whole envelope. This matters for two reasons: it keeps consumers decoupled from EventBridge's envelope shape (so the event format can evolve without touching every consumer), and for Step Functions it lets you feed the state machine exactly the input its first state expects, with no unwrapping `Pass` state. Reshape at the rule, not in the consumer.

### The latency tax

EventBridge is *slower* than SNS — budget roughly **half a second** of routing latency, sometimes more under load. It is a routing engine doing pattern evaluation, not a thin notification pipe. For application events where half a second is invisible, this is a non-issue. For a sub-millisecond hot path, EventBridge is the wrong tool — that is a direct call or a Kinesis put.

---

## 4. Step Functions — orchestration, Standard vs Express

Step Functions is not transport — it is **orchestration**. It runs a state machine written in the **Amazon States Language (ASL)**, a JSON DSL with states `Task`, `Choice`, `Map`, `Parallel`, `Wait`, `Pass`, `Fail`, `Succeed`. It manages retries, catches, branching, and parallelism so your Lambdas stay dumb single-step functions and the *workflow* lives in declarative JSON you can read in a code review.

The decision inside Step Functions is **Standard vs Express**:

| | **Standard** | **Express** |
|---|---|---|
| Duration | up to **1 year** | up to **5 minutes** |
| Execution model | durable, exactly-once *state transitions* | at-least-once, in-memory |
| Billing | **per state transition** | **per execution × duration × memory** (GB-second) |
| History | full, queryable, 90-day retention | logged to CloudWatch only (if enabled) |
| Throughput | thousands/s | **100,000+/s** |
| Use it for | human-in-the-loop, long sagas, anything that waits hours/days | high-volume short orchestration: per-request, per-event processing |

The cost intuition: Standard bills **per state transition**, so a workflow with 12 states costs 12 transitions per run — cheap at low volume, expensive at millions of runs/day. Express bills per **execution-duration**, so a 200 ms workflow is nearly free per run and stays cheap at scale. Crossover is real: at low volume Standard is cheaper; at high volume Express wins by a wide margin. The order-pipeline orchestration this week is **Express** because it is per-order, short, and high-volume. A monthly billing-reconciliation saga that waits for human approval is **Standard**.

`Retry` (with `IntervalSeconds`, `BackoffRate`, `MaxAttempts`, and `JitterStrategy`) and `Catch` (matched on error names like `States.TaskFailed` or your own) are how you make a workflow resilient without writing retry loops in every Lambda. **Distributed Map** fans out over up to millions of items from S3 or DynamoDB with bounded concurrency — the tool for "process every line of a 10 GB S3 manifest."

---

## 5. Kinesis Data Streams — the ordered log

Kinesis Data Streams is an **ordered, replayable, sharded log** — Kafka-shaped. Producers `PutRecord` with a **partition key**; records with the same key land on the same **shard** and are **ordered within that shard**. Consumers read the shard in order, tracking their position by **sequence number**. Data is retained **24 hours by default, up to 365 days**, so consumers can replay history.

### Shards and the limits that bite

Each shard ingests **1 MB/s or 1,000 records/s** and emits **2 MB/s** (shared across all standard consumers of that shard). You scale by adding shards. Two failure modes:

- **Hot shard** — a partition key that is too popular (everything keyed by `country = "US"`) sends all its traffic to one shard, which throttles while the others idle. Fix: a higher-cardinality partition key.
- **Falling behind** — the **`IteratorAgeMilliseconds`** metric is the single most important Kinesis metric. It is how far behind real time your consumer is reading. Rising iterator age means your consumers cannot keep up; you are accumulating lag that will eventually hit the retention edge and *lose data*. Alarm on it.

**Enhanced fan-out** gives each registered consumer its *own* dedicated 2 MB/s pipe per shard (pushed via HTTP/2) instead of sharing the 2 MB/s read budget — the fix when several consumers read the same hot stream and starve each other. **On-demand** capacity mode auto-scales shards and bills per GB; **provisioned** bills per shard-hour and is cheaper at steady, predictable load.

### On-demand vs provisioned, and the iterator-age alarm

Kinesis has two capacity modes and the choice matters for both cost and operations. **Provisioned** mode means you declare a shard count and pay per shard-hour regardless of traffic — cheapest at steady, predictable load, but you must reshard manually (split a hot shard, merge cold ones) and you pay for idle shards. **On-demand** mode auto-scales shards to observed throughput and bills per GB ingested plus a per-stream-hour fee — more expensive per GB at sustained high load, but it absorbs spikes without a paging incident and you never reshard by hand. The rule we use: start on-demand (it removes a whole class of capacity-planning mistakes), and switch to provisioned only when the bill says the steady-state shard count is predictable enough to commit to.

Whichever mode you run, the one alarm you must not skip is on **`IteratorAgeMilliseconds`**. It measures how far behind real time your consumers are reading. Flat near zero means consumers keep up; a steady climb means they cannot, and the climb has a deadline — when the iterator age reaches the retention window (24 hours by default), you start *losing data* off the back of the stream because records expire before anyone reads them. Alarm on iterator age trending up well before it nears retention, and treat a rising trend as a capacity or consumer-health incident, not a curiosity.

### Kinesis vs SQS — the line people blur

SQS: *work queue*, message is *deleted* after processing, no replay, no ordering (standard). Kinesis: *log*, records are *retained and re-readable*, ordered within a shard, multiple independent consumers read the same data at their own pace. If you need several consumers to each independently process the *same* ordered stream and replay it — that's Kinesis. If you need one consumer to process each message exactly once and throw it away — that's SQS.

---

## 6. Kinesis Firehose — the managed sink (now "Amazon Data Firehose")

Firehose is not a bus — it is a **managed delivery pipe** that buffers records and lands them in **S3, Redshift, OpenSearch, or Splunk**. You give it records; it batches them by a **buffering hint** (size *and* interval, whichever fires first — e.g. 128 MB or 300 s), optionally **converts the format to Parquet/ORC** using a Glue table, optionally **dynamically partitions** by a JSON field (`s3://bucket/year=2026/month=06/day=09/`), and writes the objects. No shards to manage, no consumer to run.

For "land my events in S3 so Athena can query them tomorrow," Firehose — not raw Data Streams — is what you want. Raw Data Streams hands you records and makes *you* write the batching, format conversion, and S3 writer. Firehose is that writer, managed. This week's analytics tap is a Firehose stream landing Parquet in S3; Week 11 hangs Glue and Athena off it.

---

## 7. MSK — Kafka, managed

MSK is **Apache Kafka run by AWS**. If your organisation already speaks Kafka — has Kafka producers, Kafka Streams apps, Kafka Connect connectors, engineers who know `consumer.poll()` — MSK lets you keep all of it and stop running brokers. Two flavours:

- **MSK provisioned** — you choose broker instance types, count, and storage. You think about partitions, replication factor, retention, and ISR (in-sync replicas). Cheapest at sustained high throughput; you pay for brokers whether or not traffic flows.
- **MSK Serverless** — no brokers to size; billed **per-partition-hour and per-GB**. Easier, and it bills **even when idle** — the line item that surprises people. Tear it down each night during this week.

Auth is **IAM** (our choice — no SCRAM secret to rotate, policies are IAM you already know), **SASL/SCRAM** (username/password in Secrets Manager), or **mTLS**. **MSK Connect** runs Kafka Connect connectors (S3 sink, Debezium source) as a managed service.

### The Kafka ↔ Kinesis concept map

You must be able to translate between them in a design review:

| Kafka / MSK | Kinesis Data Streams |
|---|---|
| topic | stream |
| partition | shard |
| consumer group | KCL application (with a lease table) |
| offset | sequence number |
| producer key → partition | partition key → shard |
| retention (configurable, can be infinite with tiered storage) | retention (24 h–365 days) |
| ISR / replication factor | managed, invisible (AZ-replicated) |
| broker | (no equivalent — AWS runs it) |

Kafka's ceiling is higher and its ecosystem is enormous; Kinesis is simpler, more "AWS-native," and has nothing to run. The challenge this week makes you swap the EventBridge spine for MSK and write up exactly what changes — because that is the real conversation, with a budget attached.

---

### Schema registry — the contract you forgot to write down

One EventBridge feature worth a paragraph because teams skip it and regret it: the **schema registry**. Every event on a bus has an implicit contract — "an `OrderPlaced` has an `orderId`, a `customerId`, and an `amount`." When that contract lives only in the producer's head, the day someone renames `amount` to `total` is the day three downstream consumers break silently. The schema registry makes the contract explicit: EventBridge can **discover** schemas automatically from the events flowing across a bus, you can version them, and you can generate **code bindings** (typed classes in Python/TypeScript/Java/Go) so consumers deserialize against a real type instead of `event["detail"]["amont"]` — a typo that fails at runtime, not compile time. On the capstone's bus, turn on schema discovery early; the registry becomes living documentation of every event your system emits, and the code bindings turn a class of 3 a.m. bugs into compile errors.

## 8. The open-source comparators

When a team is *not* all-in on AWS, the honest answer is sometimes not an AWS service:

- **NATS / JetStream** — one small binary that does pub/sub, queues, and a persistent replayable stream (JetStream). The lightweight "EventBridge + SQS in a box." Brilliant for edge, on-prem, and latency-sensitive internal messaging. No managed AWS equivalent that is as small and fast.
- **RabbitMQ** — exchanges, queues, bindings, dead-letter exchanges, and rich routing (topic/headers/fanout exchanges). The "SQS + SNS with much richer routing." AWS even sells it managed as **Amazon MQ**. Mature, battle-tested, AMQP-standard.
- **Apache Kafka** — the thing MSK manages. Run it yourself (or via Confluent/Redpanda) and you trade operational burden for control and cost ceiling.
- **Temporal** — durable execution: workflows as *code* (Go/Java/TypeScript/Python) with automatic state persistence, retries, and replay. The open-source competitor to Step Functions **Standard**. When your orchestration logic is genuinely complex and you want it in a real programming language with tests rather than ASL JSON, Temporal is the honest answer.

---

## 9. The decision table — the thing you defend

Memorize this. It is the table you reproduce on the whiteboard when the staff engineer asks "why this and not that?"

| Need | SQS std | SQS FIFO | SNS | EventBridge | Kinesis DS | MSK |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Point-to-point work queue | ✅ | ✅ | ❌ | ❌ | ⚠️ | ⚠️ |
| Fan-out to many consumers | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Strict ordering | ❌ | per-group | ❌ | ❌ | per-shard | per-partition |
| Replay / re-read history | ❌ | ❌ | ❌ | ✅ (archive) | ✅ (≤365 d) | ✅ (configurable) |
| Content-based routing | ❌ | ❌ | filter policy | ✅ rich | ❌ | ❌ |
| Schema registry | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ (Glue/MSK) |
| Highest throughput ceiling | high | 300–3k/grp | high | medium | high | **highest** |
| Lowest latency | ~ms | ~ms | ~ms | **~500 ms** | ~ms | ~ms |
| Pay-per-use (free when idle) | ✅ | ✅ | ✅ | ✅ | ⚠️ (provisioned bills idle) | ❌ (MSK bills idle) |
| Operational burden | none | none | none | none | low | medium–high |

Reading the table as decision rules:

- **Work queue, retry, one consumer, duplicates OK** → SQS standard.
- **Work queue, must be in order per entity, duplicates fatal** → SQS FIFO with `MessageGroupId`.
- **Notify N independent consumers, no replay needed, low latency** → SNS (fan-out to SQS so each consumer gets a buffer).
- **Application events, many reactors, content routing, need replay** → EventBridge custom bus + archive. *This is the order pipeline's spine.*
- **Ordered stream, multiple independent replaying consumers, analytics** → Kinesis Data Streams (+ Firehose for the S3 sink).
- **Already speak Kafka / need Kafka ecosystem / highest throughput** → MSK.
- **Orchestrate steps with retries/branching, short & high volume** → Step Functions Express. **Long-running / human-in-the-loop** → Standard.

---

## 9a. EventBridge Scheduler — the thing that retired cron-on-a-rule

A small but load-bearing addition you should know: **EventBridge Scheduler** is the modern, separate service for "run this target on a schedule." It replaced the old pattern of a CloudWatch Events / EventBridge *rule* with a `schedule` expression. Scheduler is its own service with its own quotas (over a million schedules per account, one-time *or* recurring, time-zone-aware with daylight-saving handling, with an optional flexible time window to spread load). It targets any of 270+ AWS API actions directly — so a nightly "kick off the reconciliation Step Functions Standard machine at 02:00 Europe/London" is one schedule, no rule, no Lambda glue.

```bash
aws scheduler create-schedule \
  --name nightly-reconcile \
  --schedule-expression "cron(0 2 * * ? *)" \
  --schedule-expression-timezone "Europe/London" \
  --flexible-time-window '{"Mode":"FLEXIBLE","MaximumWindowInMinutes":15}' \
  --target '{"Arn":"arn:aws:states:eu-west-1:111122223333:stateMachine:reconcile","RoleArn":"arn:aws:iam::111122223333:role/scheduler-invoke"}'
```

Why it matters for the decision table: when someone says "we'll just put it on an EventBridge rule with a cron expression," the 2026 answer is "use Scheduler — it is purpose-built, time-zone-aware, and does not consume rule quota." Rules are for *event matching*; Scheduler is for *time*.

## 9b. A worked sizing-and-cost example

Numbers make the table real. Take the order pipeline at **200,000 orders/day** (the mini-project's assumed scale). Each order produces one `OrderPlaced` event that fans to three targets. Rough monthly arithmetic (confirm current prices on the pricing pages — these are 2026 ballparks):

- **EventBridge custom events**: 200k/day × 30 = 6M events/month. At ~$1.00 / million custom events published → **~$6/month**. Archive storage and the occasional replay are pennies on top.
- **SQS**: 6M sends + 6M receives + 6M deletes ≈ 18M requests. First 1M free, then ~$0.40/million → **~$7/month**.
- **Step Functions Express**: 6M executions × ~250 ms × 256 MB. Express bills ~$1.00/million requests plus GB-seconds. 6M requests → ~$6, plus 6M × 0.25 s × 0.25 GB = 375k GB-s × ~$0.00001667 → ~$6. **~$12/month**.
- **Firehose**: 6M small records, say ~1 KB each = ~6 GB/month ingested. At ~$0.029/GB → **<$1/month** (Parquet conversion adds a little).
- **S3 + DynamoDB on-demand**: a few GB of Parquet and 6M on-demand writes → **~$8/month** combined.

Total: **~$35/month** at 200k orders/day, *free when idle*. Now contrast the same workload on **MSK Serverless**, which bills per partition-hour even at 3 a.m. on a Sunday with zero traffic — and you see why the challenge's crossover analysis matters. EventBridge's per-event tax is cheap until you are doing tens of millions of events a day; MSK's partition-hour floor is paid whether you send one event or a billion.

This is the kind of back-of-envelope you do *in the design review*, on the whiteboard, before anyone commits a line of CDK. "It's about thirty-five dollars a month and free when idle" ends a lot of arguments.

## 10. What you should be able to say out loud

After this lecture, when someone asks "why EventBridge for the order spine and not SNS?", the answer is a sentence:

> "We need content-based routing to four different reactors, we need to replay a window of events after a bad deploy, and we want a schema registry so contracts are explicit. SNS gives us fan-out and attribute filtering but no replay and no schema registry, and half a second of EventBridge latency is invisible for an order event. So EventBridge, with an archive scoped to the custom bus, and SQS queues behind the rule targets so each reactor has its own buffer and DLQ."

That is the deliverable of this week's first half: not a stack, a *defense*. Lecture 2 makes the other half real — at-least-once is the contract, so build for replay and idempotency from the first commit, or your replay will double-charge a customer the day you need it most.
