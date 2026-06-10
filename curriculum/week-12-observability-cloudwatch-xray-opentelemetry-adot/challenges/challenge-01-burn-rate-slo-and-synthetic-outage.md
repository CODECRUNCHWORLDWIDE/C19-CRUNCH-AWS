# Challenge 1 — A Burn-Rate SLO Alarm, Proven With a Synthetic Outage

> **Estimated time:** 2.5–3 hours. This is the week's synthesis: an SLO with an error budget, a multi-window multi-burn-rate alarm that pages fast and tickets slow, and a deliberately-broken service that proves the alarm fires at the right moment and clears on recovery. It is the exact observability spine the capstone requires.

## The problem

You have an instrumented HTTP API (the API-Gateway-fronted `recommend` Lambda from Exercise 2 and the mini-project). Your job: declare a **99.9% availability SLO** on it, build a **multi-window, multi-burn-rate alarm** the way the Google SRE workbook describes, route fast burns to a "page" channel and slow burns to a "ticket" channel, then **fire a controlled synthetic outage** and prove — with timestamps — that the fast-burn alarm pages within minutes and clears within minutes of recovery.

The senior skill being tested is the one a single static threshold cannot demonstrate: paging *immediately* for a fast burn (an outage emptying the budget in hours) while only *ticketing* for a slow burn (a low-grade error rate that would take weeks to matter). If your alarm pages at 3 a.m. for a 90-second blip, or stays red for an hour after the incident recovered, your windows are wrong — and the synthetic outage is how you find out.

## What you build

1. An **API with a clean SLI**: `good = requests that returned 2xx/3xx`, `total = all requests`, both available as CloudWatch metrics (API Gateway's `Count` and `5XXError` give you this directly).
2. A **multi-window burn-rate alarm set** in CDK or OpenTofu:
   - Fast burn: burn rate **14.4** over a 1-hour long window AND a 5-minute short window → **page** topic.
   - Medium burn: burn rate **6** over 6-hour AND 30-minute windows → **page** topic.
   - Slow burn: burn rate **3** over 1-day AND 2-hour windows → **ticket** topic.
   Each pair is two child alarms AND-ed by a composite alarm. The threshold for burn rate `B` is `B × error_budget = B × 0.001`.
3. Two **SNS topics** — `slo-page` and `slo-ticket` — subscribed to whatever you can observe (email is fine; a Slack webhook via Chatbot is nicer).
4. A **synthetic outage mechanism**: an environment flag (e.g. `FAIL_RATE`) that makes the Lambda return 5xx for a controlled fraction of requests, plus a small load driver so there is enough traffic for the ratios to be meaningful.
5. A written **`SLO.md`** with the SLO definition, the error-budget arithmetic, the alarm table, and the *measured* detection and recovery-confirmation times from your outage.

## Starter: the fast-burn alarm in CDK

The full pattern is in Lecture 2 §2.6. Here is the fast-burn pair; replicate it for the medium and slow rows with the windows and thresholds from the table.

```typescript
import { Duration } from 'aws-cdk-lib';
import * as cw from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as sns from 'aws-cdk-lib/aws-sns';

const pageTopic = new sns.Topic(this, 'SloPage', { topicName: 'slo-page' });
const ticketTopic = new sns.Topic(this, 'SloTicket', { topicName: 'slo-ticket' });

const total = new cw.Metric({ namespace: 'AWS/ApiGateway', metricName: 'Count',
  dimensionsMap: { ApiName: 'recommend-api' }, statistic: 'Sum' });
const errors = new cw.Metric({ namespace: 'AWS/ApiGateway', metricName: '5XXError',
  dimensionsMap: { ApiName: 'recommend-api' }, statistic: 'Sum' });

const ERROR_BUDGET = 0.001;             // 99.9% SLO
const FAST_BURN = 14.4;
const threshold = FAST_BURN * ERROR_BUDGET;   // 0.0144

function burnRatio(scope: Construct, id: string, window: Duration): cw.MathExpression {
  return new cw.MathExpression({
    expression: 'e / t',
    usingMetrics: {
      e: errors.with({ period: window }),
      t: total.with({ period: window }),
    },
    period: window,
    label: `burn-${id}`,
  });
}

const fastLong = new cw.Alarm(this, 'FastBurnLong', {
  metric: burnRatio(this, 'long', Duration.hours(1)),
  threshold, evaluationPeriods: 1,
  comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
  treatMissingData: cw.TreatMissingData.NOT_BREACHING,
});
const fastShort = new cw.Alarm(this, 'FastBurnShort', {
  metric: burnRatio(this, 'short', Duration.minutes(5)),
  threshold, evaluationPeriods: 1,
  comparisonOperator: cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
  treatMissingData: cw.TreatMissingData.NOT_BREACHING,
});

const fastBurnPage = new cw.CompositeAlarm(this, 'FastBurnPage', {
  compositeAlarmName: 'recommend-slo-fast-burn',
  alarmRule: cw.AlarmRule.allOf(
    cw.AlarmRule.fromAlarm(fastLong, cw.AlarmState.ALARM),
    cw.AlarmRule.fromAlarm(fastShort, cw.AlarmState.ALARM),
  ),
});
fastBurnPage.addAlarmAction(new cwActions.SnsAction(pageTopic));
```

The long window confirms the burn is sustained (not a blip); the short window makes the composite *clear fast* once the burn stops (so you're not paged about a recovered incident). Both AND-ed: fire when sustained, clear when recovered.

## The synthetic outage and the measurement

Drive steady traffic with the canary plus a small generator, then inject failure and time the alarm.

```bash
# 1. Baseline traffic so the ratios have a denominator. Keep this running in a loop.
while true; do curl -s -o /dev/null "https://<api-id>.execute-api.us-east-1.amazonaws.com/recommend?path=sagemaker"; sleep 1; done &

# 2. Inject the outage and STAMP THE TIME.
echo "INJECT at $(date -u +%T)"
aws lambda update-function-configuration --function-name recommend \
  --environment "Variables={FAIL_RATE=0.8}"

# 3. Poll the composite alarm until it pages, and stamp the time.
while [ "$(aws cloudwatch describe-alarms --alarm-names recommend-slo-fast-burn \
        --query 'CompositeAlarms[0].StateValue' --output text)" != "ALARM" ]; do sleep 15; done
echo "PAGED at $(date -u +%T)"

# 4. Heal the service and STAMP the time.
echo "HEAL at $(date -u +%T)"
aws lambda update-function-configuration --function-name recommend \
  --environment "Variables={FAIL_RATE=0.0}"

# 5. Poll until the alarm clears, and stamp the time.
while [ "$(aws cloudwatch describe-alarms --alarm-names recommend-slo-fast-burn \
        --query 'CompositeAlarms[0].StateValue' --output text)" != "OK" ]; do sleep 15; done
echo "CLEARED at $(date -u +%T)"
```

**Detection time** = `PAGED − INJECT`. **Recovery-confirmation time** = `CLEARED − HEAL`. For a well-tuned fast-burn alarm against a hard 80%-failure outage, expect detection in single-digit minutes and clearing within a few minutes of healing. If detection takes 30+ minutes, your short window is too long or your `M out of N` too strict; if clearing takes ~an hour, you forgot the short window and only the long window is gating.

## Acceptance criteria

- [ ] A 99.9% SLO declared with a clear SLI definition (what counts as a "good" request).
- [ ] A multi-window, multi-burn-rate alarm set with at least the **14.4 / 6 / 3** rows, each a composite of a long-window and short-window child alarm.
- [ ] Fast/medium burns route to a **page** topic; slow burns route to a **ticket** topic. (Two distinct SNS topics.)
- [ ] `treatMissingData` chosen on purpose for each alarm and justified in `SLO.md`.
- [ ] A synthetic outage fired, with **measured detection time and recovery-confirmation time** recorded with timestamps.
- [ ] A screenshot or CLI capture of the composite alarm transitioning `OK → ALARM → OK`.
- [ ] An `SLO.md` containing: the SLO/SLI definition, the error budget in failed-requests for a stated request volume, the burn-rate threshold arithmetic (`B × 0.001`), the alarm table, and the two measured times with a one-paragraph interpretation.
- [ ] Everything torn down after capture; no orphaned canary, Lambda, or alarm billing.

## Stretch

- Add the **6h / 1d** and **3d / 6h** slow rows fully and route them to `slo-ticket`, then run a *slow* outage (`FAIL_RATE=0.02` sustained) and show the slow-burn alarm opens a ticket *without* paging — proving the page-vs-ticket asymmetry.
- Turn on **CloudWatch Application Signals**, let it auto-discover the service and generate its own SLO + burn-rate alarm, and compare its alarm to your hand-built one in `SLO.md`. Which would you ship, and why?
- Propagate **trace context across the EventBridge boundary** so the trace for a failed request spans API Gateway → Lambda → EventBridge → the downstream consumer, and link the trace from the alarm notification.
- Add a second exporter to your ADOT collector that also ships to **Amazon Managed Prometheus**, write the burn-rate as a PromQL recording rule, and note how much shorter it is than the CloudWatch metric-math version.

## What "good" looks like

A strong `SLO.md` reads like a real reliability artifact: it states the SLO and the budget in concrete failed-requests, shows the `B × 0.001` arithmetic for each burn rate, explains *why two windows per row*, and reports the measured detection/recovery times with an honest interpretation ("detection took 4 minutes, dominated by the 5-minute short window; recovery cleared in 3 minutes because the short window resets fast"). A weak submission has alarms that were never fired, or an `SLO.md` that says "we alert on errors" with no budget, no burn rate, and no measured proof. The synthetic outage is non-negotiable: an unproven alarm is the thing this challenge exists to eliminate.
