# Week 14 — Challenges

One challenge this week. It is the synthesis of both lectures: it takes the edge tier from Exercise 3, hardens it with WAF and origin failover, *proves* the failover by killing the primary origin while traffic flows, and asks you to write the cost-as-a-feature decision doc that a senior engineer would defend in a design review — the same shape of artifact as Week 11's self-hosted-vs-managed write-up, pointed at the edge instead of inference.

## Index

1. **[Challenge 1 — Edge + WAF + origin failover + the cost decision](challenge-01-edge-waf-origin-failover-cost.md)** — add WAF managed rules and a rate-based rule to the CloudFront distribution, configure origin failover with an origin group, prove failover by killing the primary origin, and write the decision doc that justifies which logic you placed in which edge tier with the per-million-requests numbers. (~2.5–3 h)

## How to approach it

- This is open-ended on purpose. There is more than one defensible edge design; what is graded is whether your choices have *numbers* behind them and whether the failover actually works when you break the origin.
- Bring the artifacts you already built: the Exercise 3 distribution with its CloudFront Function and Lambda@Edge tenant injector, and the FinOps numbers (Savings Plan break-even, per-tier edge cost) from Exercises 1 and 2.
- The deliverable is a working, hardened edge *and* a written decision doc. A failover you didn't prove, or a doc without the per-1M cost numbers, is incomplete.
- Mind the teardown. WAF web ACLs cost money per month while they exist, a CloudFront distribution must be disabled before delete, and Lambda@Edge replicas clear asynchronously. The whole point of the week is that you can reason about edge cost — don't also pay it needlessly.
