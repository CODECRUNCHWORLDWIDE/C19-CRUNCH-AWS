# Week 6 — Challenges

The exercises drill the build. **The challenge makes you prove a decision with data.** This week's challenge is a benchmark plus a written decision doc — the kind of artifact a senior reviewer actually reads before approving an `io2` line on the bill.

## Index

1. **[Challenge 1 — Benchmark `gp3` vs `io2` on a synthetic Postgres workload](challenge-01-gp3-vs-io2-benchmark.md)** — provision both volume types, run `fio` and `pgbench` against each, capture IOPS / throughput / p50 / p99 latency, and write up which volume wins for which workload shape and at what cost. (~3 h)

This challenge is the spine of Friday. It is also a rehearsal for the capstone's chaos drill and FinOps weeks: you will be asked, repeatedly, to defend a storage choice with numbers, not vibes. "We used `io2` because it felt fast" does not survive a design review. "We used `gp3` because at 8,000 provisioned IOPS it met our p99 target at 38% of the `io2` cost, and here is the `fio` run" does.

Tear-down discipline: the EC2 instance and especially the `io2` volume provisioned at high IOPS are the most expensive things you touch all week. Run the benchmark, capture the numbers, `cdk destroy` (or terminate + delete the volumes) the **same day**.
