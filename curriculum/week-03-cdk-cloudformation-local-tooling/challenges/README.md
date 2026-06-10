# Week 3 — Challenges

The exercises drill the three IaC tools. **The challenge stretches you** across the full local-to-real loop: emulate, invoke, and then deliberately break a deployed stack to learn what drift looks like.

## Index

1. **[Challenge 1 — LocalStack, `sam local invoke`, and drift](challenge-01-localstack-sam-drift.md)** — run the Exercise 1 Lambda against an emulated S3 bucket with `sam local invoke`, then deploy to real `dev`, mutate a resource in the console, and catch the drift from CloudFormation. (~120 min)

Challenges are optional for passing the week, but this one is the bridge between "I wrote IaC" and "I operate IaC." The local invoke loop is the muscle you use every week after, and the drift drill is the first time you feel the hidden tax of infrastructure-as-code. If you do one optional thing this week, do this.
