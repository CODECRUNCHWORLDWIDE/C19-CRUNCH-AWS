# Week 15 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13. Answer key at the bottom — don't peek.

---

**Q1.** What is the primary *output* of an architecture review?

- A) A signed-off slide deck.
- B) A list of risks and a go/no-go decision about whether the design is safe to operate.
- C) A new architecture the reviewer would have built instead.
- D) A cost estimate only.

---

**Q2.** In the single-event walk, the discipline at every hop is to name:

- A) The AWS service's launch year.
- B) The failure mode at that hop and the observability signal that would reveal it.
- C) The IAM policy ARN verbatim.
- D) The CloudFormation logical ID.

---

**Q3.** A reviewer asks for your RTO. Which answer is strongest?

- A) "Our RTO target is 5 minutes."
- B) "RTO target 5 minutes; the AZ-failover FIS drill measured actual recovery at 142 seconds — PASS."
- C) "We assume Aurora's documented failover time."
- D) "We haven't measured it, but it should be fast."

---

**Q4.** Chaos engineering is best defined as:

- A) Randomly breaking production to see what happens.
- B) A controlled experiment to falsify a hypothesis about the system's resilience, behind a stop condition.
- C) Load testing with extra traffic.
- D) Disabling monitoring during a deploy.

---

**Q5.** In AWS Fault Injection Service, what is a *stop condition*?

- A) The maximum duration of an experiment.
- B) A CloudWatch alarm that, if it fires, halts the experiment immediately — the seatbelt.
- C) The IAM role FIS assumes.
- D) The tag used to select targets.

---

**Q6.** Your first FIS experiment fails with `AccessDenied`. What is the most likely cause?

- A) The CloudWatch alarm is in OK state.
- B) The FIS execution role is missing a target-resource action (e.g. `ec2:StopInstances`) it needs.
- C) The experiment template has too many tags.
- D) FIS is not available in your Region.

---

**Q7.** The DynamoDB-throttle drill provokes throttling on one partition. What mitigation should make the throttles materially drop?

- A) Increasing the Lambda timeout.
- B) Write-sharding the hot key across multiple suffixes so writes spread across partitions.
- C) Switching the table to a colder storage class.
- D) Adding a CloudFront distribution in front of DynamoDB.

---

**Q8.** In the Lambda concurrency-exhaustion drill, what signal best confirms the throttle became *back-pressure* rather than *data loss*?

- A) The billing dashboard updated.
- B) The `Throttles` metric rose and the async DLQ / on-failure destination caught the excess, which then drained after the load dropped.
- C) CPU on the function host increased.
- D) The `Invocations` metric stayed flat.

---

**Q9.** In a blameless postmortem, an operator deleted production data with a destructive command. What is the correct *root cause*?

- A) The operator's mistake.
- B) The system that allowed a destructive command to reach production with no guardrail or least-privilege boundary.
- C) The time of day.
- D) Bad luck.

---

**Q10.** Every action item in a postmortem must have which three properties to be a commitment, not a wish?

- A) A color, a font, and a heading.
- B) A named owner, a due date, and a disposition tag (accept / mitigate-now / mitigate-later).
- C) Three manager approvals, a Jira link, and a label.
- D) A severity, a screenshot, and a Slack thread.

---

**Q11.** For the cost-defense, which number best explains *why you destroy the SageMaker endpoint nightly in non-prod*?

- A) The per-request cost at peak traffic.
- B) The idle bill — what the system costs per day if nobody calls it.
- C) The total bytes scanned by Athena.
- D) The number of CloudFront edge locations.

---

**Q12.** In the AWS-shop (Well-Architected) system-design interview, the rubric the interviewer scores against is:

- A) The number of services you can name.
- B) The five pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization.
- C) Whether you used the newest service.
- D) Lines of CDK written.

---

**Q13.** Your capstone's RPO target is 1 minute across Regions. For the Aurora analytical store, what most directly determines your *actual* RPO?

- A) The CloudFront cache TTL.
- B) The Aurora cross-region read-replica replication lag at the moment of failure.
- C) The DynamoDB on-demand burst limit.
- D) The Lambda reserved concurrency.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — A review's output is a risk list and a safe-to-operate decision, not a slide sign-off. A reviewer who finds no risks did not do the job; one who imposes the architecture they'd have built (C) is failing. (Lecture 1 §1.1.)
2. **B** — At every hop you name the failure mode *and* the signal that reveals it. A walk that names hops but not failures is a tour, not a defense. (Lecture 1 §1.3.)
3. **B** — A *measured* RTO from the chaos drill beats a target every time. The reviewer trusts what you measured, not what you hope. (Lecture 1 §1.4, Lecture 2 §2.7.)
4. **B** — A controlled experiment to falsify a resilience hypothesis, behind a stop condition. Random breakage (A) is sabotage; the seatbelt is what makes it engineering. (Lecture 2 §2.1–2.2.)
5. **B** — A stop condition is a CloudWatch alarm that aborts the experiment the instant steady state collapses. It is the difference between FIS and a reckless script. (Lecture 2 §2.3.)
6. **B** — FIS assumes an execution role; the most common failure is that role missing a target-resource action. Read the error, add the action, retry. (Lecture 2 §2.4, Exercise 1.)
7. **B** — Write-sharding spreads the hot key across suffixes so writes hit multiple partitions, defeating the hot partition. (Week 9; Lecture 2 §2.6 Drill 2.)
8. **B** — Throttles rising shows the ceiling; the DLQ/destination catching and later draining the excess proves the events were held and reprocessed, not lost. (Lecture 2 §2.6 Drill 3.)
9. **B** — Blameless postmortems never stop at "human error." If a human could destroy prod, the missing guardrail is the systemic, fixable root. (Lecture 2 §2.8.)
10. **B** — Owner, date, and disposition tag. Unowned, undated action items are wishes nobody acts on. (Lecture 2 §2.8.)
11. **B** — The idle bill (what it costs with zero traffic) explains the architecture's fixed-cost floor and why you kill the always-on endpoint nightly. (Lecture 1 §1.6.)
12. **B** — The five Well-Architected pillars are literally the AWS-shop interviewer's rubric; be able to walk your capstone through all five. (Lecture 1; resources.)
13. **B** — RPO is the data-loss window; for a cross-region replica it is bounded by the replication lag at failure time. You must measure that lag to defend the number. (Week 13; Exercise 3.)

</details>

---

If you scored under 9, re-read Lecture 1's question set and Lecture 2's FIS-and-postmortem mechanics — both the oral defense and the chaos drill lean on them. If you scored 12 or 13, you're ready for the [homework](./homework.md) and the live defense.
