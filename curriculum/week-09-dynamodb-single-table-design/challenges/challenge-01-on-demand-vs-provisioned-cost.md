# Challenge 1 — On-Demand vs Provisioned-with-Autoscaling: Measure the Cost Delta and Recommend Per Profile

> **Estimated time:** 2–3 hours. This is the FinOps muscle the whole course keeps exercising. The deliverable is a one-page cost report with a defensible recommendation per load profile — exactly what you would put in a design-review doc.

You have a single table serving a multi-tenant SaaS. Your finance partner asks the question every senior engineer eventually answers: *"Are we on the right DynamoDB billing mode, and what would the other mode cost?"* Your job is to answer it with numbers, not vibes. You will switch the table from on-demand to provisioned-with-autoscaling, model three load profiles — steady-state, burst, and idle — compute the cost of each profile under each mode, and recommend the right mode per profile.

## What "done" looks like

A file `cost-report.md` containing:

1. A table of the three load profiles with their assumed traffic shape.
2. The monthly cost of each profile under **on-demand** and under **provisioned-with-autoscaling** (and a bonus row for **provisioned + reserved capacity**).
3. A one-sentence recommendation per profile, with the break-even reasoning.
4. The IaC diff that switches the table's billing mode, in CDK (primary) and one of CloudFormation/OpenTofu.

## Step 1 — The three load profiles

Model these. The numbers are deliberately concrete so your math is checkable; substitute your mini-project's real shape if you have measured it.

| Profile | Shape | Sustained | Peak |
|---------|-------|-----------|------|
| **Steady-state** | Constant business-hours-and-overnight load | 500 WCU + 1,500 RCU, 24/7 | same |
| **Burst** | Quiet most of the day, one 1-hour spike | ~20 WCU/RCU baseline | 5,000 WCU + 5,000 RCU for 1h/day |
| **Idle** | Dev/staging table, near-zero traffic | < 5 WCU/RCU, sporadic | same |

## Step 2 — The capacity-unit cost math

Use the 2026 us-east-1 list prices (re-check at <https://aws.amazon.com/dynamodb/pricing/> — they move, and the report must cite the date you pulled them):

- **On-demand:** ~$1.25 per million WCU, ~$0.25 per million RCU (eventually consistent; strongly consistent reads are 2× the RCU count).
- **Provisioned:** ~$0.00065 per WCU-hour, ~$0.00013 per RCU-hour. 730 hours/month.
- **Reserved capacity:** roughly 50–75% off provisioned for a 1- or 3-year commit on a steady baseline.

Worked example for steady-state WCU (do the RCU and the other profiles yourself):

```
Steady-state, 500 WCU 24/7:
  Provisioned:  500 WCU × $0.00065/WCU-hr × 730 hr  = $237.25 / month
  On-demand:    500 writes/s × 3600 s × 730 hr × $1.25 / 1e6
                = 500 × 3600 × 730 = 1.314e9 WCU/month
                × $1.25 / 1e6  = $1,642.50 / month
  -> Provisioned wins ~6.9×. With reserved capacity, ~15×.
```

Note the unit difference that trips everyone up: provisioned bills *capacity-hours* (you pay for the reservation whether or not you use it); on-demand bills *consumed request-units* (you pay only for actual requests). Provisioned wins when utilization is high; on-demand wins when it is low or spiky.

## Step 3 — Compute all three profiles, both modes

Build the full table. Show your arithmetic. The burst profile is the interesting one:

- **On-demand burst:** you pay only for the spike hour plus the trickle. The spike: `5000 × 3600 × 30 days × $1.25 / 1e6 ≈ $675/mo` (WCU). On-demand absorbs the spike with zero throttling and zero capacity planning.
- **Provisioned burst:** you must either provision for the peak (5,000 WCU × $0.00065 × 730 ≈ **$2,372/mo**, of which ~96% is wasted because the peak is 1h/day), *or* rely on autoscaling — which **lags spiky load**. Application Auto Scaling reacts on CloudWatch alarms over multi-minute windows; a sudden 250× spike will throttle during the ramp before capacity catches up. Quantify the throttle window and call it out.

Your filled table should look like:

| Profile | On-demand | Provisioned (autoscaling) | Provisioned + reserved | Winner |
|---------|-----------|---------------------------|------------------------|--------|
| Steady-state | ~$1,970/mo | ~$295/mo | ~$120/mo | Provisioned (+reserved) |
| Burst | ~$700/mo | ~$2,400/mo (or throttles) | n/a | On-demand |
| Idle | ~$0.50/mo | ~$2.40/mo floor | n/a | On-demand |

(Combine the WCU and RCU figures; the cells above are illustrative totals — produce your own with the real arithmetic shown.)

## Step 4 — The recommendation

Write one sentence per profile. The expected shape of the answer:

- **Steady-state → provisioned with autoscaling, then reserved capacity on the proven floor.** High, predictable utilization is exactly what provisioned is priced for; reserved capacity on the baseline turns the ~7× win into ~15×.
- **Burst → on-demand.** The spike is too sharp for autoscaling to track without throttling, and provisioning for the peak wastes 96% of the capacity. On-demand wins on both cost and reliability.
- **Idle → on-demand.** Provisioned bills a floor even at zero traffic; on-demand scales to ~$0. For dev/staging tables, on-demand is the no-brainer.

The senior conclusion, which the report must state: **the right answer is rarely "one mode forever."** Start on-demand while learning the traffic shape; move to provisioned-with-autoscaling once the baseline is steady and known; layer reserved capacity on the proven floor. You can switch modes once per 24 hours, so this is a cheap, reversible operational decision — make it with data.

## Step 5 — The IaC switch

Show the diff that flips the table. CDK (primary):

```typescript
// Before (on-demand):
billing: Billing.onDemand(),

// After (provisioned with autoscaling, 70% target utilization):
billing: Billing.provisioned({
  readCapacity: Capacity.autoscaled({ minCapacity: 5, maxCapacity: 4000, targetUtilizationPercent: 70 }),
  writeCapacity: Capacity.autoscaled({ minCapacity: 5, maxCapacity: 4000, targetUtilizationPercent: 70 }),
}),
```

OpenTofu (the autoscaling target + policy that CDK generates for you):

```hcl
resource "aws_dynamodb_table" "saas" {
  name         = "saas-single-table"
  billing_mode = "PROVISIONED"
  read_capacity  = 5      # autoscaling floor
  write_capacity = 5
  # ... keys as before ...
}

resource "aws_appautoscaling_target" "write" {
  max_capacity       = 4000
  min_capacity       = 5
  resource_id        = "table/${aws_dynamodb_table.saas.name}"
  scalable_dimension = "dynamodb:table:WriteCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "write" {
  name               = "saas-write-target-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.write.resource_id
  scalable_dimension = aws_appautoscaling_target.write.scalable_dimension
  service_namespace  = aws_appautoscaling_target.write.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = 70.0
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBWriteCapacityUtilization"
    }
  }
}
```

## Acceptance criteria

- [ ] `cost-report.md` contains the three-profile table with on-demand, provisioned-autoscaling, and provisioned+reserved columns, all with arithmetic shown.
- [ ] Every dollar figure cites the pricing-page date it was pulled.
- [ ] The burst row explicitly addresses the autoscaling-lag/throttle risk, not just the cost.
- [ ] One-sentence recommendation per profile, each with a break-even reason.
- [ ] The report states the "start on-demand → provisioned → reserved" lifecycle conclusion.
- [ ] The IaC diff that switches modes is included for CDK plus one of CloudFormation/OpenTofu, and it actually deploys (`cdk diff` shows only the billing change).

## Going further

- Pull a real **Cost & Usage Report** for a table you ran the exercises against and reconcile your model against the actual line items.
- Model the cost of **Global Tables** for the steady-state profile (writes billed in every region) and decide whether multi-region DR is worth it at your traffic.
- Estimate where **reserved capacity** breaks even versus the 1-year commitment risk if your traffic might drop.
