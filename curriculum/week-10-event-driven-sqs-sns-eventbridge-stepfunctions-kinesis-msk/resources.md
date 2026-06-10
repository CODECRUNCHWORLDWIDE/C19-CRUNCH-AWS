# Week 10 — Resources

Every link on this page is **free** to read. AWS documentation, the AWS Architecture Center, Serverless Land, the re:Invent session recordings on YouTube, the `aws-samples` and `aws-powertools` GitHub repos (all Apache-2.0 / MIT), the NATS / RabbitMQ / Apache Kafka / Temporal docs, and the OpenTofu registry are all open. No paywalled books are required; the two books listed under "If you want the long form" are worth buying but are not gated reading for the week.

Everything here is current to **2026**. Where a doc page moves, the search term in **bold** will find the current URL.

## Required reading (work it into your week)

### SQS

- **Amazon SQS Developer Guide — landing page** (search: **"Amazon SQS Developer Guide"**):
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html>
- **SQS — standard vs FIFO queues**:
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-queue-types.html>
- **SQS — visibility timeout** (read this twice; sizing it wrong is the #1 SQS bug):
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html>
- **SQS — short and long polling** (`ReceiveMessageWaitTimeSeconds`):
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html>
- **SQS — dead-letter queues and the redrive policy**:
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html>
- **SQS — FIFO delivery logic, `MessageGroupId`, and content-based dedup**:
  <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html>

### SNS

- **Amazon SNS Developer Guide — landing page**:
  <https://docs.aws.amazon.com/sns/latest/dg/welcome.html>
- **SNS — message filtering with filter policies** (attribute-based and payload-based `MessageBody` scope):
  <https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html>
- **SNS — fan-out to SQS** (the single most common AWS messaging shape):
  <https://docs.aws.amazon.com/sns/latest/dg/sns-sqs-as-subscriber.html>
- **SNS — FIFO topics**:
  <https://docs.aws.amazon.com/sns/latest/dg/sns-fifo-topics.html>

### EventBridge

- **Amazon EventBridge User Guide — landing page**:
  <https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-what-is.html>
- **EventBridge — event patterns** (the routing language; learn the `$or`, `prefix`, `numeric`, `exists` operators):
  <https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns.html>
- **EventBridge — archive and replay** (the load-bearing feature for this week):
  <https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-archive.html>
- **EventBridge — schema registry and code bindings**:
  <https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-schema-registry.html>
- **EventBridge Pipes — user guide** (source → filter → enrichment → target):
  <https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes.html>
- **EventBridge Scheduler** (the modern replacement for rules-on-a-cron):
  <https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html>

### Step Functions

- **AWS Step Functions Developer Guide — landing page**:
  <https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html>
- **Step Functions — Standard vs Express workflows**:
  <https://docs.aws.amazon.com/step-functions/latest/dg/concepts-standard-vs-express.html>
- **Amazon States Language specification** (the JSON DSL; bookmark it):
  <https://states-language.net/spec.html>
- **Step Functions — error handling: `Retry` and `Catch`**:
  <https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html>
- **Step Functions — distributed Map** (large fan-out over S3 / DynamoDB):
  <https://docs.aws.amazon.com/step-functions/latest/dg/use-dist-map-orchestrate-large-scale-parallel-workloads.html>

### Kinesis

- **Amazon Kinesis Data Streams Developer Guide**:
  <https://docs.aws.amazon.com/streams/latest/dev/introduction.html>
- **Kinesis — resharding, shard limits, and the hot-shard problem**:
  <https://docs.aws.amazon.com/streams/latest/dev/kinesis-using-sdk-java-resharding.html>
- **Kinesis — enhanced fan-out**:
  <https://docs.aws.amazon.com/streams/latest/dev/enhanced-consumers.html>
- **Amazon Data Firehose Developer Guide** (renamed from "Kinesis Data Firehose"; the service is now **Amazon Data Firehose**):
  <https://docs.aws.amazon.com/firehose/latest/dev/what-is-this-service.html>
- **Firehose — record format conversion to Parquet/ORC and dynamic partitioning**:
  <https://docs.aws.amazon.com/firehose/latest/dev/dynamic-partitioning.html>

### MSK

- **Amazon MSK Developer Guide — landing page**:
  <https://docs.aws.amazon.com/msk/latest/developerguide/what-is-msk.html>
- **MSK Serverless**:
  <https://docs.aws.amazon.com/msk/latest/developerguide/serverless.html>
- **MSK — IAM access control** (the auth mode we use; no SCRAM secret to babysit):
  <https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control.html>
- **Apache Kafka documentation** (the thing MSK manages; read the "Design" chapter):
  <https://kafka.apache.org/documentation/#design>

### Idempotency and Powertools

- **Powertools for AWS Lambda (Python) — Idempotency** (the `@idempotent` decorator and the DynamoDB persistence layer):
  <https://docs.powertools.aws.dev/lambda/python/latest/utilities/idempotency/>
- **Lambda — event source mapping for SQS** (`ReportBatchItemFailures`, batch window, `maxConcurrency`):
  <https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html>
- **Lambda — `bisectBatchOnFunctionError`, `maximumRecordAgeInSeconds`, `maximumRetryAttempts`** (Kinesis/DynamoDB mappings):
  <https://docs.aws.amazon.com/lambda/latest/dg/with-kinesis.html>

## Authoritative deep dives and talks

- **AWS re:Invent 2024 — "Advanced event-driven patterns with Amazon EventBridge" (API310)** — the canonical EventBridge architecture talk; Pipes, archive/replay, and schema registry shown end to end. Search YouTube: **"re:Invent EventBridge advanced patterns API310"**.
- **AWS re:Invent — "Building event-driven architectures" (the long-running SVS-track session)** — the decision-table session, re-recorded most years; the version from the most recent re:Invent is the one to watch.
- **Serverless Land — Patterns library** (filter by EventBridge, SQS, Step Functions; every pattern ships CDK/SAM/Terraform):
  <https://serverlessland.com/patterns>
- **Serverless Land — Event-Driven Architecture visuals**:
  <https://serverlessland.com/event-driven-architecture/visuals>
- **AWS Architecture Center — "Event-driven architecture" lens**:
  <https://aws.amazon.com/event-driven-architecture/>
- **AWS Prescriptive Guidance — "Idempotency for serverless applications"**:
  <https://docs.aws.amazon.com/prescriptive-guidance/latest/lambda-idempotency/welcome.html>
- **The Burning Monk (Yan Cui) — "Choosing between SNS, SQS, EventBridge, and Kinesis"** — the most-cited independent decision-table essay; opinionated and correct. Search: **"theburningmonk SNS SQS EventBridge Kinesis"**.
- **AWS Database Blog / Compute Blog — "Implementing idempotent AWS Lambda functions with Powertools"**:
  <https://aws.amazon.com/blogs/compute/>

## Open-source comparators

- **NATS / JetStream documentation** (the lightweight "EventBridge + SQS" in one binary):
  <https://docs.nats.io/>
- **RabbitMQ documentation** (exchanges, queues, dead-letter exchanges — the "SQS + SNS with richer routing"):
  <https://www.rabbitmq.com/documentation.html>
- **Apache Kafka documentation** (already linked under MSK; the design chapter is the comparator reading):
  <https://kafka.apache.org/documentation/>
- **Temporal documentation** (durable execution; the open-source competitor to Step Functions Standard):
  <https://docs.temporal.io/>
- **Confluent — "Kafka vs Kinesis"** (vendor-biased but technically precise on the partition/shard mapping):
  <https://www.confluent.io/learn/kafka-vs-kinesis/>

## CDK / IaC references

- **AWS CDK API reference — `aws-cdk-lib`** (the L2 constructs for `aws-sqs`, `aws-sns`, `aws-events`, `aws-events-targets`, `aws-stepfunctions`, `aws-kinesisfirehose`, `aws-pipes`):
  <https://docs.aws.amazon.com/cdk/api/v2/>
- **AWS CDK — EventBridge Pipes L2 construct (`aws-pipes-*` alpha/stable status notes)**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_pipes-readme.html>
- **OpenTofu registry — AWS provider** (`aws_sqs_queue`, `aws_sns_topic`, `aws_cloudwatch_event_bus`, `aws_kinesis_firehose_delivery_stream`):
  <https://search.opentofu.org/provider/hashicorp/aws/latest>
- **CloudFormation — `AWS::Events::Rule`, `AWS::SQS::Queue`, `AWS::Pipes::Pipe` resource references** (the templates CDK synthesizes to):
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html>

## If you want the long form (optional, paid)

- **"Building Event-Driven Microservices" — Adam Bellemare (O'Reilly).** The vendor-neutral mental model: event-carried state transfer, event sourcing, the cost of choreography vs orchestration. Read it once and the AWS service names become implementation details.
- **"Designing Data-Intensive Applications" — Martin Kleppmann (O'Reilly).** Chapters 11 (stream processing) and 8 (the trouble with distributed systems) are the theory under every word in this week's lectures. If you only read two chapters of one book this year, read these.

## A note on currency

AWS renames things. "Kinesis Data Firehose" is now **Amazon Data Firehose**. "CloudWatch Events" became **EventBridge** years ago but the API still answers to `events`. Step Functions "Express" is unchanged. MSK "Serverless" is unchanged. When a doc URL 404s, the **bold search term** next to it is the durable handle — paste it into the AWS docs search and you will land on the current page.
