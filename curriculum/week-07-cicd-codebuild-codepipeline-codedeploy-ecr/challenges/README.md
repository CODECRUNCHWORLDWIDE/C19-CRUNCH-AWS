# Week 7 — Challenges

The exercises build the AWS-native delivery flow. **The challenge stretches you** by making you rebuild the entire thing the modern way — GitHub Actions federated into AWS with OIDC, no long-lived keys anywhere — and then write the honest comparison a senior engineer is expected to defend in a design review.

## Index

1. **[Challenge 1 — Replicate the delivery flow with GitHub Actions + OIDC, then compare](challenge-01-github-actions-oidc-replication.md)** — rebuild the lint → test → multi-arch build → ECR push → blue/green ECS deploy flow as a GitHub Actions workflow, authenticating into AWS with an OIDC trust relationship scoped to your repo and branch (zero stored AWS keys). Then write a two-approach comparison on security, cost, and operability. (~120–180 min)

Challenges are optional for passing the week. If you do this one, you finish the week able to defend either delivery model on a whiteboard — which is exactly the conversation that comes up in the capstone review and in interviews for any AWS-shop role. The OIDC role and workflow you build here are also the second half of the mini-project deliverable, so doing the challenge is a head start on Friday's mini-project.
