# Exercise 1 — FIS AZ Failover: Measure Your RTO

> **Estimated time:** ~75 minutes. **Cost:** cents (FIS is priced per action-minute; the capstone it runs against is the real cost — destroy the non-prod stack after).

## Goal

Build an **AWS Fault Injection Service** experiment that simulates the loss of one Availability Zone by stopping that AZ's EKS worker nodes, run it against your deployed capstone with a CloudWatch stop condition as the seatbelt, and **measure the actual recovery time** against your documented 5-minute RTO. The headline outcome: a measured RTO number — not a target — that you bring to Friday's architecture defense.

This is the drill that answers Lecture 1's reliability question "what is your RTO and how do you *know*?" By the end you will know, because you watched it.

## Prerequisites

- AWS CLI v2 configured (`aws sts get-caller-identity` returns your account).
- Your capstone (or a non-prod copy) deployed and reachable at a public HTTPS URL, with EKS managed node groups spread across at least three AZs and their backing EC2 instances **tagged `service=eks-node`**. (If your nodes aren't tagged, add the tag to the node group's launch template and roll the nodes — FIS targets by tag.)
- A load generator to hold steady traffic during the drill.
- Region `us-east-1` assumed; substitute consistently if you use another.

## Acceptance criteria

- [ ] A FIS execution role exists that FIS can assume and that holds `ec2:StopInstances`/`StartInstances` scoped to `service=eks-node`, plus `cloudwatch:DescribeAlarms`.
- [ ] A CloudWatch alarm `capstone-api-5xx-high` exists and is wired as the experiment's **stop condition**.
- [ ] A FIS experiment template targets *running* `service=eks-node` instances in **one** AZ only (filtered), with `startInstancesAfterDuration` set so the fault self-reverses.
- [ ] You run the experiment while probing the API once per second, and record the timeline: t0, t_fault, t_impact, t_recover.
- [ ] You compute `recovery_seconds` and state PASS/REVIEW against your documented RTO.
- [ ] You confirm the SageMaker endpoint is *not* a single-AZ SPOF (or you note it as a finding for the postmortem).

---

## Step 1 — Create the FIS execution role

FIS assumes this role to inject the fault. Create the trust policy and a least-privilege permission policy.

```bash
export REGION=us-east-1
export ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

cat > fis-trust.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "fis.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
JSON

aws iam create-role \
  --role-name fis-experiment-role \
  --assume-role-policy-document file://fis-trust.json

cat > fis-policy.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Ec2NodeFaults",
      "Effect": "Allow",
      "Action": ["ec2:StopInstances", "ec2:StartInstances", "ec2:RebootInstances"],
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": { "StringEquals": { "aws:ResourceTag/service": "eks-node" } }
    },
    {
      "Sid": "Ec2Describe",
      "Effect": "Allow",
      "Action": ["ec2:DescribeInstances"],
      "Resource": "*"
    },
    {
      "Sid": "StopConditionAlarmRead",
      "Effect": "Allow",
      "Action": ["cloudwatch:DescribeAlarms"],
      "Resource": "*"
    }
  ]
}
JSON

aws iam put-role-policy \
  --role-name fis-experiment-role \
  --policy-name az-failover \
  --policy-document file://fis-policy.json

export FIS_ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/fis-experiment-role"
echo "FIS role: ${FIS_ROLE_ARN}"
```

`ec2:DescribeInstances` is unscoped because it is a list/read with no resource-level conditions; the *destructive* `StopInstances` is scoped to the `service=eks-node` tag so a bug in your template can never stop your bastion or a database host.

## Step 2 — Create the stop-condition alarm (the seatbelt)

The experiment must abort if killing an AZ actually breaks the API — i.e. if your multi-AZ failover does *not* work. This alarm is that seatbelt. It watches your API's 5xx rate; if it crosses 5%, FIS stops the experiment and restarts the nodes.

```bash
# Adjust the namespace/metric to match how your capstone publishes API errors.
# This example uses API Gateway's 5XXError metric for the capstone HTTP API.
aws cloudwatch put-metric-alarm \
  --alarm-name capstone-api-5xx-high \
  --alarm-description "Stop FIS experiment if API 5xx rate is too high" \
  --namespace AWS/ApiGateway \
  --metric-name 5XXError \
  --dimensions Name=ApiId,Value=<your-http-api-id> \
  --statistic Average \
  --period 60 \
  --evaluation-periods 1 \
  --threshold 0.05 \
  --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching

export ALARM_ARN="arn:aws:cloudwatch:${REGION}:${ACCOUNT}:alarm:capstone-api-5xx-high"
```

If your API errors are published as a custom metric (e.g. from ADOT), point the alarm at that metric instead. The principle is unchanged: the alarm represents "steady state is broken," and FIS halts the fault the moment it fires.

## Step 3 — Create the experiment template

Write the template JSON. It targets only *running* nodes in `us-east-1a`, stops them, and auto-restarts them after 10 minutes.

```bash
cat > az-failover-template.json <<JSON
{
  "description": "Capstone AZ-failover drill: stop EKS nodes in us-east-1a",
  "roleArn": "${FIS_ROLE_ARN}",
  "stopConditions": [
    { "source": "aws:cloudwatch:alarm", "value": "${ALARM_ARN}" }
  ],
  "targets": {
    "eksNodesAz1a": {
      "resourceType": "aws:ec2:instance",
      "selectionMode": "ALL",
      "resourceTags": { "service": "eks-node" },
      "filters": [
        { "path": "Placement.AvailabilityZone", "values": ["us-east-1a"] },
        { "path": "State.Name", "values": ["running"] }
      ]
    }
  },
  "actions": {
    "stopAz1aNodes": {
      "actionId": "aws:ec2:stop-instances",
      "description": "Stop running EKS nodes in us-east-1a",
      "parameters": { "startInstancesAfterDuration": "PT10M" },
      "targets": { "Instances": "eksNodesAz1a" }
    }
  },
  "tags": { "Name": "capstone-az-failover", "team": "platform", "environment": "nonprod" }
}
JSON

TEMPLATE_ID=$(aws fis create-experiment-template \
  --cli-input-json file://az-failover-template.json \
  --query 'experimentTemplate.id' --output text)
echo "experiment template: ${TEMPLATE_ID}"
```

## Step 4 — Establish steady state, then inject the fault

Start your load generator and a one-per-second probe in two other terminals, then start the experiment.

```bash
# Terminal A: hold steady traffic (k6, hey, or a loop). Example with hey:
#   hey -z 8m -q 100 -m POST -H 'Content-Type: application/json' \
#       -d '{"tenant":"drill","type":"probe"}' https://<your-api>/v1/events

# Terminal B: a simple 1 Hz probe that prints status + latency with a UTC timestamp:
cat > probe.sh <<'SH'
URL="$1"
while true; do
  start=$(date +%s.%N)
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 2 -X POST \
    -H 'Content-Type: application/json' -d '{"tenant":"probe","type":"probe"}' "$URL")
  end=$(date +%s.%N)
  ms=$(echo "($end - $start) * 1000" | bc)
  printf '%s  code=%s  %.0fms\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$code" "$ms"
  sleep 1
done
SH
chmod +x probe.sh
./probe.sh "https://<your-api>/v1/events"   # run in its own terminal, leave it printing

# Terminal C: after ~30s of green probes (steady state), inject the fault:
EXP_ID=$(aws fis start-experiment \
  --experiment-template-id "${TEMPLATE_ID}" \
  --query 'experiment.id' --output text)
echo "experiment running: ${EXP_ID}  (note this time as t_fault)"
```

Note the wall-clock time you started the experiment — that is **t_fault**. Watch Terminal B: the probes will (briefly, if your failover works) go red as `us-east-1a`'s pods reschedule and the ALB drains the dead AZ, then green again. The first sustained red is **t_impact**; the return to sustained green is **t_recover**.

## Step 5 — Read the experiment state and the timeline

```bash
# Poll the experiment to completion (or watch it stop if the seatbelt fired):
while true; do
  STATE=$(aws fis get-experiment --id "${EXP_ID}" --query 'experiment.state.status' --output text)
  echo "experiment state: ${STATE}"
  [ "$STATE" = "completed" ] && break
  [ "$STATE" = "stopped" ]   && { echo "STOP CONDITION FIRED — failover did NOT hold; investigate"; break; }
  [ "$STATE" = "failed" ]    && { aws fis get-experiment --id "${EXP_ID}" --query 'experiment.state.reason'; break; }
  sleep 15
done
```

A `completed` state with no breach in your probe log means the fault was absorbed — strong result. A brief breach that recovered within your RTO is the expected result; record the timeline. A `stopped` state means the seatbelt fired: your AZ failover did *not* work, the 5xx alarm tripped, and FIS aborted — that is a finding (and exactly what the drill is for: you found it in a controlled experiment, not at 3 a.m.).

## Step 6 — Compute the RTO and check the SageMaker SPOF

From your probe log, pick out the four timestamps and compute:

```
recovery_seconds = t_recover - t_fault     # this is your measured RTO
impact_seconds   = t_recover - t_impact    # user-visible outage window
```

Then check whether the recommendation feature stayed up. If you deployed the SageMaker endpoint as a *single instance in one AZ* and that AZ was `us-east-1a`, it was down for the whole drill — a single-AZ SPOF. Confirm:

```bash
aws sagemaker describe-endpoint-config --endpoint-config-name <your-endpoint-config> \
  --query 'ProductionVariants[].{Variant:VariantName,Instances:InitialInstanceCount}'
```

If `InitialInstanceCount` is 1, note it as a postmortem finding: the fix is ≥2 instances so SageMaker spreads them across AZs. This is exactly the kind of SPOF Lecture 1 said a reviewer will catch — better you catch it first.

## Expected output

```
# probe log excerpt
2026-06-10T14:02:18Z  code=200  118ms     <- steady state (t0)
2026-06-10T14:02:20Z  code=200  121ms
2026-06-10T14:02:24Z  code=503  2001ms    <- first breach (t_impact)
2026-06-10T14:02:25Z  code=503  2000ms
...
2026-06-10T14:04:42Z  code=200  144ms     <- recovered (t_recover)

# computed
recovery_seconds = 142   (t_recover 14:04:42 - t_fault 14:02:20)
impact_seconds   = 138
RTO target 300s -> PASS
data_loss: none (DLQ depth flat through the drill)
SageMaker variant InitialInstanceCount=1 -> FINDING: single-AZ SPOF
```

Your exact numbers will differ. The shape: a sub-5-minute recovery if your multi-AZ design works, a measured RTO you can defend, and at least one finding for the postmortem.

## Cleanup (end-of-session)

The experiment auto-restarts the nodes after 10 minutes, so the fault self-reverses. But confirm the nodes are back and tear down the non-prod capstone if you are done for the day:

```bash
# Confirm us-east-1a nodes are running again:
aws ec2 describe-instances \
  --filters "Name=tag:service,Values=eks-node" "Name=availability-zone,Values=us-east-1a" \
  --query 'Reservations[].Instances[].State.Name'

# If you're done drilling for the day, destroy the non-prod stack:
#   npx cdk destroy --all --context environment=nonprod
```

## Inline hints

- *`start-experiment` fails with AccessDenied* — the FIS role is missing a permission. Read the error; it names the action. Add it to `fis-policy.json` and `put-role-policy` again. This is the #1 FIS gotcha.
- *Experiment `completed` but no nodes were stopped* — the target matched zero instances. Check your nodes are tagged `service=eks-node` and that some are actually in `us-east-1a` (`aws ec2 describe-instances ... --query '...AvailabilityZone'`).
- *Probes never went red even though nodes stopped* — congratulations, your failover is transparent; `t_impact` is "none." That is the best possible result. Note it.
- *Stop condition fired immediately* — your alarm was already in ALARM before the experiment (the API was unhealthy at t0). Fix the API, re-establish steady state, then retry.
- *Want a true full-AZ outage, not just compute* — switch the action to the FIS **AZ Availability: Power Interruption** scenario, which also exercises Aurora's AZ failover and the network. Attach the longer IAM action list the scenario doc specifies. This is the version to use for the capstone's real AZ-failover claim.
