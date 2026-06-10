# Week 10 — Challenges

One challenge this week, and it is the one the design review hinges on: swap the EventBridge spine of your order pipeline for **MSK (managed Kafka)** for the *same* workload, then write up exactly what changed — in ordering, replay, throughput, and cost — and defend when each primitive is the right choice.

This is not a "rewrite it in a different SDK" exercise. The interesting part is the *analysis*: Kafka and EventBridge are genuinely different shapes, and forcing the same pipeline through both surfaces the trade-offs the decision table in Lecture 1 only sketches.

| # | File | What you do | Difficulty |
|---|------|-------------|------------|
| 1 | [challenge-01-swap-eventbridge-for-msk.md](./challenge-01-swap-eventbridge-for-msk.md) | Replace EventBridge with an MSK Serverless cluster as the order spine; reproduce fan-out, ordering, replay; write up ordering/replay/throughput/cost deltas with real numbers; defend each primitive. | Hard / open-ended |

## Ground rules

- **MSK Serverless bills per-partition-hour and per-GB, even when idle.** The challenge has a loud teardown step. Run it in one sitting and tear it down the same day. Budget a few dollars, not a few cents.
- Use **IAM auth** for MSK (no SCRAM secret to babysit). Your client connects with the `aws-msk-iam-sasl-signer` library.
- The writeup is the deliverable, not the cluster. A working cluster with no analysis is a fail; a thorough analysis backed by a cluster you stood up and measured is a pass.
- Bring a **number** to every claim. "MSK is cheaper at high throughput" is a guess. "MSK Serverless beats EventBridge at ~X events/s sustained, here is the spreadsheet" is an answer.
