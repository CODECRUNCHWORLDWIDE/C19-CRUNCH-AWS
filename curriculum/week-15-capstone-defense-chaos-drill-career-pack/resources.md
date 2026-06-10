# Week 15 — Resources

Everything here is free to read. AWS documentation is open, the re:Invent talks are on YouTube, the exam guides are public PDFs, and the postmortem and architecture-review templates are open source. We link a couple of paid books at the chapter level only where the free material genuinely falls short.

A scheduling note that will save you a day: **set up your FIS execution role and one trivial experiment template on Monday.** FIS will not run an experiment without a role it can assume that holds the targeted-resource actions, and discovering a missing `ec2:RebootInstances` or AZ-availability permission at the moment you try to inject a fault on Wednesday is a waste of an afternoon. Run one no-op experiment Monday so the plumbing is proven before the real drill.

## Required reading (work it into your week)

- **AWS Fault Injection Service — what is FIS** (the service that drives your chaos drills):
  <https://docs.aws.amazon.com/fis/latest/userguide/what-is.html>
- **FIS — experiment templates, actions, targets, stop conditions** (the four building blocks you assemble):
  <https://docs.aws.amazon.com/fis/latest/userguide/experiment-templates.html>
  <https://docs.aws.amazon.com/fis/latest/userguide/actions.html>
  <https://docs.aws.amazon.com/fis/latest/userguide/targets.html>
  <https://docs.aws.amazon.com/fis/latest/userguide/stop-conditions.html>
- **FIS — the AZ Availability: Power Interruption scenario** (the supported way to simulate a full AZ outage end-to-end):
  <https://docs.aws.amazon.com/fis/latest/userguide/fis-scenario-az-availability.html>
- **FIS — IAM roles for experiments** (the role FIS assumes; the single most common setup failure):
  <https://docs.aws.amazon.com/fis/latest/userguide/security-iam.html>
- **AWS Well-Architected Framework** (the five-pillar lens your AWS-shop interview and your defense both use):
  <https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html>
- **The AWS Builders' Library — "Building resilient services" and "Implementing health checks"** (the source material for the questions a reviewer will ask):
  <https://aws.amazon.com/builders-library/>
- **AWS Resilience Hub** (the tool that scores an app against RTO/RPO targets and recommends fixes — read it even if you don't run it):
  <https://docs.aws.amazon.com/resilience-hub/latest/userguide/what-is.html>

## The chaos-drill mechanics (read these before Wednesday)

- **FIS — `aws:ec2:stop-instances` / `aws:ec2:reboot-instances` actions** (AZ-node faults on EKS managed node groups, which are EC2 ASGs underneath):
  <https://docs.aws.amazon.com/fis/latest/userguide/fis-actions-reference.html>
- **FIS — `aws:eks:*` and `aws:ecs:*` actions** (pod/task-level faults on the EKS and Fargate halves):
  <https://docs.aws.amazon.com/fis/latest/userguide/eks-actions.html>
- **FIS — `aws:dynamodb:*` and the throttle/error-injection actions** (and how to combine FIS with a hot-partition load to force throttling):
  <https://docs.aws.amazon.com/fis/latest/userguide/fis-actions-reference.html>
- **Lambda — reserved concurrency and throttling** (the lever you saturate in the concurrency-exhaustion drill, and the `Throttles`/`429` you trace into SQS):
  <https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html>
- **Lambda — error handling and DLQs / Lambda destinations for async invokes** (where the back-pressure lands):
  <https://docs.aws.amazon.com/lambda/latest/dg/invocation-async.html>
- **DynamoDB — partition behavior, adaptive capacity, and throttling** (why a hot partition throttles even with capacity to spare, and why write-sharding fixes it):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html>

## Postmortem & architecture-review templates (free, open source)

- **Google SRE Book — "Postmortem Culture: Learning from Failure"** (the canonical blameless-postmortem chapter; the five-whys and action-item discipline come from here):
  <https://sre.google/sre-book/postmortem-culture/>
- **Google SRE Workbook — the example postmortem** (a filled-in template you can copy the shape of):
  <https://sre.google/workbook/postmortem-analysis/>
- **AWS — operational readiness reviews (ORR)** (the closest AWS-native analog to the cohort architecture review; the question set overlaps heavily):
  <https://docs.aws.amazon.com/wellarchitected/latest/operational-readiness-reviews/wa-operational-readiness-reviews.html>
- **The "Etsy Debriefing Facilitation Guide" (Allspaw)** — the practitioner's guide to running a blameless review without it turning into a blame session. Search for it; it is a free PDF.

## Pricing pages (read these as dollars, not docs — you need them for the cost-defense memo)

You cannot write the cost-defense memo without the numbers. Open these and write the figures into the memo:

- **AWS Cost & Usage Report → Athena/QuickSight** (the tagged breakdown your memo rests on; you set this up in Week 14):
  <https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html>
- **Savings Plans pricing** (the commitment you defend as optimization #1 for steady-state compute):
  <https://aws.amazon.com/savingsplans/pricing/>
- **Graviton (arm64) and the price/performance case** (the cheapest single optimization for most steady workloads):
  <https://aws.amazon.com/ec2/graviton/>
- **AWS Fault Injection Service pricing** (per action-minute; the drill itself costs cents, but know the number):
  <https://aws.amazon.com/fis/pricing/>
- **SageMaker, Aurora, NAT Gateway pricing** (the three line items most likely to dominate an idle capstone bill):
  <https://aws.amazon.com/sagemaker/pricing/> · <https://aws.amazon.com/rds/aurora/pricing/> · <https://aws.amazon.com/vpc/pricing/>

## AWS certification — the exam blueprints (free PDFs)

We map your gaps; we do not certify you. Read the official exam guide for each target before you self-assess in Exercise 3.

- **AWS Certified Solutions Architect — Professional (SAP-C02)** — exam guide and domain weighting. Domains: Solutions for Organizational Complexity (26%), Design for New Solutions (29%), Continuous Improvement (25%), Accelerate Migration & Modernization (20%):
  <https://aws.amazon.com/certification/certified-solutions-architect-professional/>
- **AWS Certified DevOps Engineer — Professional (DOP-C02)** — exam guide and domains: SDLC Automation (22%), Configuration Management & IaC (17%), Resilient Cloud Solutions (15%), Monitoring & Logging (15%), Incident & Event Response (14%), Security & Compliance (17%):
  <https://aws.amazon.com/certification/certified-devops-engineer-professional/>
- **AWS Certified Security — Specialty (SCS-C02)** — the spine is Weeks 2 and 13; read the guide if security is your weak domain:
  <https://aws.amazon.com/certification/certified-security-specialty/>
- **AWS Skill Builder — official practice question sets** (the closest free analog to the real scenario style; do a timed set before the readiness gate):
  <https://skillbuilder.aws/>

The per-domain readiness checklists referenced in the syllabus live at `/career/sap-map.md`, `/career/dop-map.md`, and `/career/scs-map.md` in the course repo; Exercise 3 scores you against the same domains.

## System-design interview prep

- **"Grokking the System Design Interview" framing** — the request walk, the back-of-envelope estimate, the bottleneck, the trade-off. The shape is the same whether the interviewer is at a FAANG or an AWS shop; only the substrate differs.
- **AWS Well-Architected as the AWS-shop interview script** — the five pillars (Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization) are literally the rubric an AWS-shop interviewer scores against. Be able to walk your capstone through all five.
- **The AWS Architecture Center reference architectures** (the patterns an interviewer expects you to reach for, and to know the trade-offs of):
  <https://aws.amazon.com/architecture/>
- **"Designing Data-Intensive Applications" (Kleppmann)** — the FAANG-variant bible. Chapters 5 (replication), 8 (the trouble with distributed systems), and 9 (consistency and consensus) are the ones a distributed-systems interviewer probes.

## re:Invent and AWS talks (free, on YouTube)

- **"Chaos engineering on AWS with AWS Fault Injection Service"** — the FIS deep dive; search the AWS Events channel for the most recent year's ARC/OPS-track FIS session:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Operational excellence at Amazon" / "How Amazon does on-call"** — the source for the postmortem and runbook discipline this week teaches:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Advanced architectures with the AWS Well-Architected Framework"** — the five-pillar framing for your defense and the AWS-shop interview:
  <https://www.youtube.com/@AWSEventsChannel>

*(re:Invent session IDs change yearly; the channel is stable. Filter by the most recent year and the ARC / OPS / DOP tracks.)*

## Open-source comparators (know what you traded away)

- **Chaos Toolkit / Chaos Mesh / Litmus** — open chaos-engineering frameworks. FIS is the managed, AWS-integrated, IAM-governed, stop-condition-aware option; these are what you run yourself on Kubernetes when you want cloud-portable chaos. You give up the AWS-native AZ-power and managed-service fault actions and gain portability:
  <https://chaostoolkit.org/> · <https://chaos-mesh.org/> · <https://litmuschaos.io/>
- **Gremlin** — the commercial chaos platform FIS competes with; worth knowing the feature comparison for an interview.
- **k6 / Locust / `hey` / `vegeta`** — the load generators you drive the system with before and during the drill. Use whichever you already know; the capstone only needs sustained, measurable request load:
  <https://k6.io/docs/> · <https://locust.io/>

## Books (chapter-level)

- **"Site Reliability Engineering" (Google)** — Chapters on postmortems, error budgets, and on-call are the free, definitive treatment of everything this week's postmortem and runbook deliverables ask for. Read the postmortem chapter cover to cover. Free online:
  <https://sre.google/sre-book/table-of-contents/>
- **"Chaos Engineering" (Rosenthal & Jones, O'Reilly)** — the discipline's foundational text: the principles, the GameDay, the steady-state hypothesis. Borrow it; read the principles chapter.

## The Claude / Bedrock note (your capstone calls it)

Your capstone's comparison feature calls **Anthropic Claude** through Bedrock. The current model IDs, the region-prefixed **inference-profile** IDs, and per-1K-token pricing change often enough that you should not trust memory — confirm the current Haiku/Sonnet model ID and price from the Bedrock console (Model access → the model's detail page) and the pricing page above before you put a Bedrock per-call cost in the cost-defense memo. Week 11's lecture notes use `anthropic.claude-3-5-haiku-20241022-v1:0` and the US cross-Region inference profile `us.anthropic.claude-3-5-haiku-20241022-v1:0` as the worked example; verify against your account, because availability is Region- and account-specific.

## Tools you'll use this week

- **AWS CLI v2** — `aws fis create-experiment-template`, `aws fis start-experiment`, `aws cloudwatch describe-alarms`. Verify with `aws --version` (want `aws-cli/2.x`).
- **AWS CDK v2** (TypeScript) — `npx cdk deploy --all` / `npx cdk destroy --all`. The capstone monorepo is CDK; FIS experiment templates can be defined in CDK too (`aws-cdk-lib/aws-fis` L1 constructs).
- **Python 3.12+** with `boto3` — the chaos-drill driver (Exercise 2) and the readiness-gate scorer (Exercise 3) are Python.
- **A load generator** — `k6`, `hey`, `vegeta`, or Locust. Any one is fine.
- **`jq`** — for slicing the JSON the FIS and CloudWatch CLIs return.
- **A screen recorder** — for the 10-minute walkthrough video. OBS Studio (free) or your OS's built-in recorder.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **FIS** | AWS Fault Injection Service: managed chaos engineering. You define experiment templates and it injects faults with IAM governance and stop conditions. |
| **Experiment template** | The FIS object that bundles actions, targets, stop conditions, and an execution role. Reusable; you start *experiments* from it. |
| **Action** | One fault FIS injects: stop instances, throttle DynamoDB, inject Lambda errors, interrupt an AZ's power. |
| **Target** | The resources an action hits, selected by ARN, by tag, or by a resource filter (e.g. "all EKS nodes in `us-east-1a`"). |
| **Stop condition** | A CloudWatch alarm that, if it fires, *halts the experiment immediately*. The seatbelt: you never run an uncapped fault in an account with real users. |
| **AZ power interruption** | The FIS scenario that simulates a full Availability Zone outage (compute, network, and managed-service AZ affinity) — the supported way to test AZ failover. |
| **Blast radius** | How much of the system a single fault can take down. The first question a reviewer asks. Smaller is better. |
| **RTO** | Recovery Time Objective: the maximum acceptable time to restore service after a failure. You *prove* yours with the AZ drill. |
| **RPO** | Recovery Point Objective: the maximum acceptable data loss, measured in time. Cross-region replication lag is your RPO floor. |
| **Blameless postmortem** | An incident writeup that treats failures as systemic, not personal. "Human error" is never a root cause; the system that allowed it is. |
| **Five whys** | Asking "why" repeatedly past the proximate cause until you reach a systemic, fixable root. |
| **Burn-rate alarm** | An SLO alarm that fires when the error budget is being consumed faster than the SLO allows. You watch it during the drill. |
| **Well-Architected** | AWS's five-pillar review framework. Both your capstone defense and the AWS-shop interview score against it. |
| **Cost-defense memo** | A one-pager that ties the running system to a real weekly dollar figure and names the first optimizations. The senior skill of "cost as a feature." |
| **GameDay** | A scheduled, rehearsed chaos exercise run as a team. The mature form of the one-off chaos drill. |

---

*If a link 404s, please open an issue so we can replace it.*
