# Week 15 — Exercises

Three exercises. The first two are the chaos drill — they produce the measured RTO and the postmortems that the capstone defense rests on. The third is the career pack's readiness gate. Do Exercise 1 before Exercise 2 (Exercise 2 assumes the FIS execution role and one experiment template already exist), and do all three before Friday's oral.

## Index

1. **[Exercise 1 — FIS AZ failover](exercise-01-fis-az-failover.md)** — build an AWS Fault Injection Service experiment template that stops one AZ's worth of EKS nodes (and optionally fails over Aurora), wire a CloudWatch stop condition, run it against your capstone, and measure the recovery time against your documented RTO. (~75 min)
2. **[Exercise 2 — FIS chaos drills: DynamoDB throttle + Lambda concurrency](exercise-02-fis-chaos-drills.py)** — drive the other two required drills with a Python driver that injects the fault, probes the system once per second, computes the timeline (t0 / t_fault / t_impact / t_recover), and emits a pre-filled `POSTMORTEM.md` skeleton. (~90 min)
3. **[Exercise 3 — Cert readiness gate](exercise-03-cert-readiness-gate.py)** — score yourself against the SAP-C02 and DOP-C02 exam domains, identify your two weakest domains, and clear the ≥70% readiness gate. (~60 min)

## Before you start

- **Your capstone is deployed and reachable.** Exercises 1 and 2 inject faults into a *running* system. Run the drills against a non-prod copy of the capstone (`cdk deploy --all` with an `environment=nonprod` context), never against anything with real users.
- **A FIS execution role exists.** Exercise 1 walks you through creating it; do that step first even if you skim the rest. The single most common FIS failure is a missing target-resource permission on this role.
- **AWS CLI v2** configured with a profile that can use FIS, EC2, DynamoDB, Lambda, CloudWatch, and (for Exercise 1's Aurora option) RDS. `aws --version` should report `aws-cli/2.x`.
- **Python 3.12+** with `boto3` for Exercises 2 and 3. A clean virtualenv is fine; `boto3` is the only hard dependency.
- **A load generator** (`k6`, `hey`, `vegeta`, or a simple loop) to hold the system at a steady request rate so the probe has a real steady state to measure against.

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Wire the stop condition first, every time.** Never start a FIS experiment without the CloudWatch-alarm seatbelt. If the alarm does not exist yet, create it before the experiment template.
- Run it. Watch your dashboards *live* while the fault is injected — the point is to *see* the failover happen, not just read the timeline afterward.
- Tear down what costs money: FIS experiments cost cents (per action-minute), but the capstone they run against does not. After the drills, `cdk destroy --all` the non-prod copy so nothing bills overnight. A leaked Aurora cluster or SageMaker endpoint is a $40+ surprise.
- Every exercise ends with a checkable artifact: a measured RTO timeline, a `POSTMORTEM.md`, or a readiness score. If you don't have it, you're not done.

## Cost note

The FIS experiments themselves cost cents (priced per action-minute). The expensive thing is the capstone they run against — Aurora, the SageMaker endpoint, the NAT Gateway, EKS. Run the drills, capture the timelines, then destroy the non-prod stack. **Do not leave the capstone running over the weekend to "save re-deploy time."** The re-deploy is `cdk deploy --all`; the weekend bill is not refundable.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-15` to compare.
