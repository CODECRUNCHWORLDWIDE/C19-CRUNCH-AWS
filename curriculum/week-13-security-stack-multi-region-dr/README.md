# Week 13 — The Security Stack & Multi-Region DR (Capstone build begins)

Welcome to the week the course has been pointing at since Week 1. By Friday you will have a **security baseline** turned on across the account — GuardDuty detecting threats from VPC Flow Logs, DNS, and CloudTrail; Security Hub aggregating posture; Macie scanning the data-lake bucket for PII; Inspector scanning your EKS and ECR — with every Critical and High finding triaged. In parallel you will have a **multi-region disaster-recovery footprint**: DynamoDB Global Tables and an Aurora Global Database replicating into a second Region, S3 Cross-Region Replication on the lake bucket, KMS multi-region keys so the encrypted data is *readable* on the other side, and a Route 53 health-checked failover you can trigger end-to-end. And you will have run that failover for real, with a stopwatch, and written down an actual RTO and RPO number.

This is Phase 4's pivot week, and it is two disciplines in a trench coat. The first half is **security**: KMS done properly (CMK vs AWS-managed, key policies vs grants, automatic rotation, multi-region keys, envelope encryption), Secrets Manager vs Parameter Store, and the detection-and-posture stack (GuardDuty, Security Hub, Macie, Inspector) plus the network/edge controls (Network Firewall, WAF managed rule groups, Shield Advanced, ACM and ACM Private CA). The second half is **DR**: the four postures — backup/restore, pilot light, warm standby, active/active — each with an honest RTO/RPO and a real cost number, and the AWS primitives that implement them (Aurora Global, DynamoDB Global Tables, S3 CRR, Route 53 failover).

We are vendor-aware, not vendor-loyal. The security stack has open-source shadows you should know exist — **Falco** and **Wazuh** for runtime threat detection, **Trivy** and **Grype** for vulnerability scanning, **HashiCorp Vault** for secrets, **OPA/Conftest** for policy-as-code — and the DR patterns are the same multi-region consensus and replication problems you will meet again in **C22 · Crunch Mesh**. We name the comparators not to send you down a rabbit hole, but so you know what the managed thing is doing for you and what you would own if you ran it yourself.

The artifacts you build this week are **not** throwaway. The syllabus is explicit: **the capstone build begins this week.** The security baseline you enable and the second-Region DR footprint you stand up are the capstone's `Security` and `DR` pillars, imported directly into the capstone monorepo in the weeks that follow. You are not doing a lab that gets deleted Sunday night — you are pouring the foundation of the thing you defend in Week 15. Build it to keep.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the KMS model end to end — AWS-managed keys vs customer-managed keys (CMKs), key policies vs IAM vs grants, automatic annual rotation, and **envelope encryption** (why AWS encrypts your data with a data key and the data key with the CMK).
- **Author** a least-privilege KMS **key policy** that separates key *administrators* from key *users*, and explain why `kms:*` to the root principal is the default that everyone misreads.
- **Choose** between Secrets Manager and SSM Parameter Store on the axes of rotation, cost, size, and cross-service integration, and wire a Secrets Manager secret with automatic rotation.
- **Enable** GuardDuty (org-wide via a delegated administrator), read a finding, and explain the three data sources it consumes (VPC Flow Logs, DNS query logs, CloudTrail) plus the EKS/S3/RDS/Lambda protection plans.
- **Aggregate** posture in Security Hub, enable the AWS Foundational Security Best Practices and CIS standards, and triage findings by severity to a documented disposition.
- **Run** Macie on the data-lake bucket to surface PII, and Inspector on EKS and ECR for vulnerability findings, and resolve every Critical/High.
- **Place** the edge controls correctly — WAF with AWS managed rule groups plus a custom rate-limit rule, Shield Advanced's trade-off, Network Firewall vs Security Groups/NACLs, and ACM vs ACM Private CA.
- **Pick a DR posture honestly** — backup/restore, pilot light, warm standby, active/active — given a stated RTO and RPO budget, and attach a real monthly cost to each.
- **Stand up** a second-Region DR footprint: DynamoDB Global Tables, an Aurora Global Database, S3 CRR with a **multi-region KMS key** so the replica is decryptable, and Route 53 health-checked failover records.
- **Execute** a manual Region failover end to end, measure the actual recovery time and data-loss window, and write the RTO/RPO you *achieved* against the budget you *targeted*.

## Prerequisites

This week assumes you have completed Weeks 1–12 of C19, or have equivalent AWS fluency. Specifically:

- You can deploy a CDK stack (TypeScript) from zero and read the synthesized CloudFormation. (Week 3.)
- You understand IAM policy evaluation — explicit deny wins, condition keys, `sts:AssumeRole` chains, permission boundaries. **This week leans hard on it**; a KMS key policy is just a resource policy, and GuardDuty/Security Hub org-wide setup is delegated-administrator IAM. (Week 2.)
- You have an Aurora cluster (Week 8) and a DynamoDB single-table design (Week 9). This week makes both multi-region. If you tore them down, the exercises include minimal stacks so you are not blocked.
- You have an S3 data-lake bucket with KMS encryption (Weeks 6, 11). Macie scans it and S3 CRR replicates it this week.
- You stood up an EKS cluster (Week 5). Inspector scans it. If it is torn down for cost, the Inspector exercise can target ECR images alone.
- Comfort reading a cost number off a pricing page and turning it into a monthly figure — Shield Advanced and a warm-standby Region are *not* cheap, and the point of Thursday is to feel that.

You do **not** need a security-specialist background. The week is engineering: turn the controls on, read what they say, fix what they flag, and prove the failover. The judgment — which DR posture, which findings matter — is what we are teaching.

## Topics covered

- **KMS deep:** AWS-managed keys vs CMKs, symmetric vs asymmetric, key policies vs IAM vs grants, the `kms:ViaService` condition, automatic rotation, **multi-region keys** (primary + replica sharing key material), and **envelope encryption** (data keys, `GenerateDataKey`, why S3/EBS/RDS all use it).
- **Secrets Manager vs SSM Parameter Store:** rotation (Lambda-backed), cross-account resource policies, per-secret cost vs free standard parameters, the 4 KB/8 KB size limits, and the "which one for a DB password" decision.
- **GuardDuty:** the three core data sources (VPC Flow Logs, DNS query logs, CloudTrail management + S3 data events), the protection plans (EKS Runtime, S3, RDS, Lambda, Malware Protection), org-wide enablement via a **delegated administrator**, finding types, and suppression rules.
- **Security Hub:** posture aggregation, the AWS Foundational Security Best Practices (FSBP) and CIS standards, control status, cross-Region aggregation, and the GuardDuty/Inspector/Macie finding ingestion (ASFF — AWS Security Finding Format).
- **Macie:** managed and custom data identifiers, a one-time sensitive-data discovery job on the lake bucket, and the cost model (per-GB inspected).
- **Inspector:** continuous vulnerability scanning of ECR images, EC2, and Lambda; the EKS angle via ECR image scanning and the cluster's nodes; CVE severity and the suppression workflow.
- **Network & edge controls:** AWS Network Firewall (stateful Suricata-style rules) vs Security Groups/NACLs; WAF web ACLs, AWS managed rule groups, and a custom rate-based rule; Shield Standard (free, always on) vs Shield Advanced (paid, with the DDoS Response Team and cost protection); ACM-managed public TLS vs **ACM Private CA** for internal mTLS.
- **DR postures:** backup/restore, pilot light, warm standby, active/active — the **RTO/RPO** definitions, the cost-vs-recovery-speed trade-off, and how to pick honestly.
- **Multi-region primitives:** DynamoDB Global Tables (multi-active, last-writer-wins), Aurora Global Database (sub-second replication, < 1 min RTO managed failover), S3 Cross-Region Replication, multi-region KMS keys (so the replica decrypts), and Route 53 health-checked failover routing.
- **Open-source comparators:** Falco/Wazuh (GuardDuty), Trivy/Grype (Inspector), Vault (Secrets Manager), OPA/Conftest (Security Hub controls-as-policy) — what each replaces and what you give up.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target. Capstone weeks (13–15) reshape the cadence around the build, so this week's mini-project time is heavier than earlier weeks.

| Day       | Focus                                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | KMS, Secrets Manager, envelope encryption; key-policy authoring    |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | GuardDuty + Security Hub + Macie + Inspector org-wide (Exercise 1) |    1h    |    2.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Wednesday | KMS multi-region key + Secrets rotation in CDK (Exercise 2)        |    1h    |    2.5h   |     0.5h   |    0.5h   |   0.5h   |     0h       |    0.5h    |     6h      |
| Thursday  | DR postures; DynamoDB Global Tables + Aurora Global (Exercise 3)   |    2h    |    2h     |     0h     |    0.5h   |   0.5h   |     1h       |    0h      |     6h      |
| Friday    | Route 53 failover; run the manual failover (Challenge 1)           |    0h    |    0h     |     2.5h   |    0.5h   |   0.5h   |     2h       |    0h      |     5.5h    |
| Saturday  | Mini-project deep work (capstone Security + DR pillars)            |    0h    |    0h     |     0h     |    0h     |   0.5h   |     3.5h     |    0h      |     4h      |
| Sunday    | Quiz, cost report, finding-triage write-up, review                 |    0h    |    0h     |     0h     |    1h     |   1h     |     0.5h     |    0h      |     2.5h    |
| **Total** |                                                                   | **6h**   | **8.5h**  | **3h**     | **3.5h**  | **5h**   | **7.5h**     | **2h**     | **35.5h**   |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated AWS docs, talks, books, and open-source comparators, current to 2026 |
| [lecture-notes/01-security-stack-kms-guardduty-waf.md](./lecture-notes/01-security-stack-kms-guardduty-waf.md) | KMS and envelope encryption; Secrets Manager; the GuardDuty/Security Hub/Macie/Inspector detection-and-posture stack; WAF/Shield/Network Firewall/ACM at the edge |
| [lecture-notes/02-multi-region-dr-rto-rpo.md](./lecture-notes/02-multi-region-dr-rto-rpo.md) | The four DR postures with real RTO/RPO and cost; DynamoDB Global Tables, Aurora Global, S3 CRR, multi-region KMS, Route 53 failover |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-security-baseline.md](./exercises/exercise-01-security-baseline.md) | Enable GuardDuty/Security Hub/Macie/Inspector, read findings, triage Critical/High |
| [exercises/exercise-02-kms-multiregion-secrets.py](./exercises/exercise-02-kms-multiregion-secrets.py) | Multi-region KMS key + Secrets Manager rotation, proven with boto3 |
| [exercises/exercise-03-global-tables-aurora-global.py](./exercises/exercise-03-global-tables-aurora-global.py) | DynamoDB Global Tables + Aurora Global Database; measure replication lag |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-route53-failover-drill.md](./challenges/challenge-01-route53-failover-drill.md) | Wire Route 53 health-checked failover and run a manual Region failover; record achieved RTO/RPO |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the "Security + DR Foundation" — the capstone's Security and DR pillars |
| [quiz.md](./quiz.md) | 14 questions with an answer key |
| [homework.md](./homework.md) | Concrete homework with deliverables and a rubric |

## The "RTO and RPO are numbers, not adjectives" promise

C19's recurring marker this week is the failover footer — the two numbers you write down after you fail over:

```
Failover drill: us-east-1 → us-west-2
  RTO (time to recover service):     achieved 4m12s   (target ≤ 5m)
  RPO (data lost at failover):       achieved 0s      (target ≤ 1s)  [DynamoDB Global Tables]
  RPO (Aurora Global):               achieved ~1.1s   (target ≤ 1s)  [missed — explain why]
```

If you cannot state your RTO and RPO as **measured numbers** after the Friday drill — not "low" or "fast" — you are not done. The single most common DR failure in a real incident is discovering that "we have a DR Region" meant "we have an empty Region with no data and no DNS pointing at it." RTO and RPO are numbers. The whole point of Thursday and Friday is to produce *your* two numbers and compare them to the budget you set. A DR plan without a tested RTO/RPO is a hope, not a plan.

## A safety note before you turn the security stack on

GuardDuty, Security Hub, Macie, and Inspector are **detective** controls — turning them on does not break anything, it makes the account *honest* about what is already wrong. But three cost notes matter:

- **Macie and Inspector bill by what they inspect.** A Macie job over a multi-terabyte lake, or Inspector continuously scanning a large ECR registry, is not free. The exercises scope Macie to a small sample prefix and Inspector to a handful of images. Read `resources.md` before you point Macie at a real lake.
- **Shield Advanced is a $3,000/month commitment** (per organization, 1-year minimum). You will **not** enable it in the lab; you will *reason* about when it is worth it. The exercise stops at Shield Standard (free) and a WAF rate-limit rule.
- **A warm-standby Region roughly doubles your steady-state compute bill.** That is the entire honesty of the DR-posture lecture: recovery speed costs money, and "active/active" is the most expensive sentence in this course. Thursday makes you put a dollar figure next to each posture.

## Stretch goals

If you finish the regular work early and want to push further:

- Configure a GuardDuty **suppression rule** for a known-benign finding type and explain why suppressing (not disabling) is the right move for tuning noise.
- Stand the DynamoDB table up as a **three-Region** Global Table and observe last-writer-wins conflict resolution by writing the same item key in two Regions within the replication window.
- Replace the managed WAF rule group with a custom rule that blocks a specific request pattern, and prove it with `curl` against the CloudFront/ALB distribution.
- Compute the cost of **Falco + Trivy + Vault** run on your own EKS cluster as the open-source equivalent of GuardDuty-EKS + Inspector + Secrets Manager, and find the break-even against the managed stack.
- Promote the S3 CRR to **bidirectional** (two-way replication with replica modification sync) and reason about the loop-prevention and conflict semantics.

## Up next

Week 14 — FinOps, Edge, and the capstone build continues. You will put CloudFront + WAF + a Lambda@Edge tenant-routing function in front of the capstone API, build a QuickSight cost dashboard on the Cost & Usage Report, and commit to a Savings Plan. The Shield Advanced cost reasoning and the warm-standby dollar figures from this week feed directly into that FinOps conversation. Push your security baseline and your second-Region footprint before you move on — Week 14 assumes both exist and the capstone monorepo imports them.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
