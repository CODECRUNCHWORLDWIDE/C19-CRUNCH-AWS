# Week 13 — Challenges

One challenge this week. It is the synthesis of both lectures: it takes the multi-Region data primitives from Exercise 3 and the multi-Region KMS key from Exercise 2, puts a Route 53 health-checked failover in front of a primary and DR endpoint, and asks you to **fail over for real** and measure the RTO and RPO you actually achieve. The senior skill being tested is the one the whole week builds toward: turning "we have a DR Region" into "we drilled it on 2026-06-12, achieved RTO 4m12s and RPO 0s, and here is the runbook."

## Index

1. **[Challenge 1 — Route 53 failover drill](challenge-01-route53-failover-drill.md)** — wire health-checked failover records over a primary and DR endpoint, break the primary's health check, watch DNS flip with `dig`, confirm the DR Region serves, and record the achieved-vs-target RTO and RPO plus the runbook. (~2.5 h)

## How to approach it

- This is the most important drill in the course before the Week-15 chaos drill. It is open-ended on purpose: there is more than one defensible way to wire the failover, but there is only one acceptable outcome — a *measured* RTO and RPO, not an adjective.
- Bring the artifacts you already built: the multi-Region KMS key (Exercise 2), the DynamoDB Global Table and Aurora Global Database (Exercise 3), and the detective stack watching both Regions (Exercise 1).
- The deliverable is a working failover **and** a written drill report with the two numbers and the runbook. A failover you can't measure, or a report without the numbers, is incomplete.
- Tear down the warm-standby resources when you finish. The whole point of the drill is that you can reason about — and prove — your recovery; do not also pay for an idle second Region all weekend.
- The honest answer matters more than a perfect number. If your measured RPO *missed* the target (e.g. Aurora's ~1.1s against a ≤1s target), say so and explain why — that is the kind of finding a real DR drill exists to surface.
