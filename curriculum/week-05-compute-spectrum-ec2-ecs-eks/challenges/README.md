# Week 5 — Challenges

One challenge this week, and it is the spine of the whole week: take the three deployments you built in the exercises and turn them into a **defensible benchmark**. Numbers, not opinions. The mini-project's decision doc is only credible if this table is real.

## Index

1. **[Challenge 1 — The three-way benchmark](challenge-01-three-way-benchmark.md)** — measure cold-start, p50/p99 latency, and per-1M-request cost across ECS Fargate, EKS-on-Spot, and Lambda; produce one table that exposes the real trade-offs. (~2 hours, worth far more than its time-cost.)

## How to work the challenge

- Do **all three exercises first.** The challenge benchmarks the deployments they produce. You cannot benchmark what you did not deploy.
- **Measure honestly.** Warm the warm path; report the cold path separately. Do not bury a 1.2 s Lambda cold start inside a p50 — call it out as its own number, because in a design review someone will ask.
- **Price the parts people forget.** NAT data, ALB LCUs, the EKS control-plane fee, CloudWatch log ingestion. Lecture 1 §6 lists them. A benchmark that prices only compute is the most common review-fail.
- **Same load on all three.** Same request mix, same concurrency, same region, same `hey`/`oha` invocation. If you push 50 concurrent at Fargate and 5 at Lambda, your table is comparing nothing.
- **Tear down the moment you have the numbers.** The EKS control plane bills whether or not you are looking at it.

The deliverable is a Markdown table plus a short written interpretation. The grader re-runs your load generator against your live (or screenshotted) endpoints and checks that your numbers are reproducible within ~30%. The table feeds straight into the mini-project decision doc.
