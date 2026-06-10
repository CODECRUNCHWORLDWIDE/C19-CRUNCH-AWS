# Week 1 — The AWS Mental Model, Accounts & Billing

Welcome to **C19 · Crunch AWS**. Week 1 is the week you set the foundation that every other week stands on. By Friday you will own a fresh AWS account with a locked-down root user, an Organization with `dev` / `stage` / `prod` OUs, a Service Control Policy that *proves* it can deny an action before any compute exists, three Budgets that email you before the bill does, and a Cost & Usage Report flowing into S3 and queryable from Athena. You will also have a working AWS CLI with named profiles and `aws sso login` so you never paste a long-lived access key into a terminal again.

We assume you have shipped software before. The C15 (DevOps) graduate is the target: comfortable with Docker, Kubernetes, Terraform, and a Linux shell. You know what a route table is, you have written YAML that a machine read, and you have an opinion about secrets management. If that's you, this week is not "learn the cloud" — it's "learn the AWS *mental model* and the account-level controls that senior engineers wire up on day one and never think about again." We move fast.

The first thing to internalize: **AWS is not 200+ products you need to learn. It is seven service families and a small set of cross-cutting primitives (IAM, the account boundary, the Region, the bill).** Once you can place any new service into a family and reason about its blast radius, IAM surface, and cost shape, the catalog stops being intimidating. This week builds that map and then nails down the two things beginners get wrong and seniors get right from the start: **the account boundary and the bill.**

> A note on cost. Everything in this week fits inside the AWS Free Tier or costs cents. Organizations, SCPs, Budgets, and Cost Explorer are free. The only line items with real (tiny) cost are the S3 bucket holding the Cost & Usage Report and the Athena scans, both measured in fractions of a cent at this scale. We tell you exactly what each step costs as we go.

## Learning objectives

By the end of this week, you will be able to:

- **Place** any AWS service into one of seven families (compute, storage, database, networking & content delivery, security & identity, integration & messaging, management & observability) and reason about its blast radius before reading its docs.
- **Explain** the Region / Availability Zone / edge-location topology and pick a Region on latency, data-residency, service-availability, and cost grounds — not by habit.
- **Draw** the shared responsibility model and state, for any given service, which line of the "responsibility for / responsibility in" split is yours.
- **Create** a fresh AWS account and lock down the root user: hardware or virtual MFA, no access keys, a sealed-credential runbook, and an alternate-contact for billing.
- **Stand up** an AWS Organization with `dev` / `stage` / `prod` Organizational Units and attach a Service Control Policy as a *guardrail*, not a permission grant.
- **Prove** an SCP denies an action by attempting the blocked action from inside the constrained account and reading the `explicit deny` in the error.
- **Configure** AWS Budgets with `$5` / `$25` / `$80` thresholds wired to email notifications, and read Cost Explorer to find what is actually costing money.
- **Deliver** a Cost & Usage Report into S3, register it in Athena, and write SQL that breaks spend down by service and tag.
- **Operate** the AWS CLI v2 fluently with named profiles, `aws configure sso`, and `aws sso login` — no long-lived keys on disk.

## Prerequisites

This week assumes you have completed **C15 · Crunch DevOps** (or have 1+ year shipping Docker + Kubernetes + Terraform) and have **C14**-level Linux fluency. Specifically:

- Comfortable in a terminal — you can `cd`, set environment variables, read a `man` page, pipe `jq` over JSON.
- You have written infrastructure as code at least once (Terraform, Pulumi, or CloudFormation).
- You understand IAM at the "I have copy-pasted a policy" level. We deepen this in Week 2; this week you only need to read a deny.
- You can read and write Git without friction.
- You have a credit/debit card you can attach to a new AWS account. AWS requires one even for Free-Tier usage. We keep your spend under a few cents this week.

You do **not** need prior AWS depth. If you have clicked around the console once, that is plenty. If you have never opened the AWS console, that is fine too — we start from account creation.

## Topics covered

- The history of AWS as a set of primitives (S3 2006, EC2 2006) and why that origin story explains the catalog's shape.
- The seven service families and the "ignore the other 190 until you need them" heuristic.
- Region / AZ / edge-location / Local Zone / Wavelength topology, and how to choose a Region.
- Global vs Regional vs zonal services (IAM and Route 53 are global; most things are Regional; `us-east-1` is special).
- The shared responsibility model — "of the cloud" vs "in the cloud" — applied to S3, EC2, RDS, and Lambda.
- The account as the hard security and billing boundary. AWS account vs Organization vs OU vs SCP.
- Root-user hygiene: MFA, no access keys, sealed-credential runbook, alternate contacts, the IAM Identity Center handoff.
- AWS Organizations: management account, member accounts, OUs, the org tree, `aws:PrincipalOrgID`.
- Service Control Policies: deny-by-guardrail, the `FullAWSAccess` default, why an SCP grants nothing, and how `RequestedRegion` conditions work.
- Free-Tier mechanics (12-month, always-free, trials) and the traps that generate surprise bills.
- AWS Budgets, Cost Explorer, Cost Anomaly Detection, and the Cost & Usage Report (CUR 2.0 via Data Exports).
- Querying the CUR with Athena: partition projection, cost-by-service, cost-by-tag.
- AWS CLI v2: named profiles, `~/.aws/config` vs `~/.aws/credentials`, `aws configure sso`, `aws sso login`, CloudShell.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | History, seven families, Region/AZ/edge topology   |    2h    |    1h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5h      |
| Tuesday   | Shared responsibility; account creation; root MFA  |    2h    |    2h     |     0h     |    0.5h   |   1h     |     0h       |    0h      |     5.5h    |
| Wednesday | Organizations, OUs, SCPs; prove a deny             |    1.5h  |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | Budgets, Cost Explorer, CUR; CLI profiles & SSO    |    1.5h  |    2h     |     0h     |    0.5h   |   1h     |     1.5h     |    0.5h    |     7.5h    |
| Friday    | CUR → S3 → Athena challenge; CLI fluency            |    0h    |    1h     |     1h     |    0.5h   |   1h     |     2h       |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                             |    0h    |    0h     |     0h     |    0h     |   0h     |     3h       |    0h      |     3h      |
| Sunday    | Quiz, cost report, reflection                      |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0h      |     2h      |
| **Total** |                                                    | **7h**   | **8h**    | **2h**     | **3.5h**  | **5h**   | **8h**       | **2h**     | **35.5h**   |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated AWS docs, talks, books, and tools — all current to 2026 |
| [lecture-notes/01-why-aws-has-200-services.md](./lecture-notes/01-why-aws-has-200-services.md) | Why the catalog is so big, the seven service families, Region/AZ/edge topology, the shared responsibility model |
| [lecture-notes/02-account-posture-organizations-scps.md](./lecture-notes/02-account-posture-organizations-scps.md) | The account boundary, Organizations, OUs, SCPs as guardrails, and root-user hygiene |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-root-lockdown-runbook.md](./exercises/exercise-01-root-lockdown-runbook.md) | Create an account, enable root MFA, write the sealed-credential runbook |
| [exercises/exercise-02-org-with-scp-deny-region.tf](./exercises/exercise-02-org-with-scp-deny-region.tf) | OpenTofu: build an Organization with three OUs and an SCP that denies `us-east-1` |
| [exercises/exercise-03-budgets-alerts.ts](./exercises/exercise-03-budgets-alerts.ts) | AWS CDK (TypeScript): three Budgets at `$5`/`$25`/`$80` wired to email |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-cur-to-athena.md](./challenges/challenge-01-cur-to-athena.md) | CUR → S3 → Athena: break spend down by service and tag |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the multi-account org-and-billing foundation |
| [quiz.md](./quiz.md) | 14 questions with an answer key |
| [homework.md](./homework.md) | Six practice problems with a rubric |

## The "prove it" promise

C19 has a recurring rule: **a control you have not tested is a control you do not have.** Every guardrail this week ends with you attempting the thing it is supposed to block and reading the denial. When you write an SCP that denies `us-east-1`, you will run an `aws ec2 run-instances --region us-east-1` and watch it fail with:

```
An error occurred (AccessDenied) when calling the RunInstances operation:
User: arn:aws:sts::111122223333:assumed-role/... is not authorized to perform:
ec2:RunInstances ... with an explicit deny in a service control policy
```

The phrase `with an explicit deny in a service control policy` is the whole point of Wednesday. If you never saw that line, you never proved the guardrail.

## Stretch goals

If you finish the regular work early and want to push further:

- Read the **AWS Well-Architected Framework** Security and Cost Optimization pillars end to end: <https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html>.
- Re-implement Exercise 2 (the Organization + SCP) in **CloudFormation** and diff the experience against OpenTofu. Then again in **CDK**. You now have the same control in all three tools.
- Turn on **Cost Anomaly Detection** with a monitor scoped to your whole account and a `$10` alert threshold. Read what it claims it will catch.
- Wire your three Budgets to an **SNS topic** instead of (or in addition to) email, and subscribe a Slack-incoming-webhook Lambda. You will rebuild this properly in Week 7.
- Write a one-page note for your future self: *what is the difference between an IAM policy, an SCP, a permission boundary, and a resource policy?* You only need the SCP this week; Week 2 needs all four.

## Up next

Continue to **Week 2 — IAM Done Right** once you have pushed your mini-project repo. Week 2 is the single most important week in the course, and it assumes the Organization and the `aws sso login` workflow you build here. Do not skip the proof steps — Week 2's lab stands on this account scaffold.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
