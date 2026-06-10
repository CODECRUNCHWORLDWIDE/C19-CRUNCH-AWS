# Lecture 2 — Chaos Engineering with AWS Fault Injection Service, and the Blameless Postmortem

> **Reading time:** ~80 minutes. **Hands-on time:** ~90 minutes (you build a FIS experiment template, wire a stop condition, run the AZ-failover drill, and start the postmortem).

Lecture 1 said the failure-modes section is half the architecture review and that a *measured* RTO beats a *target* RTO every time. This lecture is how you produce the measurements. We will cover chaos engineering as a discipline — the steady-state hypothesis, the controlled experiment, the seatbelt — and then the AWS-native tool for it, the **Fault Injection Service (FIS)**: its four building blocks, the IAM model that trips everyone up, and how to assemble the four capstone drills. Then we cover the artifact the drills produce: the **blameless postmortem**, with a five-whys root cause and action items that have owners and dates. By the end you can inject a fault on purpose, measure the recovery, and write the document that turns "it broke" into "we learned."

## 2.1 — What chaos engineering actually is

Chaos engineering is not "break things in production and see what happens." That is sabotage. Chaos engineering is **a controlled experiment to falsify a hypothesis about your system's resilience.** The discipline, from the Netflix-era principles, is four steps:

1. **Define steady state.** A measurable property that says the system is healthy: "p99 latency < 300 ms and error rate < 0.1% at 100 RPS." This is your hypothesis's null — the thing you expect to *stay true* even under the fault.

2. **Hypothesize that steady state continues under a fault.** "If I lose one Availability Zone, steady state holds, because traffic shifts to the other two AZs and the Aurora writer fails over within my 5-minute RTO." You are stating, in advance, what you expect — which means the experiment can *surprise* you, which is the entire value.

3. **Inject a real-world fault** in the smallest blast radius that tests the hypothesis. Kill one AZ's nodes. Throttle one table. Saturate one function's concurrency. The fault must be *real* (an actual AZ outage, not a mocked one) and *bounded* (one AZ, with a seatbelt that stops it if the experiment goes wrong).

4. **Measure, and either confirm or falsify.** Did steady state hold? If yes, you have *evidence* your design survives that fault — the RTO number you bring to the review. If no, you found a weakness in a controlled experiment instead of at 3 a.m. — which is the whole point.

The mindset shift: **a chaos experiment that finds nothing is still a success** (you confirmed resilience), and one that finds a weakness is an even bigger success (you found it cheaply). The failure mode is *not running the experiment* and discovering the weakness in a real incident. The capstone makes you run it, measure it, and write down what you learned.

## 2.2 — The seatbelt: why you never inject a fault without a stop condition

Before any tooling, internalize the one rule that separates chaos engineering from recklessness: **every fault injection runs behind a stop condition that halts it the instant the system goes outside acceptable bounds.** You hypothesize steady state holds; if you are *wrong* and steady state collapses, you do not want the fault to keep running while users suffer. The stop condition is a CloudWatch alarm — "if the API 5xx rate exceeds 5%, stop the experiment immediately" — that FIS watches continuously and that aborts the experiment and (where the action supports it) reverses the fault.

This is why we do chaos engineering on AWS with FIS rather than a hand-rolled script: FIS makes the stop condition a first-class, enforced part of the experiment, with IAM governance over who can inject what. A bash script that kills instances has no seatbelt. FIS does. Run your first real drill against a non-prod copy of the capstone regardless — but even then, the stop condition is the habit you build now so it is reflexive when you do this against production later.

## 2.3 — FIS: the four building blocks

An FIS **experiment template** is built from exactly four things. Learn them and FIS is simple.

1. **Actions** — the faults to inject. Each action has a type (`aws:ec2:stop-instances`, `aws:dynamodb:...`, `aws:lambda:invocation-add-delay`, the AZ-power scenario) and parameters (how long, how many, what error). Actions can run in sequence or parallel and can depend on one another (`startAfter`).

2. **Targets** — the resources an action hits, selected by explicit ARN, by **resource tag**, or by a **resource filter** (e.g. "EC2 instances where `availability-zone = us-east-1a` and tag `service = eks-node`"). Tag- and filter-based targeting is what lets one template hit "all the nodes in one AZ" without you listing instance IDs that change on every scale event.

3. **Stop conditions** — the CloudWatch alarms that abort the experiment. The seatbelt from §2.2. You can have several; if any fires, the experiment stops.

4. **An execution role** — the IAM role FIS *assumes* to do the injection. This is the part everyone gets wrong, so it gets its own section.

```
   ┌──────────────────────── FIS Experiment Template ────────────────────────┐
   │                                                                          │
   │  Actions ──────────────►  Targets ──────────────►  (resources hit)       │
   │   • stop-instances          • tag: service=eks-node                      │
   │   • az-power-interruption    & az = us-east-1a                           │
   │                                                                          │
   │  Stop conditions  ◄──── CloudWatch alarm: API 5xx > 5%  (the seatbelt)   │
   │                                                                          │
   │  Execution role: arn:aws:iam::ACCT:role/fis-experiment-role             │
   │   (FIS assumes this to call ec2:StopInstances, etc.)                      │
   └──────────────────────────────────────────────────────────────────────────┘
        │ start-experiment
        ▼
   A running Experiment (has a state: initiating → running → completed/stopped/failed)
```

## 2.4 — The IAM model: the thing that trips everyone up

FIS does not act as *you*. It assumes an **execution role** you specify, and that role must hold the permissions to perform the actions on the targets. The first FIS experiment everyone writes fails with an access-denied because the role is missing an action. The fix is to grant the role exactly the target-resource actions each FIS action needs, plus the `fis` permissions, and to let FIS assume it.

The trust policy lets the FIS service assume the role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "fis.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

The permission policy grants the actions the experiments need. For the AZ/EKS-node drill (FIS stops EC2 instances that back the EKS managed node group), plus the CloudWatch read it needs for stop conditions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Ec2NodeFaults",
      "Effect": "Allow",
      "Action": [
        "ec2:StopInstances",
        "ec2:StartInstances",
        "ec2:RebootInstances",
        "ec2:DescribeInstances"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": { "aws:ResourceTag/service": "eks-node" }
      }
    },
    {
      "Sid": "StopConditionAlarmRead",
      "Effect": "Allow",
      "Action": ["cloudwatch:DescribeAlarms"],
      "Resource": "*"
    }
  ]
}
```

Note the `Condition` scoping `ec2:StopInstances` to instances tagged `service=eks-node` — least privilege even for the chaos role, so a misconfigured experiment cannot stop your database host. (For the AZ-power-interruption *scenario*, AWS publishes a managed policy / a longer action list covering the network and managed-service AZ affinity it manipulates; attach what the scenario doc lists. For the DynamoDB and Lambda drills, the role needs the corresponding `dynamodb:` and `lambda:` actions on the targeted ARNs. Always start from the action's "IAM permissions" doc section and grant exactly those.)

## 2.5 — Building the AZ-failover experiment template

Here is the AZ-failover experiment as JSON you pass to `aws fis create-experiment-template`. It stops every EC2 instance tagged as an EKS node in one AZ, with a stop condition on the API's 5xx alarm. This is the template Exercise 1 builds and runs.

```json
{
  "description": "Capstone AZ-failover drill: stop all EKS nodes in us-east-1a",
  "roleArn": "arn:aws:iam::111122223333:role/fis-experiment-role",
  "stopConditions": [
    {
      "source": "aws:cloudwatch:alarm",
      "value": "arn:aws:cloudwatch:us-east-1:111122223333:alarm:capstone-api-5xx-high"
    }
  ],
  "targets": {
    "eksNodesAz1a": {
      "resourceType": "aws:ec2:instance",
      "selectionMode": "ALL",
      "resourceTags": { "service": "eks-node" },
      "filters": [
        {
          "path": "Placement.AvailabilityZone",
          "values": ["us-east-1a"]
        },
        {
          "path": "State.Name",
          "values": ["running"]
        }
      ]
    }
  },
  "actions": {
    "stopAz1aNodes": {
      "actionId": "aws:ec2:stop-instances",
      "description": "Stop EKS nodes in us-east-1a to simulate AZ loss",
      "parameters": {
        "startInstancesAfterDuration": "PT10M"
      },
      "targets": { "Instances": "eksNodesAz1a" }
    }
  },
  "tags": { "Name": "capstone-az-failover", "team": "platform", "environment": "nonprod" }
}
```

Two details that matter. `startInstancesAfterDuration: PT10M` tells FIS to *automatically restart* the stopped instances after 10 minutes — the fault is self-reversing, so even if your laptop dies mid-drill the AZ comes back. And the `filters` select only *running* nodes in *one* AZ, so the blast radius is exactly one AZ's worth of compute and no more. The stop condition (`capstone-api-5xx-high`) is the seatbelt: if killing that AZ pushes the API over 5% 5xx — meaning your multi-AZ failover did *not* work — FIS stops the experiment and restarts the nodes immediately.

For a *true* full-AZ outage (not just compute, but the network and managed-service AZ affinity), use the FIS **AZ Availability: Power Interruption** scenario instead of a bare `stop-instances` action. It is the AWS-supported way to test that your Aurora writer fails over to another AZ, your ALB drains the dead AZ's targets, and your cross-AZ traffic reroutes — all the things a real AZ event does. The scenario wraps the actions and the longer IAM action list; you supply the targets and the stop condition. The lecture's bare `stop-instances` template is the simpler starting point; graduate to the AZ-power scenario for the capstone's real AZ-failover claim.

Defining the same template in **CDK** (TypeScript), so it lives in the capstone monorepo as code:

```typescript
import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as fis from 'aws-cdk-lib/aws-fis';

export class ChaosStack extends Stack {
  constructor(scope: Construct, id: string, fisRoleArn: string, alarmArn: string, props?: StackProps) {
    super(scope, id, props);

    new fis.CfnExperimentTemplate(this, 'AzFailover', {
      description: 'Capstone AZ-failover drill: stop EKS nodes in us-east-1a',
      roleArn: fisRoleArn,
      stopConditions: [{ source: 'aws:cloudwatch:alarm', value: alarmArn }],
      tags: { Name: 'capstone-az-failover', team: 'platform', environment: 'nonprod' },
      targets: {
        eksNodesAz1a: {
          resourceType: 'aws:ec2:instance',
          selectionMode: 'ALL',
          resourceTags: { service: 'eks-node' },
          filters: [
            { path: 'Placement.AvailabilityZone', values: ['us-east-1a'] },
            { path: 'State.Name', values: ['running'] },
          ],
        },
      },
      actions: {
        stopAz1aNodes: {
          actionId: 'aws:ec2:stop-instances',
          description: 'Stop EKS nodes in us-east-1a',
          parameters: { startInstancesAfterDuration: 'PT10M' },
          targets: { Instances: 'eksNodesAz1a' },
        },
      },
    });
  }
}
```

## 2.6 — The four capstone drills, and what each proves

The capstone spec requires three drills plus a bonus. Each tests a different failure class and proves (or disproves) a different design claim.

### Drill 1 — AZ failover (the RTO drill)

**Fault:** stop one AZ's worth of EKS nodes and fail over the Aurora writer (the AZ-power scenario does both). **Hypothesis:** steady state holds; the ALB drains the dead AZ, Karpenter (or the ASG) reschedules pods into the surviving AZs, and Aurora's writer fails over to a standby AZ within the 5-minute RTO. **What you measure:** the recovery time (the RTO number for the review) and whether any requests were lost (the RPO). **What it commonly reveals:** that you ran the SageMaker endpoint as a single instance in one AZ (now it is down for the whole drill), or that your EKS node group had no spare capacity headroom, so rescheduling 1/3 of the pods stalled.

### Drill 2 — DynamoDB throttle (the hot-partition drill)

**Fault:** drive disproportionate traffic at one partition key while the table is provisioned (or even on-demand below its burst), forcing `ProvisionedThroughputExceededException` / throttling on that partition. You can combine a FIS action with a targeted load loop. **Hypothesis:** the system degrades *gracefully* — throttled writes retry with backoff, land in the SQS retry queue, and eventually the DLQ if they keep failing, and the rest of the table is unaffected. **What you measure:** the throttle count, where the back-pressure landed, and whether your **write-sharding** mitigation (Week 9) actually defeats the hot partition when you turn it on. **What it commonly reveals:** that a consumer was *not* idempotent, so the retries double-wrote; or that there was no DLQ on the path, so throttled events vanished.

### Drill 3 — Lambda concurrency exhaustion (the back-pressure drill)

**Fault:** drive more concurrent invocations at a Lambda than its **reserved concurrency** allows, so Lambda throttles (`429 TooManyRequestsException`) the excess. **Hypothesis:** the throttle is *back-pressure*, not data loss — for async invokes Lambda retries and eventually routes to the configured DLQ / on-failure destination; for sync invokes the caller (API Gateway) returns a 429 the client can retry. **What you measure:** the `Throttles` metric, the SQS/DLQ depth as the back-pressure accumulates, and the recovery once the load drops. **What it commonly reveals:** that reserved concurrency was set too low (or not at all, so one function starved the whole account's concurrency pool — the noisy-neighbor failure), or that the async path had no DLQ so throttled-then-expired events were silently dropped.

### Drill 4 — the bonus (NAT saturation / CloudFront origin failure / KMS throttle)

Pick one. **NAT saturation:** flood egress through a single NAT Gateway and watch connections fail — proving the Week 4 lesson that one NAT is a SPOF and a bottleneck, and that VPC endpoints would have removed the dependency. **CloudFront origin failure:** kill the origin and verify origin failover (or that you serve a cached/error response gracefully). **KMS throttle:** drive enough KMS operations to hit the request-rate limit and watch envelope-encryption-dependent paths degrade — proving you understand that KMS is a shared, rate-limited dependency. Each makes your postmortem section stronger; the syllabus requires only one bonus.

## 2.7 — Measuring the drill: the timeline that becomes the RTO

A drill is worthless without a measured timeline. You run a continuous probe (one request per second against the public API) before, during, and after the fault, and you compute four timestamps:

- **t0** — steady-state baseline established (probes green for ≥ N consecutive seconds).
- **t_fault** — the fault is injected (FIS experiment transitions to `running`).
- **t_impact** — the first *sustained* breach of steady state (probes go red past a hysteresis threshold, so a single blip does not count).
- **t_recover** — steady state restored (probes green again past the hysteresis threshold).

From those: **recovery_seconds = t_recover − t_fault** (your RTO), and **impact_seconds = t_recover − t_impact** (the user-visible outage window). If the system *absorbed* the fault — no sustained breach — then `t_impact` is "none" and you have proven the fault is transparent to users, an even stronger result. Exercise 2 ships a driver that computes exactly these timestamps and emits the postmortem skeleton with them filled in. The discipline of the hysteresis (N consecutive bad probes, not one) matters: networks blip, and you do not want a single dropped packet recorded as an outage.

A worked timeline you would put in the review:

```
t0       2026-06-10T14:02:00Z   steady state: p99 142ms, 0% errors at 100 RPS
t_fault  2026-06-10T14:02:20Z   FIS stopped 4 EKS nodes in us-east-1a
t_impact 2026-06-10T14:02:24Z   API 5xx spiked to 11% (pods rescheduling)
t_recover 2026-06-10T14:04:42Z  5xx back to <0.1%, Aurora writer promoted in 1b
                                recovery_seconds = 142  (RTO target 300 -> PASS)
                                impact_seconds   = 138   data_loss: none (DLQ flat)
```

That paragraph — a measured timeline with a PASS/REVIEW verdict against the documented RTO — is what the reliability question set in Lecture 1 was asking for. You do not get to *say* your RTO is 5 minutes; you get to *show* it was 142 seconds.

## 2.8 — The blameless postmortem: turning the drill into a document

The drill produces data; the postmortem turns it into organizational learning. AWS, Google, and every serious operations culture write postmortems the same way, and the capstone requires one per drill. The non-negotiable properties:

**Blameless.** The postmortem describes *what the system did*, not *who did what wrong*. "Human error" is never a root cause — if a human could take an action that broke production, the *system that allowed that action without a guardrail* is the root cause. This is not politeness; it is correctness. Blame makes people hide information, which makes the next incident worse. Blameless makes people surface information, which makes the system better. A postmortem that says "Alice deployed a bad config" failed; one that says "the pipeline had no config validation gate, so a malformed config reached production" succeeded — and the action item writes itself (add the gate).

**Five whys to a systemic root.** You ask "why" repeatedly past the proximate cause until you reach something systemic and fixable:

```
The API returned 5xx for 138 seconds.
  Why? One AZ's EKS nodes stopped and pods took 138s to reschedule.
    Why did rescheduling take 138s? The node group had no spare capacity headroom,
      so new nodes had to be provisioned before pods could be placed.
        Why no headroom? The cost-optimization pass set min nodes = exactly the
          steady-state need with no buffer.
            Why no buffer? There was no documented headroom policy balancing
              cost against AZ-failure recovery time.   <-- systemic root
```

The root is not "the nodes stopped" (that was the *injected fault*, expected). The root is the *missing headroom policy* — a systemic, fixable thing. The action item: "define a node-headroom policy (e.g. N+1 AZ of spare capacity via Karpenter over-provisioning) with an owner and a date."

**A correct timeline.** The measured timestamps from §2.7, in UTC, so anyone reading later can reconstruct what happened when.

**Action items with owners, dates, and tags.** Every action item has a *named owner*, a *due date*, and a tag: **accept** (we acknowledge this risk and choose not to fix it, with a reason), **mitigate-now** (fix before the next deploy), or **mitigate-later** (track in the backlog with a trigger for when it becomes urgent). An action item without an owner and a date is a wish, not a commitment. A postmortem whose action items are all unowned is a postmortem nobody will act on.

The postmortem template, which Exercise 2 generates pre-filled with your measured timeline:

```markdown
# Chaos Drill Postmortem — AZ Failover

## Summary
- Drill: AZ failover (FIS, us-east-1a)
- Verdict: PASS (RTO 142s < 300s target; data_loss: none)
- User-visible impact window: 138s

## Timeline (UTC)
| Event | Time |
|---|---|
| Steady-state baseline | 2026-06-10T14:02:00Z |
| Fault injected         | 2026-06-10T14:02:20Z |
| First SLO breach       | 2026-06-10T14:02:24Z |
| SLO restored           | 2026-06-10T14:04:42Z |

## Root cause (five whys)
<!-- the chain above -->

## What we expected vs. what happened
<!-- the hypothesis from §2.1 vs. the measurement -->

## Action items
| Action | Owner | Due | Tag |
|---|---|---|---|
| Define node-headroom policy (N+1 AZ spare) | @you | 2026-06-20 | mitigate-now |
| Run AZ drill weekly as a scheduled GameDay   | @you | 2026-07-01 | mitigate-later |
```

## 2.9 — Chaos as a practice, not an event

The mature end state is not "we ran a chaos drill once before the review." It is **GameDays** — scheduled, rehearsed chaos exercises the team runs regularly, with the postmortem feeding action items back into the system, which the next GameDay re-tests. You can encode this on AWS: an EventBridge-scheduled rule that starts your FIS experiment weekly against a non-prod copy, posting the recovery time to a CloudWatch dashboard, so resilience is *trended* rather than assumed. The stretch goal turns your one-off capstone drill into exactly this. The principle: a resilience property you do not continuously test is a resilience property you are slowly losing, because every deploy can erode it. Chaos engineering done well is a *regression test for resilience*.

Scheduling the AZ-failover experiment as a weekly GameDay is a small amount of CDK. An EventBridge Scheduler rule invokes a tiny Lambda that calls `fis:StartExperiment` on your template, and the experiment's own stop condition keeps it safe:

```typescript
import { Duration, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as scheduler from 'aws-cdk-lib/aws-scheduler';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';

export class GameDayStack extends Stack {
  constructor(scope: Construct, id: string, experimentTemplateId: string, props?: StackProps) {
    super(scope, id, props);

    // A tiny Lambda that starts the FIS experiment from its template id.
    const starter = new lambda.Function(this, 'StartDrill', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'index.handler',
      timeout: Duration.seconds(30),
      environment: { TEMPLATE_ID: experimentTemplateId },
      code: lambda.Code.fromInline(
        'import os, boto3\n'
        + 'def handler(event, context):\n'
        + '    fis = boto3.client("fis")\n'
        + '    r = fis.start_experiment(experimentTemplateId=os.environ["TEMPLATE_ID"])\n'
        + '    return {"experimentId": r["experiment"]["id"]}\n'
      ),
    });
    // Least privilege: start only this one template.
    starter.addToRolePolicy(new iam.PolicyStatement({
      actions: ['fis:StartExperiment'],
      resources: [
        `arn:aws:fis:${this.region}:${this.account}:experiment-template/${experimentTemplateId}`,
        `arn:aws:fis:${this.region}:${this.account}:experiment/*`,
      ],
    }));

    // Weekly, Monday 15:00 UTC, against the non-prod copy only.
    new scheduler.CfnSchedule(this, 'WeeklyGameDay', {
      flexibleTimeWindow: { mode: 'OFF' },
      scheduleExpression: 'cron(0 15 ? * MON *)',
      target: {
        arn: starter.functionArn,
        roleArn: new iam.Role(this, 'SchedRole', {
          assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
          inlinePolicies: {
            invoke: new iam.PolicyDocument({
              statements: [new iam.PolicyStatement({
                actions: ['lambda:InvokeFunction'],
                resources: [starter.functionArn],
              })],
            }),
          },
        }).roleArn,
      },
    });
  }
}
```

Now resilience is exercised every Monday, the recovery time is trended on a dashboard, and a regression (a deploy that quietly raised the RTO) shows up as a rising line instead of a 3-a.m. surprise. That is the difference between *having* tested your failover once and *continuously testing* it.

### The common mistakes that turn a drill into an outage

Even with FIS, teams make the same handful of mistakes. Know them so you do not:

- **No stop condition.** The cardinal sin. An uncapped fault in an account with users is sabotage, not chaos engineering. Wire the alarm first, every time.
- **Testing in prod first.** Run the drill against a non-prod copy until the recovery is boringly reliable, *then* graduate to prod as a GameDay with the team watching. Your first AZ drill should not be against paying customers.
- **No steady-state baseline.** If you inject the fault without first establishing that the system was healthy, you cannot tell whether the fault caused the breach or the system was already broken. Always probe for ≥ 20 seconds of green before injecting.
- **No hysteresis on the probe.** A single dropped packet recorded as an outage gives you a false RTO. Require N consecutive bad probes before declaring a breach, and N consecutive good before declaring recovery.
- **Forgetting to verify the revert.** The fault should self-reverse (`startInstancesAfterDuration`), but verify it actually did. A drill that leaves the system degraded is worse than no drill.
- **A drill with no postmortem.** The measurement is worthless if it does not become organizational learning with owned action items. The drill is the means; the postmortem is the product.

## 2.10 — What you should be able to do now

- State the four steps of a chaos experiment and why a no-finding experiment is still a success.
- Explain the stop condition as the seatbelt, and why FIS's enforced stop conditions beat a hand-rolled script.
- Assemble a FIS experiment template from its four building blocks (actions, targets, stop conditions, execution role) in JSON and in CDK.
- Write the FIS execution role's trust and permission policies, scoped least-privilege, and explain why the missing-permission error is the most common FIS failure.
- Run the four capstone drills and say what design claim each one tests and commonly disproves.
- Measure a drill's timeline (t0 / t_fault / t_impact / t_recover) into an RTO/RPO with a hysteresis-guarded probe.
- Write a blameless postmortem with a five-whys systemic root cause and owned, dated, tagged action items.

## 2.11 — The exercises that go with this lecture

- **Exercise 1 — FIS AZ failover.** Build the experiment template, wire the stop condition, run the drill, measure the RTO.
- **Exercise 2 — FIS chaos drills (DynamoDB throttle + Lambda concurrency).** Drive the other two required drills with a Python driver that captures the timeline and emits the postmortem skeleton.

Bring the measured timelines and the postmortems to Friday's defense. They are the difference between *claiming* your system survives an AZ outage and *proving* it.
