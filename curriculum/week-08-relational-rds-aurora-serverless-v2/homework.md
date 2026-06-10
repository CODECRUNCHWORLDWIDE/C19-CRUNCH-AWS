# Week 8 Homework

Five practice problems that revisit the week's topics and rehearse the mid-program design exam. The full set should take about **4 hours**. Work in your Week 8 Git repository so each problem produces at least one commit or artifact you can point to later.

Each problem includes a **problem statement**, **acceptance criteria** so you know when you're done, a **hint**, and an **estimated time**.

---

## Problem 1 — Read the Aurora paper and extract the quorum argument

**Problem statement.** Read sections 2–4 of "Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases" (SIGMOD 2017, linked in `resources.md`). Write a 250–300 word note at `notes/aurora-quorum.md` that answers, in your own words:

1. Why six copies across three AZs, rather than three copies across three AZs.
2. What the 4/6 write and 3/6 read quorums each protect against (be specific about "AZ loss" vs "AZ + 1").
3. Why the 10 GiB segment size is central to the durability argument (the mean-time-to-repair point).
4. The "~7.7× less network traffic" claim — what is Aurora *not* sending that mirrored-Postgres-on-EBS *is* sending.

**Acceptance criteria.**

- `notes/aurora-quorum.md` exists, is 250–300 words, and correctly states the 4/6 and 3/6 quorums.
- It explains the segment-size / fast-repair durability argument (not just "six is more than three").
- It names what Aurora does not ship (full data pages / double writes), citing the paper section.
- Committed.

**Hint.** The repair-window argument is in the paper's durability-at-scale discussion: fast segment re-replication shrinks the window in which a second correlated failure could break quorum. Lecture 1 §1.3 paraphrases it.

**Estimated time.** 45 minutes.

---

## Problem 2 — Compute three break-evens by hand

**Problem statement.** Using `R_acu = $0.12`/ACU-hr and the provisioned rate table from Lecture 2 §2.2, compute the **break-even average ACU** for each of `db.r7g.large`, `db.r7g.xlarge`, and `db.r7g.2xlarge`. Then, for a workload whose measured time-averaged ACU is **3.0**, state which billing mode is cheaper against each class, and the monthly dollar figure for both modes (single node, 730 hours). Put the work in `notes/breakeven-math.md` as a table.

**Acceptance criteria.**

- The three break-even ACUs are correct: ~2.30, ~4.60, ~9.20.
- For avg 3.0 ACU: Serverless v2 (`3 × 0.12 × 730 = $262.80`) is **cheaper than** `db.r7g.large` ($201? — check!) — actually state the comparison correctly with the numbers.
- The table shows ASv2 and provisioned monthly cost side by side for each class.
- A one-line conclusion: at avg 3.0 ACU, ASv2 beats `xlarge`/`2xlarge` but **loses** to `large` (3.0 > 2.30 break-even).
- Committed.

**Hint.** Break-even is `R_prov / R_acu`. At avg 3.0 ACU, ASv2 costs `3.0 × 0.12 × 730 = $262.80`. Compare to `large` $201.48, `xlarge` $402.96, `2xlarge` $805.92. ASv2 loses to `large` (you exceeded its 2.30 break-even) but wins against `xlarge` and `2xlarge` (you are below theirs). This is the subtle "right-size first, then choose mode" lesson.

**Estimated time.** 30 minutes.

---

## Problem 3 — Write the failover runbook entry

**Problem statement.** Using your Exercise-3 measurements (or, if you have not run it yet, the expected-output numbers), write a runbook entry at `runbook/aurora-failover.md` of the kind that goes in a real on-call playbook. It must include: the alarm/symptom that indicates a writer failure, the **expected** write and read recovery times (your measured numbers), the command to check failover status (`aws rds describe-events`), the application-side expectation (the cluster endpoint CNAME re-points; the app reconnects to the same hostname), and the **stated RTO and RPO** with one sentence of justification each.

**Acceptance criteria.**

- `runbook/aurora-failover.md` exists with all six elements above.
- The RPO is correctly stated as **zero** for an in-region Aurora failover (shared storage; promoted reader sees all durable writes) and the justification is correct.
- The RTO is your measured write-recovery p-max, not a guess.
- The app-side note correctly says the connection string does **not** change (cluster endpoint CNAME).
- Committed.

**Hint.** This is the template you will reuse for the capstone's chaos-drill postmortem. Keep it tight — a runbook entry someone reads at 3 a.m. should be scannable, not an essay.

**Estimated time.** 40 minutes.

---

## Problem 4 — Find the RDS Proxy pinning condition

**Problem statement.** RDS Proxy multiplexes connections, but certain SQL operations force it to "pin" a backend connection to one client session, losing the multiplexing benefit. Read the RDS Proxy docs (`resources.md`), then write `notes/proxy-pinning.md` listing **at least four** operations that cause pinning (e.g., `SET` of certain session variables, prepared statements outside autocommit, advisory locks, temp tables) and, for each, a one-line mitigation or "unavoidable." Then explain in two sentences why pinning matters for a Lambda fleet specifically.

**Acceptance criteria.**

- `notes/proxy-pinning.md` lists ≥4 pinning triggers, each with a mitigation note.
- It correctly explains that a pinned connection is removed from the pool for that session's duration, so heavy pinning collapses the proxy back toward one-connection-per-client — exactly the `max_connections` problem you used the proxy to solve.
- It names the Lambda angle: short-lived invocations that each pin defeat the proxy's whole purpose.
- Committed.

**Hint.** Search the RDS Proxy User Guide for "pinning" / "Avoiding pinning." `SET SESSION` of certain variables, `CREATE TEMPORARY TABLE`, advisory locks, and protocol-level prepared statements are the usual suspects.

**Estimated time.** 30 minutes.

---

## Problem 5 — Design-exam warm-up: the multi-tenant data layer

**Problem statement.** The mid-program design exam is a 3-hour multi-tenant SaaS whiteboard. Warm up by writing a 1-page design note at `design/multi-tenant-data-layer.md` answering: for a SaaS with 500 tenants, would you use **pool** (all tenants in one cluster, `tenant_id` column + row-level security), **silo** (one cluster per tenant), or **bridge** (schema-per-tenant in shared clusters)? Pick one, and defend it on **three axes**: cost (use the ACU math — what does 500 idle silo clusters cost vs one pool cluster?), isolation/blast-radius (a noisy or compromised tenant), and connection-pool math (how RDS Proxy + IAM auth changes the fan-out). State where Serverless-v2-with-min=0 changes the silo math.

**Acceptance criteria.**

- `design/multi-tenant-data-layer.md` picks one model and defends it on all three axes with at least one **number** per axis.
- The cost axis uses real ACU/provisioned math (e.g., "500 silo Serverless-v2 clusters at avg 0.3 ACU = `500 × 0.3 × 0.12 × 730` vs one pool `db.r7g.2xlarge` = $806/mo").
- The connection axis correctly reasons about RDS Proxy multiplexing and per-tenant IAM-scoped DB users.
- It states the condition under which the answer flips (e.g., a regulated tenant demanding silo isolation regardless of cost).
- Committed.

**Hint.** There is no single right answer — there is a defensible answer with numbers. Pool is usually cheapest and the default; silo is for hard isolation/compliance; bridge splits the difference. Serverless-v2-with-min=0 makes silo *much* cheaper for idle-heavy tenants, which is the modern twist (Lecture 2 §2.4 Profile C, the "per-tenant micro-clusters" line). This is exactly the question the design exam will probe.

**Estimated time.** 55 minutes.

---

## Submission

Commit all five artifacts to your Week 8 repository under the paths given (`notes/`, `runbook/`, `design/`). In your engineering journal for the week, add a paragraph on **the one number that surprised you most** — most students are surprised by how steeply Serverless v2 loses on steady load, or by how small the in-region failover RPO actually is (zero).

## Rubric (50 points)

| Problem | Points | Full marks |
|---|---:|---|
| P1 — Aurora paper note | 10 | Correct quorums, segment/repair durability argument, the "not shipping pages" point. |
| P2 — Break-even math | 10 | Three correct break-even ACUs and the correct avg-3.0 conclusion (loses to `large`, beats `xlarge`/`2xlarge`). |
| P3 — Failover runbook | 10 | All six elements; RPO=0 justified; RTO from measurement; app-side CNAME note correct. |
| P4 — Proxy pinning | 10 | ≥4 triggers with mitigations; correct explanation of why pinning defeats the pool; Lambda angle. |
| P5 — Design warm-up | 10 | One model chosen, defended on all three axes with numbers, flip condition stated. |

**Pass:** 35/50. The design warm-up (P5) is the single best preparation for the Wednesday exam — do not skip it.
