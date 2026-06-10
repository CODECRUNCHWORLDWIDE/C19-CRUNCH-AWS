# Exercise 1 — Build the Order-Processing Pipeline (CDK TypeScript)

**Time:** ~2 hours. **Mode:** guided build. **Output:** a deployed stack named `Week10OrderPipeline` whose topology is:

```
                                          ┌─ rule: order-validator-rule ──> SQS (order-validator-queue) ──> Lambda (validator)
API GW  ──> Lambda  ──> EventBridge   ────┤
(POST   (front-door,   (crunch-orders-      ├─ rule: order-orchestrate-rule ──> Step Functions Express (order-saga)
/orders)  validates,     -bus)              │
          PutEvents)                        └─ rule: order-analytics-rule  ──> Kinesis Firehose ──> S3 (Parquet)
```

You will hand-build this in CDK. Exercises 2 and 3 add the DLQs/poison-pill drill and the archive replay on top of this exact stack.

---

## Step 0 — Scaffold the CDK app

```bash
mkdir week10-order-pipeline && cd week10-order-pipeline
cdk init app --language typescript
npm install aws-cdk-lib constructs
```

Confirm `cdk bootstrap` has been run in your `dev` account (Week 3). If not:

```bash
cdk bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/eu-west-1
```

---

## Step 1 — The custom bus, the queue, and the analytics bucket

Open `lib/week10-order-pipeline-stack.ts`. We build the durable pieces first — the bus, the work queue (with its DLQ pre-wired, because we never ship a queue without one), and the S3 bucket Firehose lands into.

```typescript
import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";
import * as tasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as firehose from "aws-cdk-lib/aws-kinesisfirehose";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import { SqsEventSource } from "aws-cdk-lib/aws-lambda-event-sources";

export class Week10OrderPipelineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // --- Custom event bus: isolate our app events from AWS service noise ---
    const bus = new events.EventBus(this, "OrdersBus", {
      eventBusName: "crunch-orders-bus",
    });

    // --- Work queue + its DLQ. Visibility timeout = 6x the consumer p99 (~5s). ---
    const validatorDlq = new sqs.Queue(this, "ValidatorDlq", {
      queueName: "order-validator-dlq",
      retentionPeriod: cdk.Duration.days(14),
    });
    const validatorQueue = new sqs.Queue(this, "ValidatorQueue", {
      queueName: "order-validator-queue",
      visibilityTimeout: cdk.Duration.seconds(30),
      receiveMessageWaitTime: cdk.Duration.seconds(20), // long polling
      deadLetterQueue: { queue: validatorDlq, maxReceiveCount: 3 },
    });

    // --- Analytics landing bucket ---
    const analyticsBucket = new s3.Bucket(this, "AnalyticsBucket", {
      bucketName: `crunch-orders-analytics-${this.account}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // dev only
      autoDeleteObjects: true,                  // dev only
      encryption: s3.BucketEncryption.S3_MANAGED,
    });
```

---

## Step 2 — The front-door Lambda and API Gateway

The front door validates the request, generates a stable `orderId` (the idempotency key for the whole pipeline), and `PutEvents` to the bus. Create `lambda/front-door/index.py`:

```python
import json
import os
import uuid
import boto3

events = boto3.client("events")
BUS_NAME = os.environ["BUS_NAME"]


def handler(event, context):
    body = json.loads(event.get("body") or "{}")
    # The orderId is the idempotency key. Generate once, here, at the edge.
    order_id = f"order#{uuid.uuid4().hex[:8]}"
    detail = {
        "orderId": order_id,
        "customerId": body.get("customerId"),
        "amount": body.get("amount"),
        "items": body.get("items", []),
    }
    events.put_events(
        Entries=[{
            "Source": "com.crunch.orders",
            "DetailType": "OrderPlaced",
            "Detail": json.dumps(detail),
            "EventBusName": BUS_NAME,
        }]
    )
    return {
        "statusCode": 202,
        "body": json.dumps({"orderId": order_id, "status": "accepted"}),
    }
```

Wire it in the stack:

```typescript
    const frontDoor = new lambda.Function(this, "FrontDoor", {
      functionName: "order-front-door",
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "index.handler",
      code: lambda.Code.fromAsset("lambda/front-door"),
      environment: { BUS_NAME: bus.eventBusName },
      timeout: cdk.Duration.seconds(10),
    });
    bus.grantPutEventsTo(frontDoor);

    const api = new apigw.RestApi(this, "OrdersApi", { restApiName: "orders-api" });
    api.root.addResource("orders").addMethod("POST", new apigw.LambdaIntegration(frontDoor));
```

---

## Step 3 — The validator Lambda behind SQS

The validator is the retry-able work consumer. It throws on a missing `customerId` (that is the poison-pill seam exercise 2 uses). Create `lambda/validator/index.py`:

```python
import json


class ValidationError(Exception):
    pass


def handler(event, context):
    failures = []
    for record in event["Records"]:
        try:
            detail = json.loads(record["body"])["detail"]
            if not detail.get("customerId"):
                raise ValidationError("missing customerId")
            print(f"[order-validator] validated {detail['orderId']}")
        except Exception as exc:  # noqa: BLE001
            print(f"[order-validator] FAILED {record['messageId']}: {exc}")
            failures.append({"itemIdentifier": record["messageId"]})
    # Partial batch response: only failed records are retried.
    return {"batchItemFailures": failures}
```

Wire it, with partial-batch-response on:

```typescript
    const validator = new lambda.Function(this, "Validator", {
      functionName: "order-validator",
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "index.handler",
      code: lambda.Code.fromAsset("lambda/validator"),
      timeout: cdk.Duration.seconds(5),
    });
    validator.addEventSource(new SqsEventSource(validatorQueue, {
      batchSize: 10,
      reportBatchItemFailures: true, // partial batch failure
    }));
```

---

## Step 4 — The Step Functions Express orchestration

A short, high-volume saga: validate → charge → confirm. Express, because it is per-order and sub-second. Create the state machine inline:

```typescript
    const chargeFn = new lambda.Function(this, "Charge", {
      functionName: "order-charge",
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "index.handler",
      code: lambda.Code.fromInline(
        "def handler(e, c):\n" +
        "    return {'orderId': e['orderId'], 'charged': True}\n"
      ),
      timeout: cdk.Duration.seconds(5),
    });

    const charge = new tasks.LambdaInvoke(this, "ChargeCard", {
      lambdaFunction: chargeFn,
      payloadResponseOnly: true,
    }).addRetry({
      errors: ["States.TaskFailed"],
      interval: cdk.Duration.seconds(1),
      maxAttempts: 3,
      backoffRate: 2.0,
    });

    const succeed = new sfn.Succeed(this, "OrderComplete");
    const definition = charge.next(succeed);

    const orderSaga = new sfn.StateMachine(this, "OrderSaga", {
      stateMachineName: "order-saga",
      stateMachineType: sfn.StateMachineType.EXPRESS,
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      logs: {
        destination: new logs.LogGroup(this, "OrderSagaLogs", {
          retention: logs.RetentionDays.ONE_WEEK,
        }),
        level: sfn.LogLevel.ALL,
      },
    });
```

---

## Step 5 — The Firehose analytics tap (Parquet to S3)

Firehose buffers and lands every order in S3 for Week 11's Athena queries. We use the L1 `CfnDeliveryStream` because it exposes the buffering hints cleanly.

```typescript
    const firehoseRole = new iam.Role(this, "FirehoseRole", {
      assumedBy: new iam.ServicePrincipal("firehose.amazonaws.com"),
    });
    analyticsBucket.grantReadWrite(firehoseRole);

    const deliveryStream = new firehose.CfnDeliveryStream(this, "AnalyticsStream", {
      deliveryStreamName: "order-analytics",
      deliveryStreamType: "DirectPut",
      extendedS3DestinationConfiguration: {
        bucketArn: analyticsBucket.bucketArn,
        roleArn: firehoseRole.roleArn,
        prefix: "orders/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/",
        errorOutputPrefix: "errors/",
        bufferingHints: { sizeInMBs: 64, intervalInSeconds: 60 },
        compressionFormat: "GZIP",
      },
    });
```

---

## Step 6 — The three rules wiring the bus to the three targets

```typescript
    // Rule 1: every order -> the validator queue
    new events.Rule(this, "ValidatorRule", {
      ruleName: "order-validator-rule",
      eventBus: bus,
      eventPattern: { source: ["com.crunch.orders"], detailType: ["OrderPlaced"] },
      targets: [new targets.SqsQueue(validatorQueue)],
    });

    // Rule 2: every order -> the Express saga
    new events.Rule(this, "OrchestrateRule", {
      ruleName: "order-orchestrate-rule",
      eventBus: bus,
      eventPattern: { source: ["com.crunch.orders"], detailType: ["OrderPlaced"] },
      targets: [new targets.SfnStateMachine(orderSaga, {
        input: events.RuleTargetInput.fromEventPath("$.detail"),
      })],
    });

    // Rule 3: every order -> Firehose for analytics
    new events.Rule(this, "AnalyticsRule", {
      ruleName: "order-analytics-rule",
      eventBus: bus,
      eventPattern: { source: ["com.crunch.orders"], detailType: ["OrderPlaced"] },
      targets: [new targets.KinesisFirehoseStreamV2(
        firehose.DeliveryStream.fromDeliveryStreamName(
          this, "ImportedStream", deliveryStream.ref,
        ),
      )],
    });

    // --- Outputs the Python drills read ---
    new cdk.CfnOutput(this, "ApiUrl", { value: api.url });
    new cdk.CfnOutput(this, "BusName", { value: bus.eventBusName });
    new cdk.CfnOutput(this, "ValidatorQueueUrl", { value: validatorQueue.queueUrl });
    new cdk.CfnOutput(this, "ValidatorDlqUrl", { value: validatorDlq.queueUrl });
    new cdk.CfnOutput(this, "AnalyticsBucket", { value: analyticsBucket.bucketName });
  }
}
```

Register the stack in `bin/week10-order-pipeline.ts`:

```typescript
#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { Week10OrderPipelineStack } from "../lib/week10-order-pipeline-stack";

const app = new cdk.App();
new Week10OrderPipelineStack(app, "Week10OrderPipeline", {
  env: { region: "eu-west-1" },
});
```

---

## Step 7 — Deploy and smoke-test

```bash
npm run build
cdk deploy --require-approval never

# Grab the API URL from the deploy output, then send a good order:
API=$(aws cloudformation describe-stacks --stack-name Week10OrderPipeline \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)

curl -s -X POST "${API}orders" \
  -H 'content-type: application/json' \
  -d '{"customerId":"cust#42","amount":1299,"items":["sku-1","sku-2"]}'
```

Expected response:

```json
{"orderId": "order#a1b2c3d4", "status": "accepted"}
```

Confirm the fan-out worked:

```bash
# Validator Lambda logs should show the validated order:
aws logs tail /aws/lambda/order-validator --since 2m
# -> [order-validator] validated order#a1b2c3d4

# Step Functions Express execution succeeded (check CloudWatch Logs for the saga):
aws logs tail /aws/vendedlogs/states --since 2m 2>/dev/null || \
  aws stepfunctions list-state-machines --query "stateMachines[?name=='order-saga']"

# Firehose lands in S3 after the buffering interval (~60s):
BUCKET=$(aws cloudformation describe-stacks --stack-name Week10OrderPipeline \
  --query "Stacks[0].Outputs[?OutputKey=='AnalyticsBucket'].OutputValue" --output text)
sleep 70 && aws s3 ls "s3://${BUCKET}/orders/" --recursive
```

---

## Expected output (the whole pipeline working)

```
{"orderId": "order#a1b2c3d4", "status": "accepted"}
[order-validator] validated order#a1b2c3d4
s3://crunch-orders-analytics-111122223333/orders/year=2026/month=06/day=09/order-analytics-1-2026-06-09-14-01-12-... .gz
```

One POST, three independent reactions — a validated order in the queue consumer, a completed Express saga, and an object in S3 — all from one `PutEvents`. That is the EventBridge fan-out the rest of the week builds on.

---

## Teardown

```bash
cdk destroy --force
```

---

## What you just proved

- A single producer (`PutEvents`) fans out to three independent consumers via EventBridge rules — no producer-side coupling to any consumer.
- The work queue already has its DLQ wired (`maxReceiveCount: 3`) and long polling on — exercise 2 fires the poison pill that exercises it.
- Step Functions Express is the orchestration tier; Firehose is the analytics sink. Each consumer can fail, scale, and deploy independently.
- Every resource name is a CloudFormation output, so the Python drills can find them without hard-coding ARNs.

On to **exercise 2**: add the poison pill and watch it land in `order-validator-dlq`.
