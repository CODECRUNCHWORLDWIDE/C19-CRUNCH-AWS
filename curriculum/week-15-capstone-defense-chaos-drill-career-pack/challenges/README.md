# Week 15 — Challenges

One challenge this week, and it is the one the whole course was for: deliver the **Event-Driven SaaS Backbone** live and survive the 30-minute oral defense. It synthesizes both lectures — the architecture-review playbook and the chaos-drill results — and every prior week's artifact.

## Index

1. **[Challenge 1 — Defend the capstone live](challenge-01-defend-the-capstone-live.md)** — deploy the capstone from `cdk deploy --all`, trace a single request through it end to end, present your three chaos-drill postmortems with measured RTO/RPO, defend the cost, and answer the senior-reviewer question set in a 30-minute oral with two peer reviewers and one lead reviewer. Then review a peer's capstone with the same question set. (~3 h including the peer review)

## How to approach it

- This is open-ended on purpose. There is no single correct architecture; what is graded is whether your design decisions are *defensible with a number*, and whether your failure modes are *measured*, not hypothesized.
- Bring the artifacts you already built this week: the measured AZ-failover RTO (Exercise 1), the DynamoDB-throttle and Lambda-concurrency postmortems (Exercise 2), and the four cost numbers (Lecture 1 §1.6, and the homework cost-defense memo).
- The deliverable is a *live* defense plus a *written* peer-review of one cohort member. The oral without the peer review, or the peer review without the live defense, is incomplete.
- Tear the system down when you finish: `cdk destroy --all`, then prove zero resources remain and zero billing tail. The "it runs on demand" promise cuts both ways — a system you cannot destroy cleanly fails the capstone regardless of how the oral went.
