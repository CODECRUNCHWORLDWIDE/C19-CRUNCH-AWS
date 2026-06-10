# Challenge 1 — Swap the EventBridge Spine for MSK

**Difficulty:** hard, open-ended. **Time:** 3–4 hours including teardown. **Deliverable:** a working MSK-backed version of the order pipeline *plus* a ≥2-page writeup defending the trade-offs.

> The design review is over. The architect liked your EventBridge pipeline. Then the staff engineer says: "We're standardizing on Kafka org-wide. Show me this pipeline on MSK and tell me, with numbers, what we gain and what we lose." That conversation, with a budget attached, is this challenge.

---

## The task

Take the order pipeline from exercise 1 and **replace the EventBridge custom bus** with an **MSK Serverless** cluster. The producer (front-door Lambda) now produces to a Kafka topic instead of `PutEvents`. The three consumers (validator, orchestrator, analytics) become Kafka consumer groups reading the same topic. Then reproduce — or honestly fail to reproduce — the three properties EventBridge gave you: **fan-out, replay, and idempotent reprocessing**.

You are not required to keep Step Functions and Firehose unchanged (though you may). The spine — the thing that carries the `OrderPlaced` event from producer to the reactors — is what swaps.

---

## Acceptance criteria

A passing submission has all of the following:

1. **A deployed MSK Serverless cluster** (CDK or OpenTofu, your choice), IAM-auth, with an `orders` topic. Tear it down after; include the teardown command output in your writeup.
2. **A producer** (Lambda or local script) that produces `OrderPlaced` events to the `orders` topic, keyed by `customerId` so per-customer ordering holds.
3. **At least two independent consumer groups** reading the same topic — e.g. `validator-group` and `analytics-group` — demonstrating Kafka fan-out (every group gets every message; offsets are per-group).
4. **A replay demonstration**: reset a consumer group's offset to a point in the past (`kafka-consumer-groups --reset-offsets --to-datetime ...` or the equivalent) and show the group reprocessing from there, with your **idempotency table rejecting the duplicates** so no order is charged twice. This is the Kafka analogue of the EventBridge archive replay from exercise 3.
5. **A ≥2-page writeup** answering the four questions below with numbers, not adjectives.

---

## The four questions (the actual deliverable)

### 1. Ordering — what changed?

- EventBridge gives you **no ordering guarantee** at all. MSK gives you **strict ordering within a partition**.
- Show: produce 10 orders for the same `customerId` and confirm a single-partition-reading consumer sees them in produce order. Then change the key to round-robin and show ordering breaks across partitions.
- Answer: when did EventBridge's lack of ordering not matter for orders, and when would MSK's per-partition ordering be the reason you *must* use it? (Hint: think about a sequence of balance adjustments vs independent order placements.)

### 2. Replay — what changed?

- EventBridge replay is a one-line CLI call over a *time window*, re-evaluating rules, with **no ordering** during replay.
- MSK replay is an **offset reset** on a consumer group, preserving **per-partition order**, and the data lives in the topic for as long as your retention allows (configurable, can be effectively infinite with tiered storage).
- Show both your EventBridge replay (from exercise 3) and your MSK offset-reset replay working against the same idempotent consumer.
- Answer: which replay model is *operationally* easier, and which is *semantically* stronger? When does the difference change your architecture choice?

### 3. Throughput — what changed?

- EventBridge has a per-account `PutEvents` quota (raisable) and adds ~500 ms routing latency.
- MSK Serverless scales to a high write ceiling per partition and has single-digit-ms produce latency.
- Show: measure produce-to-consume latency for both spines at a modest rate (e.g. 100 events/s for 60 s). Report p50 and p99 for each.
- Answer: at what sustained event rate does the EventBridge per-event model start to strain, and where does MSK's partition model become the obvious choice?

### 4. Cost — what changed? (bring the spreadsheet)

- EventBridge: **$1.00 per million custom events** published (plus archive storage and replay). **Free when idle.**
- MSK Serverless: billed per **partition-hour** (~$0.0021/partition-hour as of 2026, confirm the current number on the pricing page) **plus** per-GB in/out **plus** storage-GB-hour. **Bills even when idle.**
- Build a spreadsheet (or a short Python script) that computes monthly cost for both at three event rates: **idle (1k/day), steady (1M/day), and high (100M/day)**. Find the **crossover rate** where MSK Serverless becomes cheaper than EventBridge.
- Answer: state the crossover number. Below it, EventBridge wins on cost; above it, MSK does. Defend why the org-wide Kafka standardization might still justify MSK *below* the crossover (operational consistency, ecosystem, no per-event tax at scale).

---

## Starter: MSK Serverless cluster in CDK

```typescript
import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as msk from "aws-cdk-lib/aws-msk";

export class MskSpineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const vpc = ec2.Vpc.fromLookup(this, "Vpc", { isDefault: true });
    const sg = new ec2.SecurityGroup(this, "MskSg", { vpc });
    sg.addIngressRule(sg, ec2.Port.tcp(9098), "MSK IAM-auth port (self)");

    const cluster = new msk.CfnServerlessCluster(this, "OrdersCluster", {
      clusterName: "crunch-orders-msk",
      vpcConfigs: [{
        subnetIds: vpc.selectSubnets({ subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS }).subnetIds,
        securityGroups: [sg.securityGroupId],
      }],
      clientAuthentication: { sasl: { iam: { enabled: true } } },
    });

    new cdk.CfnOutput(this, "ClusterArn", { value: cluster.attrArn });
  }
}
```

## Starter: IAM-auth Kafka producer (Python)

```python
import socket
from aws_msk_iam_sasl_signer import MSKAuthTokenProvider
from kafka import KafkaProducer
import json

REGION = "eu-west-1"
BROKERS = ["<bootstrap-broker-iam-endpoint>:9098"]


class MSKTokenProvider:
    def token(self):
        token, _ = MSKAuthTokenProvider.generate_auth_token(REGION)
        return token


producer = KafkaProducer(
    bootstrap_servers=BROKERS,
    security_protocol="SASL_SSL",
    sasl_mechanism="OAUTHBEARER",
    sasl_oauth_token_provider=MSKTokenProvider(),
    client_id=socket.gethostname(),
    key_serializer=lambda k: k.encode("utf-8"),
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

# Key by customerId -> per-customer ordering on a partition.
producer.send("orders", key="cust#42", value={"orderId": "order#1", "amount": 1299})
producer.flush()
```

(Install with `pip install kafka-python aws-msk-iam-sasl-signer`. You will also need to create the `orders` topic once — via a Kafka admin client or `kafka-topics.sh` pointed at the IAM-auth bootstrap endpoint.)

## Replay via offset reset

```bash
# Reset the analytics-group to re-read everything from 1 hour ago.
kafka-consumer-groups.sh \
  --bootstrap-server <broker>:9098 \
  --command-config client-iam.properties \
  --group analytics-group \
  --topic orders \
  --reset-offsets --to-datetime 2026-06-09T13:00:00.000 \
  --execute
```

Then re-run the analytics consumer and watch it reprocess from the reset offset — with your idempotency table skipping every order it already charged.

---

## Teardown (do not skip — MSK bills while idle)

```bash
# CDK
cdk destroy MskSpineStack --force

# or OpenTofu
tofu destroy -auto-approve

# Confirm the cluster is gone:
aws kafka list-clusters-v2 --query "ClusterInfoList[?ClusterName=='crunch-orders-msk']"
# -> []   (empty == torn down)
```

---

## What "defending the choice" looks like

The strongest writeups end with a one-paragraph recommendation that a real architect would sign:

> "For *this* order pipeline at our current ~200k orders/day, EventBridge is the correct spine: it is free when idle, the ~500 ms routing latency is invisible for an order event, replay is a one-line operation, and we don't run any infrastructure. We would switch to MSK only if (a) we cross ~XM events/day where the per-event tax exceeds partition-hour cost, (b) we need strict cross-event ordering that EventBridge cannot give, or (c) the org-wide Kafka standardization makes operational consistency worth more than the cost delta. Today, none of those hold, so: EventBridge. Here is the spreadsheet."

That is the deliverable. Not a cluster — a defense.
