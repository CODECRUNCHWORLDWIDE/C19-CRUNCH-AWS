# Week 8 — Challenges

The exercises drill the mechanics: stand up a cluster, proxy it, fail it over. **The challenge makes you do the thing that earns a senior engineer their salary in a data org: decide, with measured numbers, whether a billing mode saves money or burns it.**

## Index

1. **[Challenge 1 — Aurora Serverless v2 break-even analysis](challenge-01-serverless-v2-break-even.md)** — convert your provisioned Exercise-1 cluster to Aurora Serverless v2 (0.5–8 ACU), re-benchmark cost across three load profiles (steady, burst, idle), pull the *measured* average ACU from CloudWatch, run it through the break-even formula from Lecture 2, and produce the break-even report. (~120–150 min)

The challenge is the analytical core of the week and a direct input to the mini-project's cost-comparison deliverable. It is also the kind of artifact the mid-program design exam expects you to be able to reason about live: a reviewer will ask "would you put this tenant on Serverless v2?" and the correct answer is a number, not a vibe.

Challenges are graded. Skipping the challenge means you cannot complete the mini-project's provisioned-vs-Serverless-v2 comparison, which is worth real points and feeds the capstone's analytical store decision.
