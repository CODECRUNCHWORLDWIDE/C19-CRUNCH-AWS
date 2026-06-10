# Challenge 1 — Defend the Event-Driven SaaS Backbone Live

> **Estimated time:** 3–4 hours including the reciprocal peer review. This is the terminal challenge of C19: the 30-minute oral defense that the syllabus weights at 10% of the entire course and that gates the Crunch Labs completion certificate. It is the moment everything you built since Week 1 has to stand up in front of a senior reviewer.

## The problem

You have assembled the capstone — the Event-Driven SaaS Backbone — over Weeks 13–15. Now you deploy it from zero, walk a single request through it on camera and in front of reviewers, present what you broke on purpose and what happened, defend the bill, and answer the questions a senior engineer asks before they will trust your design in production. Then you do the reciprocal: you review a peer's capstone with the same rigor and produce a written risk list.

The skill being tested is not "did you build a system" — Weeks 13–14 tested that. The skill is **calibrated honesty about your own system under questioning**: knowing exactly where it is strong, exactly where it is weak, and being able to say so with a measured number attached, while a reviewer probes for the thing you missed.

## What you deliver

1. **A clean deploy.** `cdk deploy --all` from a blank account (or a known-good baseline) stands up the entire system with no manual console steps beyond the documented one-time opt-ins (Bedrock model access, the SageMaker training run, the FIS role). The grader runs this.
2. **A one-screen architecture diagram** with the request path as its spine, committed to the repo.
3. **The single-event walk**, rehearsed and delivered in ≤ 8 minutes, naming every hop's failure mode and the signal that would reveal it.
4. **Three chaos-drill postmortems** in `/runbook/postmortems/`: the AZ-failover RTO drill (Exercise 1), the DynamoDB-throttle drill, and the Lambda-concurrency drill (Exercise 2) — each blameless, with a five-whys root cause, a measured timeline, and owned/dated/tagged action items. (A fourth bonus drill is a stretch.)
5. **The cost-defense memo** (`/runbook/COST-DEFENSE.md`): the weekly bill from the tagged CUR, the idle bill, the per-request cost, and the three ranked optimizations with dollar estimates.
6. **The 10-minute public walkthrough video**, linked from the repo README, that a hiring manager can watch and a peer can reproduce.
7. **A written peer review** of one cohort member's capstone: a risk list scored against the senior-reviewer question set, each risk tagged accept / mitigate-now / mitigate-later.
8. **A clean teardown.** `cdk destroy --all`, then proof of zero resources and zero billing tail.

## The 30-minute oral: the agenda you will be run through

The reviewers follow the agenda from Lecture 1 §1.2. Rehearse against it:

1. **Context + one-line spec (2 min).** One sentence: what it does, for whom.
2. **Diagram + single-event walk (8 min).** One request, edge to rest and back, every hop's failure mode and signal.
3. **Failure modes + chaos results (8 min).** The three drills: the measured AZ-failover RTO vs your target, the DynamoDB throttle and whether write-sharding defeated it, the Lambda concurrency exhaustion and where the back-pressure landed. Show the postmortems.
4. **Cost (4 min).** Weekly bill, idle bill, per-request cost, three optimizations.
5. **Q&A — the reviewers drive (8 min).** They probe whatever the first 22 minutes left exposed.

## The questions you must be ready for

From Lecture 1 §1.4–1.5. Have a one-sentence answer with a number for each:

- **Blast radius of your largest single failure?** (e.g. "losing the DynamoDB table fails all writes; Global Tables gives a second-Region copy at sub-second lag, so the mitigation is a Route 53 failover with RPO = replication lag.")
- **Your single points of failure?** Enumerate them and the deliberate cost/risk call on each. (If your SageMaker endpoint ran one instance, name it — a reviewer will.)
- **RTO and RPO, and how you *know*?** State the target *and the measured number* from the AZ drill and the replica lag.
- **What pages you at 3 a.m.?** The alarm catalog and why each page is actionable.
- **Where can you lose or duplicate data?** At-least-once hops, idempotency-by-design, the DLQ that catches failures, the bounded loss window.
- **Your CI role's IAM blast radius?** The OIDC trust scoped to repo/branch, the permission boundary, no static keys.
- **Least privilege on the request path?** Pick any Lambda; show its scoped role with no `Resource: "*"`.
- **How do you deploy a change safely?** Canary + alarm-based automatic rollback; the blast radius of a bad deploy.
- **What happens at 10x traffic?** Which component bends first, and what you'd do.

## Acceptance criteria

- [ ] `cdk deploy --all` stands the system up from a clean baseline with no undocumented manual steps.
- [ ] A one-screen architecture diagram is committed, with the request path as its spine.
- [ ] You deliver the single-event walk in ≤ 8 minutes, naming each hop's failure mode and signal, without reading from a script.
- [ ] Three blameless postmortems exist, each with a five-whys systemic root cause, a measured UTC timeline, and action items that all have an owner, a date, and a disposition tag.
- [ ] The AZ-failover postmortem states a *measured* recovery time and a PASS/REVIEW verdict against your documented RTO; the RPO is justified by a measured replica lag.
- [ ] The cost-defense memo states the weekly bill from the tagged CUR, the idle bill, the per-request cost, and three ranked optimizations with dollar estimates.
- [ ] A 10-minute public walkthrough video is linked from the repo README.
- [ ] You answer the senior-reviewer question set in the oral, every answer carrying a number where one is called for.
- [ ] You submit a written peer review of one cohort member's capstone: a risk list scored against the question set, each risk tagged.
- [ ] `cdk destroy --all` removes everything; you prove zero resources remain (`aws sagemaker list-endpoints`, `aws rds describe-db-clusters`, etc.) and there is no billing tail.

## Stretch

- Run and present **all four** chaos drills (the three required plus the bonus — NAT saturation, CloudFront origin failure, or KMS throttle). A four-drill postmortem section is portfolio-grade.
- Turn the AZ-failover experiment into a **scheduled GameDay**: an EventBridge-scheduled FIS experiment against a non-prod copy, posting the recovery time to a CloudWatch dashboard, so resilience is trended. Demonstrate one scheduled run.
- Promote the Aurora cross-region replica under FIS for a true warm-standby failover, re-measure RTO/RPO, and present whether the lower RTO justifies the standing cost.
- Write the **exit plan**: price moving this workload off AWS to self-hosted Kafka + Trino + Iceberg + vLLM on EKS in engineer-weeks and dollars, with a confidence interval on each estimate. Present it as the "what is our lock-in cost" answer a CTO would ask.

## What "good" looks like

A strong defense feels like a senior engineer walking a colleague through a system they *operate*, not one they merely built. They trace a request without looking at the diagram. When asked about a weakness, they say "yes — here is the blast radius, here is why I accepted it, here is the mitigation if it gets worse," with a number. Their chaos results are measured, not asserted: "the AZ drill recovered in 142 seconds against a 300-second target, and here is the postmortem." Their cost answer names the idle bill and the first optimization without hesitation. A weak defense asserts that nothing can fail, has no measured numbers, and gets quiet when the reviewer points at the single-instance endpoint. The entire course was built to make you the first kind of engineer. This is where you prove it.
