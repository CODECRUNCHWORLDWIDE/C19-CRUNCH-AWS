# Mini-Project — The Event-Driven Order Pipeline (the Capstone's Event Spine)

> This is the system the rest of the course leans on. The EventBridge custom bus you ship here is the **capstone's event backbone**. It is the pipeline you **instrument with OpenTelemetry in Week 12** and the system you **chaos-test in Week 15** — poison-pill storms, DLQ back-pressure, Lambda concurrency exhaustion bleeding into SQS. Build it carefully now and those weeks are a victory lap. Build it sloppily and you rebuild it twice.

**Time budget:** ~10 hours across the week (see the weekly schedule in the week README). **Output:** a deployed, defended, torn-down-cleanly event-driven order pipeline with DLQs everywhere, poison-pill handling, archive replay, a Firehose-to-S3 analytics tap, *and* the MSK comparison from the challenge folded into the writeup.

---

## 1. What you are building

A production-shape order-processing pipeline. One producer, an EventBridge custom-bus spine, three independent reactors, failure boundaries on every consumer, and an analytics tap landing Parquet in S3:

```
                                ┌── order-validator-rule ──> SQS ──> Lambda (validator) ──┐
                                │      (+ order-validator-dlq, maxReceiveCount=3)         │
                                │                                                          ├─> DynamoDB
 client ─POST─> API GW ─> Lambda ──> EventBridge ── order-orchestrate-rule ──> Step Functions  (idempotency
            /orders   (front-door,   crunch-orders-      (Express: validate→charge→confirm)     + orders)
                       generates       -bus              with Retry/Catch + target DLQ          │
                       orderId)        (+ archive,                                              │
                                        30-day            order-analytics-rule ──> Firehose ──> S3 (Parquet,
                                        retention)            (+ delivery DLQ)        dynamic-partitioned)
```

This is exercise 1's pipeline, *hardened*: every reactor gets a named DLQ, every side-effecting consumer is idempotent on `orderId`, the bus has an archive, and you prove the failure and replay behaviours with the drills from exercises 2 and 3.

---

## 2. Functional requirements

### 2.1 The front door

- `POST /orders` accepts `{ "customerId", "amount", "items": [...] }`.
- The front-door Lambda generates a stable `orderId` (the idempotency key for the whole pipeline), wraps it in an `OrderPlaced` event, and `PutEvents` to `crunch-orders-bus`.
- Returns `202 Accepted` with `{ "orderId", "status": "accepted" }`. The work is asynchronous from here.
- Input validation at the edge: reject a request with no `customerId` with `400` *before* it enters the bus, so the only poison pills in the pipeline are ones you inject deliberately for the drill.

### 2.2 The three reactors

1. **Validator** (SQS → Lambda): validates the order shape, writes the validated order to the DynamoDB orders table. Idempotent on `orderId`. Partial-batch-response on. Behind `order-validator-queue` with `order-validator-dlq`, `maxReceiveCount=3`, visibility timeout = 6× p99, long polling on.
2. **Orchestrator** (EventBridge → Step Functions Express): runs the `validate → charge → confirm` saga. `Retry` with backoff+jitter on transient errors, `Catch` routing terminal failures to a failure state. The charge step is idempotent on `orderId`. The EventBridge target has a DLQ and a retry policy.
3. **Analytics** (EventBridge → Firehose → S3): every `OrderPlaced` lands in S3 as Parquet (or GZIP-JSON if you skip the Glue table), dynamically partitioned by date. The Firehose delivery has an error-output prefix and the rule target a DLQ.

### 2.3 Replay and idempotency

- An EventBridge **archive** on the custom bus, 30-day retention.
- A shared **DynamoDB idempotency table** with TTL longer than the replay window (≥30 days). Either the hand-rolled conditional-write pattern or `aws-lambda-powertools`' `@idempotent` — your choice, but pick one and use it consistently.
- The **poison-pill drill** (exercise 2): a malformed order lands in `order-validator-dlq`, payload intact, while good orders flow.
- The **replay drill** (exercise 3): replay a window from the archive, idempotency rejects every duplicate, zero double-charges.

### 2.4 The MSK comparison

- Fold the challenge writeup into your submission: the four-question analysis (ordering, replay, throughput, cost) with the crossover number. You do not have to keep the MSK cluster running — but you must have stood one up, measured it, and torn it down.

---

## 3. Non-functional requirements

- **Infrastructure as code, no console clicking.** The whole stack deploys with `cdk deploy` (TypeScript) or `tofu apply` (one component must be OpenTofu — see §5). Console clicks are for *inspecting*, never for *creating*.
- **DLQ on every consumer, named for that consumer.** No shared catch-all DLQ. `order-validator-dlq`, not `pipeline-dlq`.
- **Encryption where it's free.** SQS and SNS get SSE; the S3 bucket gets `S3_MANAGED` encryption. (Full KMS-CMK hardening is Week 13 — do not gold-plate it here, but do not ship plaintext queues either.)
- **A cost report.** Estimate the monthly cost of this pipeline at 200k orders/day. EventBridge events, SQS requests, Step Functions Express GB-seconds, Firehose GB, S3 storage, DynamoDB on-demand. One table, one total. This is the C19 weekly ritual.
- **Clean teardown.** `cdk destroy` removes everything; you verify no orphaned resources (no MSK cluster billing overnight, no stranded Kinesis shards).

---

## 4. Repository layout

```
order-pipeline/
├── bin/
│   └── order-pipeline.ts            # CDK app entry
├── lib/
│   ├── order-pipeline-stack.ts      # bus, queues+DLQs, rules, SFN, Firehose
│   └── idempotency.ts               # shared idempotency-table construct
├── lambda/
│   ├── front-door/index.py          # POST /orders -> PutEvents
│   ├── validator/index.py           # SQS consumer, idempotent, partial-batch
│   └── charge/index.py              # SFN Express task, idempotent
├── tofu/
│   └── analytics_firehose.tf        # the Firehose+bucket, in OpenTofu (§5)
├── drills/
│   ├── poison_pill.py               # exercise 2, adapted
│   └── archive_replay.py            # exercise 3, adapted
├── docs/
│   ├── decision-table.md            # the five-primitives table, your version
│   ├── msk-comparison.md            # the challenge writeup
│   └── cost-report.md               # the monthly cost table
└── README.md                        # how to deploy, drill, and tear down
```

---

## 5. The OpenTofu requirement

Reimplement **one component** — the Firehose delivery stream and its S3 bucket — in **OpenTofu** instead of CDK, so you see the same topology without CDK's synthesis magic. This is the "same primitive, two IaC tools" muscle the course builds. A minimal `tofu/analytics_firehose.tf`:

```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

provider "aws" {
  region = "eu-west-1"
}

resource "aws_s3_bucket" "analytics" {
  bucket        = "crunch-orders-analytics-tofu-${data.aws_caller_identity.me.account_id}"
  force_destroy = true # dev only
}

data "aws_caller_identity" "me" {}

resource "aws_iam_role" "firehose" {
  name = "order-analytics-firehose-tofu"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "firehose.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "firehose_s3" {
  role = aws_iam_role.firehose.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetBucketLocation", "s3:ListBucket"]
      Resource = [aws_s3_bucket.analytics.arn, "${aws_s3_bucket.analytics.arn}/*"]
    }]
  })
}

resource "aws_kinesis_firehose_delivery_stream" "orders" {
  name        = "order-analytics-tofu"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn            = aws_iam_role.firehose.arn
    bucket_arn          = aws_s3_bucket.analytics.arn
    prefix              = "orders/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/"
    error_output_prefix = "errors/"
    compression_format  = "GZIP"

    buffering_size     = 64
    buffering_interval = 60
  }
}

output "firehose_name" {
  value = aws_kinesis_firehose_delivery_stream.orders.name
}
```

Deploy it with `tofu init && tofu apply`, point an EventBridge rule target at the resulting Firehose, and note in your writeup: which IaC tool you'd reach for in this team, and why.

---

## 6. Milestones

| Milestone | Done when |
|---|---|
| **M1 — Spine up** | `cdk deploy` succeeds; `POST /orders` returns 202; all three reactors react to one good order (logs + S3 object + SFN execution). |
| **M2 — Failure boundaries** | Every consumer has a named DLQ; the poison-pill drill passes (bad order in `order-validator-dlq`, payload intact, good orders unaffected). |
| **M3 — Idempotency + replay** | Idempotency table with TTL; archive on the bus; replay drill passes (zero double-charges across a replayed window). |
| **M4 — OpenTofu component** | The Firehose+bucket deploys via `tofu apply` and an EventBridge rule routes to it. |
| **M5 — MSK comparison** | The four-question writeup with a crossover number; MSK cluster stood up, measured, torn down. |
| **M6 — Cost + teardown** | Cost report table for 200k orders/day; `cdk destroy` + `tofu destroy` leave zero billing resources. |

---

## 7. Acceptance criteria (the rubric)

You pass when **all** of these are true:

- [ ] One `PutEvents` fans out to three independent reactors via EventBridge rules.
- [ ] Every consumer has a **named** DLQ; `maxReceiveCount` tuned; visibility = 6× p99; long polling on.
- [ ] The validator Lambda returns **partial batch failures**.
- [ ] Every side-effecting consumer is **idempotent on `orderId`** (not a delivery ID).
- [ ] The idempotency table TTL ≥ the archive retention window.
- [ ] The **poison-pill drill passes**: bad message in the right DLQ, payload intact, good orders unblocked.
- [ ] The **replay drill passes**: zero double-charges across a replayed window.
- [ ] The Firehose tap lands date-partitioned objects in S3; the delivery has an error-output prefix.
- [ ] One component is implemented in **OpenTofu** and wired into the pipeline.
- [ ] The **MSK comparison** answers all four questions with numbers, including the crossover rate.
- [ ] A **cost report** for 200k orders/day with a line per service and a total.
- [ ] `cdk destroy` + `tofu destroy` leave **zero** billing resources (verified, not assumed).

---

## 8. The "it survived the poison pill" promise — your version

C19's marker for a working system this week is two demonstrations, captured in your README as terminal output:

```
[order-validator] processing msg 3f2a... attempt 1/3 -> ValidationError: missing customerId
[order-validator] processing msg 3f2a... attempt 2/3 -> ValidationError: missing customerId
[order-validator] processing msg 3f2a... attempt 3/3 -> ValidationError: missing customerId
[order-validator] msg 3f2a... exceeded maxReceiveCount=3 -> moved to order-validator-dlq
[replay] EventBridge replay 'reprocess-2026-06-08' COMPLETED · 1,284 events
[order-validator] idempotency hit for key order#7781 -> skipped (already processed)
```

Paste both into your submission README. If your pipeline cannot die gracefully on a poison pill *and* reprocess a replay without duplicating side effects, it is a demo, not a system — and the capstone needs a system.

---

## 9. How this compounds

- **Week 11** hangs a Glue crawler and Athena off the Parquet your Firehose tap is landing, and attaches SageMaker/Bedrock consumers to the EventBridge bus. Keep the bus and the S3 layout clean.
- **Week 12** instruments this exact pipeline with OpenTelemetry — traces across EventBridge → SQS → Step Functions, metrics to CloudWatch, a burn-rate SLO alarm. The cleaner your consumer boundaries now, the cleaner the spans later.
- **Week 13** is the capstone build; this bus is its event backbone.
- **Week 15** chaos-tests it: poison-pill storms, DLQ back-pressure, Lambda concurrency exhaustion. The failure boundaries you build this week are exactly what gets stressed.

Build it like you'll have to live with it for five more weeks. Because you will.

---

## 10. Submission

A PR (or a tarball) containing the repo layout in §4, with:

- The deployed-and-torn-down pipeline (CDK + the OpenTofu component).
- Both drill outputs pasted into the README.
- `docs/decision-table.md`, `docs/msk-comparison.md`, `docs/cost-report.md`.
- A two-paragraph reflection: what you'd change before this carries the capstone, and the one trade-off you're least sure about.
