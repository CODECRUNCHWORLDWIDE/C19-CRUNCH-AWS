# Mini-Project — The Capstone: Deliver, Drill, and Defend the Event-Driven SaaS Backbone

> Assemble every prior-week artifact into one running **Event-Driven SaaS Backbone**, deployable from `cdk deploy --all` and destroyable with `cdk destroy --all`. Run the chaos drill (AZ failover, DynamoDB throttle, Lambda concurrency exhaustion, plus a bonus). Write the blameless postmortems. Produce the runbook, the dashboards-as-code, the cost report, and the 10-minute walkthrough video. Then **defend it** in a 30-minute oral. This is the terminal deliverable of C19 — the credential the entire course was building toward, weighted at 35% (system) + 10% (oral) of the program grade.

This is not a new build. It is the *integration, hardening, proof, and defense* of everything you have built since Week 1. The capstone began in Week 13, continued in Week 14, and culminates here. This week you do not add a service — you assemble, break, measure, and present.

**Estimated time:** ~11 hours of mini-project work across the week (the schedule reserves Mon–Sat blocks), on top of the exercises and challenge.

---

## How this compounds

The capstone is the sum of the course. Every week fed it:

- **Weeks 1–3** gave you the multi-account Organization with SCPs, IAM Identity Center, permission boundaries, and the CDK monorepo that deploys all of it.
- **Weeks 4–7** gave you the VPC with endpoints (not three NAT gateways), the EKS + Fargate + Lambda compute hybrid, the S3 storage tiers, and the CodePipeline/GitHub-Actions-OIDC delivery flow.
- **Weeks 8–11** gave you Aurora (multi-AZ + cross-region replica), the DynamoDB single-table with Streams, the EventBridge spine with SQS DLQs and Step Functions Express, and the S3/Glue/Athena lake plus the SageMaker endpoint and Bedrock comparison.
- **Weeks 12–14** gave you the OpenTelemetry/ADOT observability with the 99.9% SLO burn-rate alarm, the GuardDuty/Security Hub/Macie/Inspector security baseline, the DynamoDB Global Tables + Aurora cross-region + Route 53 DR posture, and the FinOps controls with the tagged Cost & Usage Report.

Week 15 turns that pile of artifacts into one *defensible system*. The acceptance bar is the highest of the course: the grader deploys it, hits it, breaks it with FIS, reads your dashboards, and tears it down — and then you defend every decision in front of reviewers.

---

## What you assemble

The full required architecture is in `SYLLABUS.md` under "Capstone specification." In one diagram:

```
                          Route 53 (health-checked failover, primary -> standby Region)
                                       │
   ┌──────────────────────────── CloudFront + WAF + ACM TLS ────────────────────────────┐
   │  CloudFront Functions (header rewrite) · Lambda@Edge (tenant routing from cookie)    │
   └───────────────┬─────────────────────────────────────────────┬───────────────────────┘
                   │ /api/* (CRUD)                                 │ /app/* (long-lived)
                   ▼                                               ▼
        API Gateway HTTP API ──► Lambda (event-handler)     ALB ──► EKS (Karpenter Spot)
                   │                    │                                │ + ECS Fargate sidecar
                   │                    ▼                                │
                   │            EventBridge custom bus  ◄────────────────┘
                   │             ├─► SQS (+ DLQ) ──► retry consumers
                   │             ├─► Step Functions Express (orchestration)
                   │             └─► Kinesis Firehose ──► S3 lake (Glue + Athena)
                   ▼
        DynamoDB single-table  ──Streams──► Lambda fan-out
          └─ Global Tables ──────────────────────────────► second Region (DR)
        Aurora PostgreSQL (multi-AZ writer + cross-region read replica) ── analytical queries
                   │
        SageMaker real-time endpoint (>=2 instances, multi-AZ)  ◄── recommend() Lambda
          └─ parallel Bedrock Claude call (comparison feature)

   Cross-cutting:
     Identity   : IAM Identity Center (humans) · Cognito (end users) · IRSA / exec roles · perm boundaries
     Observability: ADOT collector (EKS DaemonSet + Lambda extension) -> X-Ray + CloudWatch · burn-rate SLO alarm · Synthetics canary
     Security   : GuardDuty · Security Hub · Macie (lake bucket) · Inspector (ECR + EKS) · KMS-CMK everywhere · Secrets Manager
     FinOps     : team/service/environment tags · CUR -> Athena -> QuickSight · one committed Savings Plan
     Chaos      : FIS experiment templates (AZ-power, DynamoDB, Lambda) with CloudWatch stop conditions
```

---

## Required deliverables

The syllabus's capstone "Deliverables" section is the checklist. This week, all of it must exist and be demonstrable.

### 1. The CDK monorepo

- **One command up, one command down.** `cdk deploy --all` from a clean baseline; `cdk destroy --all` leaves nothing billing. TypeScript primary, with at least one stack in Python (the syllabus requires it).
- **CI on GitHub Actions with OIDC federation** into AWS — no long-lived keys, trust scoped to your repo and branch.
- **FIS experiment templates defined as code** (`aws-cdk-lib/aws-fis` `CfnExperimentTemplate`) so the chaos drills live in the repo and run reproducibly.

### 2. The runbook (`/runbook` in the repo)

- Architecture diagrams (the one-screen request-path diagram above, plus any detail diagrams).
- On-call rotation template and the alarm catalog: which alarms page versus ticket, and why each page is actionable.
- Top-10 incident playbooks — one per likely incident (AZ loss, hot partition, concurrency exhaustion, NAT saturation, KMS throttle, cert expiry, deploy rollback, Region failover, DLQ backlog, cost anomaly).

### 3. Dashboards as code

- CloudWatch dashboards defined in CDK (not click-built): the three-tier trace > metric > log view, the SLO burn-rate panel, the DLQ-depth panel, the cost panel.
- QuickSight assets exported (the tagged-CUR cost dashboard from Week 14).

### 4. The chaos-drill postmortems (`/runbook/postmortems/`)

The syllabus requires, at minimum:

- **AZ failover** — kill one AZ's EKS nodes and the Aurora writer (Exercise 1, FIS). Measure recovery against your RTO. Prove (or fix) that the SageMaker endpoint is not a single-AZ SPOF.
- **DynamoDB throttle** — force a hot partition (Exercise 2). Show the degrade, then show write-sharding defeating it.
- **Lambda concurrency exhaustion** — saturate reserved concurrency (Exercise 2). Trace the back-pressure into SQS and the DLQ; prove it is back-pressure, not data loss.
- **Bonus drill of your choice** — NAT saturation, CloudFront origin failure, or KMS throttle.

Each postmortem is **blameless**, has a **five-whys** systemic root cause, a **measured UTC timeline**, and **action items with owner + date + tag**. (Lecture 2 §2.8 is the template; Exercise 2 generates the skeleton pre-filled.)

### 5. The 10-minute public walkthrough video

A screen-recorded walkthrough that traces one event through the system and explains the key trade-offs. Linked from the repo README. A hiring manager should be able to watch it; a peer should be able to reproduce the system from the repo after watching it.

### 6. The cost report

Actual dollar number for one week of capstone operation, from the tagged CUR, broken down by `service`. Plus the idle bill, the per-request cost, and the three ranked optimizations — the cost-defense memo from Lecture 1 §1.6.

---

## Required for the defense

The system is half the grade; the **oral defense** is the other gate (and the certificate requires passing it). Bring:

- The one-screen diagram and the rehearsed ≤ 8-minute single-event walk.
- The three (or four) postmortems with measured timelines.
- The four cost numbers.
- A one-sentence, number-backed answer to every question in Lecture 1's senior-reviewer set: blast radius, SPOFs, measured RTO/RPO, the 3-a.m. page walk, data loss/duplication, the CI-role IAM blast radius, least privilege on the request path, safe deploys, and the 10x-traffic bottleneck.

And the reciprocal: a **written peer review** of one cohort member's capstone — a risk list scored against the same question set, each risk tagged accept / mitigate-now / mitigate-later.

---

## Rules

- **CDK is the source of truth.** You may drive the SageMaker training run and run the CTAS by hand, but every persistent resource is in CDK so the system stands up and tears down on demand.
- **Run the chaos drills against a non-prod copy.** Inject faults with FIS stop conditions as the seatbelt. Never inject an uncapped fault.
- **Measured, not asserted.** Your RTO and RPO must be *measured numbers* from the drills and the replica lag, not targets you hope for. A reviewer trusts a measurement; an assertion fails the reliability question.
- **No `Resource: "*"` on the request path.** Every execution role on a request-path component is least-privilege on specific ARNs. A wildcard is a finding (and the IAM reviews in Weeks 2/5/13 already held you to this).
- **Clean teardown is part of the grade.** `cdk destroy --all` must leave zero resources and zero billing tail. A leaked Aurora cluster, SageMaker endpoint, or NAT Gateway is the difference between a pass and a surprise bill.
- **Tag everything.** `team`, `service`, `environment` on every resource — the cost report depends on it.

---

## Acceptance criteria

- [ ] A public GitHub repo (`c19-capstone-event-driven-saas-<yourhandle>`) containing the CDK monorepo, the runbook, the postmortems, the cost report, and the video link.
- [ ] `cdk deploy --all` from a clean baseline stands up the whole system with no undocumented manual steps (Bedrock model-access opt-in, the SageMaker training run, and the FIS role are the only documented manual one-time steps).
- [ ] CI runs on GitHub Actions with OIDC federation; no long-lived AWS keys exist in the repo or the account.
- [ ] A single request can be traced edge-to-rest-and-back through CloudFront → API/ALB → Lambda/EKS → EventBridge → DynamoDB/Aurora → SageMaker/Bedrock, and you can narrate it.
- [ ] The AZ-failover FIS drill ran with a stop condition; the postmortem states a measured recovery time and a PASS/REVIEW verdict against your documented RTO.
- [ ] The DynamoDB-throttle drill shows throttling without sharding and materially fewer throttles with write-sharding; the postmortem documents the mitigation.
- [ ] The Lambda-concurrency drill shows the `Throttles` metric rising and the back-pressure landing in SQS/DLQ then draining; the postmortem proves it was back-pressure, not data loss.
- [ ] A bonus drill ran and has a postmortem.
- [ ] All postmortems are blameless, with five-whys root causes and owned/dated/tagged action items.
- [ ] DynamoDB Global Tables, the Aurora cross-region read replica, and Route 53 health-checked failover exist; the RPO is justified by a measured replica lag.
- [ ] The SageMaker endpoint runs ≥ 2 instances across AZs (not a single-AZ SPOF).
- [ ] Dashboards are defined in CDK; the SLO burn-rate alarm and the DLQ-depth alarm exist.
- [ ] Every resource is tagged `team`, `service`, `environment`.
- [ ] `COST-DEFENSE.md` states the weekly bill (from the tagged CUR), the idle bill, the per-request cost, and three ranked optimizations with dollar estimates.
- [ ] A 10-minute public walkthrough video is linked from the README.
- [ ] You delivered the 30-minute oral and submitted a written peer review of one cohort member's capstone.
- [ ] `cdk destroy --all` removes everything; you prove zero resources remain and there is no billing tail.

---

## Suggested build order

1. **Monday (2 h mini-project + lecture).** Final integration: import the Week-13/14 stacks, get `cdk deploy --all` clean from a non-prod baseline, fix anything that does not `destroy` cleanly. Add the FIS role and one no-op experiment to prove the chaos plumbing.
2. **Tuesday (1 h + Exercise 1+2).** Run the AZ-failover FIS drill (Exercise 1). Capture the timeline and write the first postmortem. Confirm the SageMaker SPOF fix (≥ 2 instances).
3. **Wednesday (1.5 h + Exercise 2).** Run the DynamoDB-throttle drill (without then with sharding) and the Lambda-concurrency drill. Write both postmortems. Run a bonus drill if time allows.
4. **Thursday (1.5 h + Exercise 3).** Write `COST-DEFENSE.md` from the tagged CUR. Finalize the dashboards-as-code and the runbook playbooks. Take the cert readiness gate (Exercise 3) and note your two weakest domains.
5. **Friday (2.5 h + Challenge 1).** Record the 10-minute walkthrough video. Deliver the live 30-minute oral defense. Review a peer's capstone in writing.
6. **Saturday (2 h).** Mock interview in both variants (Well-Architected and FAANG). Portfolio polish: README, diagrams, video link. Run the full deploy-test-destroy loop once more, clean, and confirm zero billing tail.

---

## A worked snippet — the FIS experiment as code in the monorepo

So the chaos drills are reproducible and version-controlled, define them in CDK alongside the rest of the capstone. This is the AZ-failover template (Lecture 2 §2.5) as a stack the monorepo includes:

```typescript
import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as fis from 'aws-cdk-lib/aws-fis';

interface ChaosStackProps extends StackProps {
  fisRoleArn: string;   // the FIS execution role (created in the security stack)
  api5xxAlarmArn: string; // the stop-condition alarm (from the observability stack)
}

export class ChaosStack extends Stack {
  constructor(scope: Construct, id: string, props: ChaosStackProps) {
    super(scope, id, props);

    new fis.CfnExperimentTemplate(this, 'AzFailover', {
      description: 'Capstone AZ-failover drill: stop EKS nodes in us-east-1a',
      roleArn: props.fisRoleArn,
      stopConditions: [{ source: 'aws:cloudwatch:alarm', value: props.api5xxAlarmArn }],
      tags: { Name: 'capstone-az-failover', team: 'platform', service: 'chaos', environment: 'nonprod' },
      targets: {
        eksNodesAz1a: {
          resourceType: 'aws:ec2:instance',
          selectionMode: 'ALL',
          resourceTags: { service: 'eks-node' },
          filters: [
            { path: 'Placement.AvailabilityZone', values: ['us-east-1a'] },
            { path: 'State.Name', values: ['running'] },
          ],
        },
      },
      actions: {
        stopAz1aNodes: {
          actionId: 'aws:ec2:stop-instances',
          description: 'Stop running EKS nodes in us-east-1a',
          parameters: { startInstancesAfterDuration: 'PT10M' }, // self-reverting
          targets: { Instances: 'eksNodesAz1a' },
        },
      },
    });
  }
}
```

The `startInstancesAfterDuration: 'PT10M'` makes the fault self-revert; the `stopConditions` alarm is the seatbelt. Because it is in CDK, the grader (and a future you) can stand up the experiment with the rest of the system and run the drill identically every time. That reproducibility is the difference between a one-off lab and an operable system.

---

## Submission

Push the repo, link the video from the README, and submit your peer review. In your engineering journal, answer the question the whole course was building toward: *Would you put this system in front of real users on Monday? Where would it break first, how would you know, and what is the one thing you would fix before you slept?* The honest answer — naming a real weakness, the signal that reveals it, and the fix — is the deliverable. An engineer who can say that about their own system is the engineer this course set out to build.

---

## What this completes

This is the last mini-project of C19. After you push it, clear the readiness gate, and survive the oral, you are done. The intended next track is **C22 · Crunch Mesh** — take the EKS-plus-event-driven backbone you just defended and grow it into a multi-region active-active distributed system with consensus, sagas, and idempotency at scale. Do not delete the repo: it is your portfolio capstone, the thing you point a hiring manager at, and the starting point for Mesh.
