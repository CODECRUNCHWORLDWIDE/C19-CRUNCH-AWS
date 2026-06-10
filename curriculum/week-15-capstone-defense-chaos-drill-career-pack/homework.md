# Week 15 Homework

Five problems that produce the written artifacts of the capstone defense and the career pack. The full set should take about **5 hours**. Work in your capstone repository so each problem produces at least one commit you can point to. Several problems produce artifacts you will use directly in Friday's oral — do them before the defense, not after.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — The blameless postmortem

**Problem statement.** Take the measured timeline from one chaos drill (the AZ-failover drill from Exercise 1 is the best choice) and write a complete blameless postmortem. It must have: a summary with a PASS/REVIEW verdict, a UTC timeline (t0 / t_fault / t_impact / t_recover), a five-whys root-cause chain that reaches a *systemic* root (not "the fault we injected" and not "human error"), an expected-vs-actual section, and action items that each have an owner, a due date, and an accept/mitigate-now/mitigate-later tag.

**Acceptance criteria.**

- A committed `runbook/postmortems/az-failover.md`.
- The timeline uses real measured timestamps, not placeholders.
- The five-whys chain reaches a systemic, fixable root (e.g. "no documented node-headroom policy"), and the corresponding action item fixes *that*.
- Every action item has an owner, a date, and a tag.

**Hint.** Exercise 2's driver emits a pre-filled skeleton; for the AZ drill, copy that shape and fill the timeline from your Exercise 1 probe log. The root cause is never the injected fault (that was expected) — it is the design property that made the fault hurt, or the one that made it harmless.

**Estimated time.** 1 hour.

---

## Problem 2 — The cost-defense memo

**Problem statement.** Write the one-page cost-defense memo for your capstone. Using the tagged Cost & Usage Report (Week 14), state: the actual weekly bill broken down by `service` tag, the idle bill (what the system costs per day with zero traffic), the per-request cost (weekly bill ÷ week's request count), and whether per-request cost rises or falls with scale. Then name the three optimizations you would commit first, each with a dollar estimate and a one-line justification.

**Acceptance criteria.**

- A committed `runbook/COST-DEFENSE.md`.
- The weekly bill comes from the CUR (cite the query / the date pulled), not from memory.
- The idle bill names its components (e.g. SageMaker endpoint, NAT Gateway, Aurora minimum).
- The three optimizations are ranked, each with a dollar estimate (Graviton ~20%, a Compute Savings Plan ~30–40% on the committed baseline, killing the largest idle line item, etc.).

**Hint.** Lecture 1 §1.6 has the worked shape. The per-request number and whether it rises or falls with scale is the FinOps-maturity signal a reviewer listens for: fixed costs amortize, so a well-shaped system gets cheaper per request as it scales.

**Estimated time.** 1 hour.

---

## Problem 3 — The single-event walk script

**Problem statement.** Write the script (as notes, not a recited speech) for your ≤ 8-minute single-event walk: one tenant request traced from CloudFront to its resting place and back, naming at *every hop* the component, the failure mode, and the observability signal that would reveal that failure. Then rehearse it out loud on a timer and record how long it took.

**Acceptance criteria.**

- A committed `runbook/event-walk.md` covering: edge (CloudFront/WAF/Lambda@Edge), API layer (API Gateway/ALB), compute (Lambda/EKS), the event spine (EventBridge/SQS/DLQ/Step Functions/Firehose), data at rest (DynamoDB/Streams/Global Tables, Aurora multi-AZ + cross-region), and the inference path (SageMaker + Bedrock).
- Each hop names a failure mode and a signal.
- A note of your rehearsed time (target ≤ 8 minutes).

**Hint.** Lecture 1 §1.3 walks the exact path for the capstone. The discipline is "here is where it breaks, and here is the metric or trace that tells me." If a hop has no signal, that is itself a finding.

**Estimated time.** 1 hour.

---

## Problem 4 — Cert readiness self-assessment

**Problem statement.** Run the readiness gate (Exercise 3) for both the SAP-C02 and DOP-C02 domain sets. Record your overall score, your per-domain breakdown, and your two weakest domains. Then write a short study plan: for each weak domain, name the C19 weeks that cover it and one concrete thing you will review.

**Acceptance criteria.**

- A committed `career/cert-readiness.md` with your overall score, the per-domain table, and the PASS/PARTIAL/FAIL verdict.
- Your two weakest domains identified, each mapped to the C19 weeks that cover it (the scorer prints this mapping).
- One concrete review action per weak domain.

**Hint.** Run `python3 exercises/exercise-03-cert-readiness-gate.py` (all domains), then `--exam sap` and `--exam dop` separately to see each blueprint's score. The scorer's study-plan output is your starting point.

**Estimated time.** 1 hour.

---

## Problem 5 — Reflection: would you ship it?

**Problem statement.** Write a 350–450 word reflection at `career/week-15-reflection.md` answering:

1. After the chaos drills, would you put this capstone in front of real users on Monday? Where would it break *first*, how would you know, and what is the one thing you would fix before you slept?
2. Which chaos drill surprised you most — did a hypothesis you were confident in turn out false? What did that teach you about the gap between a diagram and a running system?
3. The course was "vendor-aware, not vendor-loyal." For one piece of your capstone, name the open-source alternative (EKS over plain k8s, DynamoDB over ScyllaDB, Kinesis over Kafka, SageMaker over vLLM) and say honestly what you'd gain and lose by switching.
4. One thing C19 didn't cover that you now want to learn next (multi-region active-active? service mesh? a deeper security specialty?), and why.

**Acceptance criteria.**

- File exists, 350–450 words, each numbered question in its own paragraph.
- Committed.

**Hint.** This is for *you*, and it doubles as your engineering-journal entry for the week. The honest answer to Q1 — naming a real weakness, the signal that reveals it, and the fix — is the exact "calibrated honesty about your own system" the defense grades. Practice it here.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 1 h 0 min |
| 2 | 1 h 0 min |
| 3 | 1 h 0 min |
| 4 | 1 h 0 min |
| 5 | 30 min |
| **Total** | **~4 h 30 min** |

*(The schedule budgets 5h to leave slack for the cost-defense memo in Problem 2, which always takes longer than you think the first time you query the CUR.)*

---

## Rubric

Graded out of 20.

| Criterion | Points | What earns full marks |
|---|---:|---|
| **Postmortem quality (P1)** | 6 | Blameless, with a measured UTC timeline, a five-whys chain that reaches a *systemic* root (not the injected fault, not "human error"), and action items that all have an owner, a date, and a tag. |
| **Cost-defense rigor (P2)** | 5 | Weekly bill from the real CUR (cited), idle bill broken into components, per-request cost, and three ranked optimizations with dollar estimates. Not estimates from memory. |
| **Defense readiness (P3)** | 5 | The single-event walk names a failure mode and a signal at every hop and rehearses to ≤ 8 minutes. A hop with no signal is itself flagged. |
| **Cert self-assessment (P4)** | 2 | The readiness gate run for both exams, weak domains identified and mapped to weeks, with concrete review actions. |
| **Reflection honesty (P5)** | 2 | Engages genuinely, especially with Q1 (would you ship it, what breaks first, the one fix) and Q2 (the surprising drill). |

A pass is 14/20. Anything below means re-write Problem 1 — the blameless postmortem with a systemic root cause is the week's load-bearing skill, and the one a reviewer will probe hardest in the oral.

When you've finished all five, push your repo and deliver the [challenge](./challenges/challenge-01-defend-the-capstone-live.md) — the live defense itself.
