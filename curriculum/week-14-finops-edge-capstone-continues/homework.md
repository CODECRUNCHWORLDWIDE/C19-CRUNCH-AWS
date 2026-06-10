# Week 14 Homework

Five problems that revisit and extend the week's topics. The full set should take about **5 hours**. Work in your Week 14 Git repository (or the capstone monorepo) so each problem produces at least one commit you can point to later. Several problems produce numbers that belong in your cost report — keep them.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — The untagged-spend audit

**Problem statement.** Using the CUR table from Exercise 1, write the query that computes total spend, total *Usage*-type spend, and the `(untagged)` total (resources with no `team` tag), and turn it into a percentage. Then identify, from the per-resource CUR column, the **three biggest untagged line items** by service, and write one sentence each on why they're untagged and how you'd tag them.

**Acceptance criteria.**

- A committed `notes/untagged-audit.md` with the total, the untagged total, the untagged percentage, and the top-three untagged services with a remediation sentence each.
- The query filters `line_item_line_item_type = 'Usage'` for the apples-to-apples number, and notes the gross (all-types) number separately.
- At least one of the three is a *shared* cost (data transfer, NAT, a lake bucket) that needs a **cost category** rather than a resource tag — and you say so.

**Hint.** Group by `COALESCE(NULLIF(resource_tags_user_team,''),'(untagged)')` for the team split, then a second query grouping the untagged rows by `product_servicecode` to find the biggest offenders. Some spend (cross-AZ data transfer, marketplace) genuinely can't carry a resource tag — that's the cost-category case.

**Estimated time.** 45 minutes.

---

## Problem 2 — Compute (and defend) the Savings Plan break-even

**Problem statement.** For your capstone's steady-state compute floor, compute the Compute Savings Plan break-even and make a *commit / don't-commit* recommendation. Pull the **current** instance/Savings-Plan rates from the pricing pages (cite the date). Show:

1. The observed steady-state floor (the always-running compute), in $/hr on-demand. (Use Cost Explorer's Savings Plans coverage report or your Exercise 2 output.)
2. The proposed commitment (~80–90% of the floor) and the discount.
3. The break-even utilization (≈ 1 − discount) and your projected utilization.
4. The commitment risk if the steady-state dropped 20%, in $/month.
5. A one-paragraph recommendation: which Savings Plan *type* (Compute / EC2-Instance / SageMaker) and which term (1yr/3yr, no-/partial-/all-upfront), and why — or why you'd wait.

**Acceptance criteria.**

- A committed `notes/savings-plan-break-even.md` with all five items and the arithmetic shown.
- Prices cited with the date pulled.
- The recommendation is *consistent* with the numbers (you don't recommend a 3-year all-upfront on a workload you said is six months from a rewrite).

**Hint.** Break-even utilization ≈ (1 − discount). Commit to the *floor*, not the average. The conservative default is 1-year no-upfront Compute SP; reach for 3-year all-upfront EC2-Instance only for a baseline you'd bet your job on.

**Estimated time.** 1 hour.

---

## Problem 3 — Rightsize one resource and quantify a Graviton move

**Problem statement.** From Compute Optimizer (Exercise 2), pick one over-provisioned resource in your account/capstone and **act on it** (downsize it, or document exactly the change you'd make and the projected saving if you can't safely change it in a lab). Separately, take one stateless service and compute the **Graviton** (arm64) monthly delta of moving it from its x86 family to the equivalent Graviton family, using current on-demand prices.

**Acceptance criteria.**

- A committed `notes/rightsize-and-graviton.md` documenting: the rightsizing change (before/after instance type, projected monthly saving, and the memory-blindness caveat if relevant), and the Graviton delta (x86 $/hr, arm $/hr, monthly saving, percentage).
- The Graviton note states that the price delta is only half the story and that you'd verify with a *price-per-request* measurement after a multi-arch rebuild.
- If you actually rebuilt a service `linux/arm64` (stretch), include the measured before/after.

**Hint.** `aws compute-optimizer get-ec2-instance-recommendations --filters Name=Finding,Values=Overprovisioned`. For Graviton, compare e.g. `m7i.large` to `m7g.large` on the pricing page; the multi-arch build is Week 7's `docker buildx`.

**Estimated time.** 1 hour.

---

## Problem 4 — Place the edge logic by cost

**Problem statement.** For your capstone edge tier, write a table that lists *each* piece of edge logic (cache-key rewrite, tenant-cookie verify, header stamping, any redirect, rate limiting, etc.) and assigns each to the correct tier — **CloudFront Function**, **Lambda@Edge**, or **WAF** — with the per-1M cost and a one-line justification. Then compute the **monthly edge cost** at a stated traffic profile (e.g. 5M requests/month, 60% cache-hit), and state what it *would* have cost to put everything in Lambda@Edge instead.

**Acceptance criteria.**

- A committed `notes/edge-cost-placement.md` with the per-logic placement table and the two monthly totals (your split vs everything-in-Lambda@Edge).
- Each placement justified by the network/origin-tier/runtime questions from Lecture 2.
- The cache-key/header logic is in the CloudFront Function tier, and the cost saving of that choice is quantified.
- WAF cost (per web ACL + per rule + per 1M inspected) included in the monthly total.

**Hint.** CloudFront Function ~$0.10/1M (no duration); Lambda@Edge ~$0.60/1M + GB-seconds; WAF has a per-ACL, per-rule, and per-1M-request component. Verify all three on the pricing pages and cite the date. Cache hits never trigger origin-tier logic — factor the hit rate in.

**Estimated time.** 45 minutes.

---

## Problem 5 — Reflection: cost as a feature

**Problem statement.** Write a 350–450 word reflection at `notes/week-14-reflection.md` answering:

1. "FinOps is SRE for the bill." After building the cost dashboard and the break-even analysis, do you buy that framing? Where does the analogy hold, and where does it break down?
2. Your untagged-spend number from Problem 1 — was it higher than you expected? What does it tell you about your IaC tagging discipline across Weeks 11–13, and what one change would most reduce it?
3. The CloudFront-Function-vs-Lambda@Edge split saved you money by keeping cheap logic in the cheap tier. Name one *other* place in your capstone where you could apply the same "right work in the right (cheaper) tier" principle.
4. One thing this week didn't cover that you now want to learn (FOCUS multi-cloud cost? OpenCost on EKS? Budgets actions as a circuit breaker? CloudFront KeyValueStore?).

**Acceptance criteria.**

- File exists, 350–450 words, each numbered question in its own paragraph.
- Committed.

**Hint.** This is for *you*. The honest answer to Q2 (your tagging discipline was probably weaker than you thought, and applying `Tags.of(app).add(...)` at the app root plus a Config/SCP guardrail is the one change that fixes it) is exactly the kind of nuance a senior engineer carries.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 45 min |
| 2 | 1 h 0 min |
| 3 | 1 h 0 min |
| 4 | 45 min |
| 5 | 30 min |
| **Total** | **~4 h 0 min** |

*(The schedule budgets 5h for homework to leave slack for Problem 3's rightsizing/Graviton work, which always takes longer than you think the first time — especially if you actually rebuild a service for arm64.)*

---

## Rubric

Graded out of 20.

| Criterion | Points | What earns full marks |
|---|---:|---|
| **Allocation rigor (P1)** | 5 | A correct untagged-spend number and percentage, the top-three offenders identified, and the shared-cost/cost-category case recognized. Not a hand-wave. |
| **Commitment reasoning (P2)** | 5 | Break-even arithmetic shown, prices cited with dates, the recommendation consistent with the floor/risk numbers and the right SP type/term justified. |
| **Optimization action (P3)** | 4 | A real rightsizing change (or a precise documented one) with the memory caveat, and a correct Graviton delta with the price-per-request nuance. |
| **Edge cost placement (P4)** | 4 | Every piece of logic placed in the correct tier with the per-1M cost, the split saving quantified, WAF cost included. |
| **Reflection honesty (P5)** | 2 | Engages genuinely with the FinOps-as-SRE framing and the tagging-discipline self-audit. |

A pass is 14/20. Anything below means re-read Lecture 1's break-even section and Lecture 2's tier-cost split, and re-run Problems 2 and 4 with real, cited numbers — that arithmetic is the week's load-bearing skill.

When you've finished all five, push your repo and open the [mini-project](./mini-project/README.md) if you haven't already — the homework numbers (untagged spend, break-even, edge cost placement) feed straight into the mini-project's `COSTREPORT.md`.
