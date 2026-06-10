# Week 15 — Capstone Defense, Chaos Drill & Career Pack

Welcome to the last week of **C19 · Crunch AWS**. You do not learn a new AWS service this week. You ship, you break it on purpose, and you defend it.

Everything you have built since Week 1 — the multi-account Organization with SCPs, the IAM Identity Center and permission boundaries, the production VPC with endpoints instead of three NAT gateways, the EKS-plus-Fargate-plus-Lambda compute hybrid, the DynamoDB single-table design, the EventBridge spine with SQS DLQs and Step Functions Express, the Aurora analytical cluster, the S3 + Glue + Athena lake, the SageMaker endpoint and Bedrock comparison, the OpenTelemetry tracing through X-Ray, the GuardDuty/Security Hub/Macie/Inspector baseline, the multi-region DR with DynamoDB Global Tables and Aurora cross-region replicas and Route 53 health-checked failover, and the FinOps controls — gets assembled into one running system: the **Event-Driven SaaS Backbone**, multi-AZ and cross-region, in your own AWS account, deployable from `cdk deploy --all` and destroyable with `cdk destroy --all`. Then you defend it.

"Defend it" is not a metaphor. This week you run a real architecture review: you stand in front of two peer reviewers and one lead reviewer, you walk a single request through the whole system, and you answer the questions a senior reviewer asks when they are deciding whether to trust your design in production. You run a **chaos drill** using **AWS Fault Injection Service (FIS)** — AZ failover, DynamoDB throttle, Lambda concurrency exhaustion, and a bonus drill of your choice — and you write the blameless, five-whys postmortem a real incident review would accept. You record the 10-minute public walkthrough video. And you do the **career pack**: a SAP-C02 / DOP-C02 cert-readiness self-assessment, a system-design interview drill in both the AWS-shop (Well-Architected) and FAANG variants, a portfolio-grade README, and a one-page **cost-defense** memo that prices your capstone honestly and names the three optimizations you would make first.

The week has a rhythm: integrate and harden early, prove the SLOs with load and the FIS chaos drill mid-week, deliver and defend at the end, then polish the career pack. If your Week 14 mini-project did not tear down cleanly with `cdk destroy --all`, fix that first — the grader runs `destroy` against your live account, and a leaked Aurora cluster or an orphaned SageMaker endpoint is the difference between a pass and a $200 surprise.

This is the week the whole course has been building toward. Treat it like a release.

## Learning objectives

By the end of this week, you will be able to:

- **Integrate** every prior-week artifact into one multi-AZ, cross-region system that deploys from a single `cdk deploy --all` and tears down with one `cdk destroy --all`, with zero billing tail.
- **Run** a structured chaos drill with **AWS Fault Injection Service** — an AZ-failure experiment, a DynamoDB throttle, and a Lambda concurrency-exhaustion experiment — using FIS experiment templates, stop conditions wired to CloudWatch alarms, and the AZ Availability Power experiment for `disrupt`-style AZ outage simulation.
- **Measure** the blast radius and recovery time of each fault empirically, reading the timeline off your own dashboards rather than guessing, and proving (or disproving) your documented RTO/RPO targets.
- **Write** a blameless postmortem with a five-whys root cause, a correct timeline, and action items that each have an owner, a date, and an accept/mitigate-now/mitigate-later tag.
- **Defend** a production architecture in a 30-minute live oral and answer the standard senior-reviewer questions about blast radius, single points of failure, data-loss windows, the "what pages you at 3 a.m." walk, and the cost-per-request math — without flinching.
- **Self-assess** your readiness against the SAP-C02 and DOP-C02 exam domains, identify your two weakest domains, and write a study plan keyed to the weeks that cover them.
- **Run** a system-design interview in both the Well-Architected (AWS-shop) framing across the five pillars and the FAANG-shop distributed-systems framing, and know which questions each interviewer is really asking.
- **Write** a one-page cost-defense memo that ties the running capstone to a real weekly dollar figure from a tagged Cost & Usage Report breakdown, and names the three optimizations you would commit first.

## Prerequisites

This week assumes you have completed Weeks 1–14 of C19 and that those mini-projects produced working, version-controlled CDK. Specifically, you need:

- An AWS account (or the cross-region pair) with billing enabled, Budgets armed at $5/$25/$80, and cost anomaly detection on. (Week 1.)
- The CDK monorepo (TypeScript primary, one stack in Python) accumulating the capstone stacks since Week 13, deploying with `cdk deploy --all` and destroying with `cdk destroy --all`. (Week 3 onward.)
- GitHub Actions CI with OIDC federation into AWS so deploys carry no long-lived keys. (Week 7.)
- The capstone's required architecture from `SYLLABUS.md`: CloudFront + WAF edge, API Gateway HTTP API + Lambda and ALB + EKS behind it, EventBridge spine with SQS DLQs and Step Functions Express, DynamoDB single-table with Streams, Aurora Postgres (multi-AZ + cross-region read replica), the S3/Glue/Athena lake, the SageMaker endpoint + Bedrock comparison, Cognito + IAM Identity Center identity, OpenTelemetry/ADOT observability with a 99.9% SLO burn-rate alarm, the GuardDuty/Security Hub/Macie/Inspector security baseline, and the DynamoDB Global Tables + Aurora cross-region + Route 53 failover DR posture. (Weeks 12–14.)
- A runbook scaffold in `/runbook` and CloudWatch dashboards-as-code in the CDK. (Weeks 12–14.)

If any of those is missing or broken, this week will expose it. That is the point.

You also need **FIS configured**: the FIS service-linked role or an execution role that FIS can assume with the actions for the experiments you run (`fis:*` on your experiment templates, plus the targeted-resource actions FIS needs — `ec2:RebootInstances`, `autoscaling:*` for ASG node faults, the AZ Availability Power action, etc.). The Monday lecture and Exercise 2 walk the exact role.

## Topics covered

- **The capstone defense.** How a real architecture review runs: the agenda, the artifacts a reviewer expects in front of them, the question set, and the failure modes of the *reviewer* as well as the reviewed. The senior-reviewer questions: blast radius, the single points of failure, the data-loss windows, the "what pages you at 3 a.m." walk, and the cost-per-request math.
- **Chaos engineering on AWS with FIS.** Fault Injection Service experiment templates, actions, targets, stop conditions wired to CloudWatch alarms, and the IAM model. The four capstone drills: **AZ failover** (kill one AZ's EKS nodes and Aurora writer), **DynamoDB throttle** (force a hot partition, watch the degrade and the mitigation), **Lambda concurrency exhaustion** (saturate reserved concurrency and trace the back-pressure into SQS and the DLQ), and a **bonus drill** (NAT saturation, CloudFront origin failure, or KMS throttle).
- **Postmortem authorship.** Blameless framing, five-whys root cause, the timeline, and action items with owners, dates, and a mitigation tag. Why "human error" is never a root cause.
- **The cohort architectural review.** Defending the capstone in a 30-minute oral with two peer reviewers and one lead reviewer; reviewing a peer's capstone with the same question set.
- **Cert-prep mapping.** The SAP-C02 (Solutions Architect Professional) and DOP-C02 (DevOps Engineer Professional) blueprints: domain weighting, the scenario-question style, and a per-domain readiness self-assessment keyed to the weeks that cover each domain.
- **System-design interview drills.** The AWS-shop variant (explicit Well-Architected framing across the five pillars) and the FAANG-shop variant (generic distributed-systems design with AWS as one allowed substrate). What each interviewer is really probing for.
- **The cost-defense memo.** A tagged Cost & Usage Report breakdown of one week of capstone operation, the per-request cost math, and the three first-payback optimizations (Graviton, a Savings Plan, an idle-endpoint kill, a NAT-to-VPC-endpoint move).
- **Portfolio polish.** The public capstone repo: diagrams, runbook, dashboards-as-code, postmortem, and the 10-minute walkthrough video that a hiring manager can watch and a peer can reproduce.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract; the capstone deserves whatever it takes.

| Day       | Focus                                                          | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Final integration; the architecture-review playbook; FIS model |    2h    |    0.5h   |     0h     |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Tuesday   | Load test; AZ-failover FIS drill (Exercise 1 + 2)              |    0h    |    2.5h   |     1h     |    0.5h   |   1h     |     1h       |    0h      |     6h      |
| Wednesday | DynamoDB throttle + Lambda concurrency drills; postmortem      |    1h    |    2.5h   |     1h     |    0.5h   |   0.5h   |     1.5h     |    0h      |     7h      |
| Thursday  | The cost-defense memo; cert map; the readiness gate (Ex. 3)    |    1h    |    1.5h   |     0h     |    0.5h   |   1h     |     1.5h     |    0.5h    |     6h      |
| Friday    | Record the video; deliver the live architecture defense        |    0h    |    0h     |     1.5h   |    0.5h   |   0h     |     2.5h     |    0.5h    |     5h      |
| Saturday  | Mock interview (both variants); portfolio polish; teardown     |    0h    |    0h     |     0h     |    0h     |   1h     |     2h       |    0.5h    |     3.5h    |
| Sunday    | Quiz, retrospective, course wrap                               |    0h    |    0h     |     0h     |    1h     |   0.5h   |     0.5h     |    0h      |     2h      |
| **Total** |                                                                | **4h**   | **7h**    | **4.5h**   | **4h**    | **5h**   | **11h**      | **2.5h**   | **38h**     |

*(The total runs slightly over 36h on purpose — the capstone is the credential the whole course was building toward. Cut self-study before you cut the defense or the chaos drill.)*

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | FIS docs, the SAP/DOP exam blueprints, postmortem and architecture-review templates, interview prep, current to 2026 |
| [lecture-notes/01-defending-the-capstone-the-review-and-the-questions.md](./lecture-notes/01-defending-the-capstone-the-review-and-the-questions.md) | How a real architecture review runs; the senior-reviewer question set; the cost-per-request math you must have ready |
| [lecture-notes/02-chaos-engineering-with-fis-and-the-blameless-postmortem.md](./lecture-notes/02-chaos-engineering-with-fis-and-the-blameless-postmortem.md) | AWS Fault Injection Service: templates, actions, stop conditions, the four capstone drills, and how to write the postmortem |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-fis-az-failover.md](./exercises/exercise-01-fis-az-failover.md) | Build a FIS AZ-failure experiment with a CloudWatch stop condition; kill one AZ; measure recovery against your RTO |
| [exercises/exercise-02-fis-chaos-drills.py](./exercises/exercise-02-fis-chaos-drills.py) | Drive the DynamoDB-throttle and Lambda-concurrency drills, capture the timeline, emit the postmortem skeleton |
| [exercises/exercise-03-cert-readiness-gate.py](./exercises/exercise-03-cert-readiness-gate.py) | Score yourself against the SAP-C02 / DOP-C02 domains and clear the readiness gate |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-defend-the-capstone-live.md](./challenges/challenge-01-defend-the-capstone-live.md) | Deliver the Event-Driven SaaS Backbone live, end to end, and survive the 30-minute oral |
| [mini-project/README.md](./mini-project/README.md) | The full capstone integration, defense, and delivery brief — the course's terminal deliverable |
| [quiz.md](./quiz.md) | 13 questions with an answer key |
| [homework.md](./homework.md) | The week's deliverables with a rubric |

## The "it runs on demand" promise

C19 has one recurring marker, and Week 15 is where it cashes out:

```
cdk destroy --all · 0 stacks remaining · 0 resources · no billing tail
```

The grader will clone your repo, run `cdk deploy --all`, hit your system, run the FIS chaos drill against it, read your dashboards, then run `cdk destroy --all` and confirm zero resources remain and zero billing tail. If `deploy` and `destroy` are not both clean and idempotent, the capstone does not pass — regardless of how good the architecture diagram looks. A system you cannot stand up and tear down on demand is not a system you operate; it is a system you are afraid of. The chaos drill is the same promise in reverse: a fault you can inject and recover from on demand is a fault you understand.

## Stretch goals

If you finish the regular work early and want to push further:

- Run **all four** chaos drills (the three required plus the bonus) and put all four postmortems in the repo. You only have to execute three for the capstone; four makes your postmortem section materially stronger in a portfolio.
- Turn the FIS experiments into a **scheduled GameDay**: an EventBridge-scheduled FIS experiment that runs the AZ-failover drill weekly against a non-prod copy and posts the recovery time to a CloudWatch dashboard. Chaos as a continuous practice, not a one-off.
- Make the Aurora cross-region replica into a true **warm-standby** failover (promote it under FIS), and re-measure RTO/RPO. Document whether the lower RTO is worth the standing cost.
- Write the **exit plan** as a stretch: price what it would cost in engineer-weeks and dollars to move this workload off AWS to self-hosted Kafka + Trino + Iceberg + vLLM on EKS, and put a confidence interval on each estimate.
- Read one published post-incident review from a company that runs on AWS (the AWS Builders' Library, or the Netflix/Stripe/Figma engineering blogs) and write a one-page note on what they asked that you did not.

## Up next

There is no Week 16. After you push the capstone, clear the readiness gate, and survive the oral, you are done with C19. The intended next track is **C22 · Crunch Mesh** — take the EKS-plus-event-driven backbone you just built and grow it into a real multi-region active-active distributed system with consensus, service mesh, sagas, and idempotency at scale. **C18 · Crunch GCP** is the sibling track; take both and you can defend a multi-cloud architecture without flinching. Read the [Crunch Labs Charter](../../CHARTER.md) for the full pathway.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
