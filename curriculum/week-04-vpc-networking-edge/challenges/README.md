# Week 4 — Challenges

One harder, open-ended challenge. It ties Lecture 2 (the edge) to the VPC you built in the exercises. Budget ~2–3 hours. There is no single "correct" implementation — you are graded on whether the acceptance criteria are met and demonstrably proven, not on how you got there.

## Index

1. **[Challenge 1 — Edge rate-limiting under load](challenge-01-edge-rate-limit.md)** — put a Route 53 alias in front of an ALB that serves a static "hello" page, deliver it through CloudFront over HTTPS with an ACM-managed certificate, attach an AWS WAF rate-based rule, and **demonstrate the rate limit triggering under load** with CloudWatch evidence and a recovery after the load stops. (~2–3 h)

## How to work the challenge

- This builds on the VPC from the exercises. Deploy the network + endpoints first; the ALB lives in the public subnets of that VPC.
- You need a domain in a Route 53 **public hosted zone** you control. If you don't own one, the challenge ships a fallback that uses the CloudFront default domain (`*.cloudfront.net`) so you can still prove the WAF behavior — you just skip the custom-domain and ACM-validation steps.
- **Remember the two regional gotchas from Lecture 2:** the ACM certificate for CloudFront and the `CLOUDFRONT`-scoped WAF web ACL both must live in `us-east-1`, regardless of where your VPC and ALB are.
- The deliverable is not "it deploys." The deliverable is the **proof**: a status-code histogram from a load tool showing `403`s, the WAF `BlockedRequests` metric going non-zero on your rate rule, and a clean `200` after the window resets.
