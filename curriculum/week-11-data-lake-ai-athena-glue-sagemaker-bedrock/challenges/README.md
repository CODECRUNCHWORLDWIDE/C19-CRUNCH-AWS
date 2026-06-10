# Week 11 — Challenges

One challenge this week. It is the synthesis of both lectures: it takes the SageMaker endpoint from Exercise 3 and puts it head-to-head with a Bedrock Claude Haiku call, from a single Lambda, and asks you to produce the self-hosted-vs-managed decision write-up that a senior engineer would defend in a design review.

## Index

1. **[Challenge 1 — Endpoint vs Bedrock from Lambda](challenge-01-endpoint-vs-bedrock.md)** — invoke both the SageMaker real-time endpoint and a Bedrock Haiku call on the same input from one Lambda, capture cost and latency for each, compute the break-even traffic, and write the decision doc. (~2.5 h)

## How to approach it

- This is open-ended on purpose. There is more than one defensible answer; what is graded is whether your answer has a *number* behind it.
- Bring the artifacts you already built: the Exercise 3 endpoint (redeploy it; do not leave it running all week) and Bedrock model access (enabled Monday).
- The deliverable is a working Lambda *and* a written decision doc. Code without the doc, or the doc without the measured numbers, is incomplete.
- Tear the endpoint down when you finish. The whole point of the challenge is that you can reason about its cost; do not also pay it needlessly.
