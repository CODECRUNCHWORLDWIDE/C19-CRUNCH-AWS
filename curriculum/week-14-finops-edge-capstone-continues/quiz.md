# Week 14 — Quiz

Fourteen questions. Take it with your lecture notes closed. Aim for 11/14 before moving to Week 15. Answer key at the bottom — don't peek.

---

**Q1.** The lecture frames FinOps as "SRE for the bill." Which FinOps concept is the equivalent of an SRE **burn-rate alarm**?

- A) A Cost & Usage Report.
- B) A Budgets *forecast* alert (and/or Cost Anomaly Detection firing on a spike).
- C) A cost allocation tag.
- D) A Savings Plan.

---

**Q2.** Which is the **source of truth** for per-resource, line-item cost allocation?

- A) The Cost Explorer console screenshot.
- B) The monthly PDF invoice.
- C) The Cost & Usage Report (CUR) delivered to S3.
- D) The Billing dashboard's "month-to-date" number.

---

**Q3.** You run the per-team CUR query and a large `(untagged)` bucket appears. What does that number most directly measure?

- A) The amount AWS overcharged you.
- B) The fraction of your bill you currently cannot allocate to a team — your tag-hygiene debt.
- C) The cost of the CUR itself.
- D) Spend that will be automatically refunded.

---

**Q4.** A user-defined tag `team` exists on your resources but does not appear as a grouping dimension in Cost Explorer. The most likely reason:

- A) Tags can't be used for cost.
- B) The tag must be **activated** as a cost allocation tag in the Billing console, and activation is not retroactive.
- C) You must restart the resources.
- D) Cost Explorer only supports AWS-generated tags.

---

**Q5.** Your capstone's compute is a stable EKS + Lambda baseline you expect to keep for a year, spread across instance families you may change. Which commitment fits best?

- A) A 3-year all-upfront Standard Reserved Instance on one instance type.
- B) A 1-year Compute Savings Plan.
- C) Spot instances only.
- D) No commitment ever.

---

**Q6.** A Savings Plan offers a 40% discount on covered usage. Roughly what **utilization** must you sustain for the commitment to break even versus paying on-demand?

- A) ~10%.
- B) ~40%.
- C) ~60%.
- D) ~95%.

---

**Q7.** Lecture 1's ordering rule for optimization is:

- A) Buy the Savings Plan first, then rightsize.
- B) Rightsize first, observe the new floor, *then* commit to a Savings Plan.
- C) Always commit to the peak usage.
- D) Never rightsize a committed instance.

---

**Q8.** Compute Optimizer recommends downsizing an instance, but your workload is memory-heavy. What's the trap?

- A) Compute Optimizer never recommends downsizing.
- B) Without the CloudWatch agent reporting memory, the recommendation is memory-blind and could OOM you.
- C) Downsizing always improves performance.
- D) Memory is irrelevant to instance choice.

---

**Q9.** Which edge logic belongs in a **CloudFront Function** rather than Lambda@Edge?

- A) Verifying an HMAC-signed cookie and looking up a tenant in DynamoDB.
- B) A fast, every-request cache-key/header rewrite with no network call.
- C) Rewriting the origin response body after fetching from a third-party API.
- D) Anything that must run at the origin-request trigger.

---

**Q10.** CloudFront Functions and Lambda@Edge differ in which way?

- A) CloudFront Functions can call the network; Lambda@Edge cannot.
- B) Lambda@Edge runs at all four trigger points and can call the network; CloudFront Functions run only at the viewer tier, sub-ms, with no network access.
- C) They cost exactly the same per million invocations.
- D) Lambda@Edge can be deployed in any Region with no constraint.

---

**Q11.** Where must a Lambda@Edge function be **created**?

- A) Any Region.
- B) The Region nearest your users.
- C) `us-east-1`.
- D) Inside the CloudFront distribution itself.

---

**Q12.** Your tenant-injection edge function adds `x-tenant-id` only when the signed cookie is valid. What critical step is still required for security?

- A) Nothing else; adding the header is sufficient.
- B) On the untrusted/missing-cookie path, **strip any client-supplied `x-tenant-id`** so the origin can't be tricked into trusting a forged header.
- C) Cache the 401 response for an hour.
- D) Log the cookie value in plaintext.

---

**Q13.** You need an edge tier for a **UDP game server** that requires a **static anycast IP**. The right AWS service is:

- A) CloudFront.
- B) A CloudFront Function.
- C) AWS Global Accelerator.
- D) Lambda@Edge.

---

**Q14.** CloudFront origin failover (origin groups) does **not** automatically retry which kind of request against the secondary?

- A) `GET`.
- B) `HEAD`.
- C) A non-idempotent `POST`/`PUT`/`PATCH` (because retrying a write could double-apply it).
- D) `OPTIONS`.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — A forecast-based Budget alert (or Cost Anomaly Detection) is the burn-rate equivalent: it warns mid-month that you're trending over, the same way a burn-rate alarm warns you'll exhaust the error budget. The CUR is the data; a tag is allocation; a Savings Plan is an optimization.
2. **C** — The CUR is the most granular billing export (line-item, hourly, optionally per-resource). Cost Explorer is a *view*; the CUR is the *ledger* you allocate and audit from.
3. **B** — Untagged spend is the portion you can't attribute to a team; it caps your FinOps maturity. It's not an overcharge or a refund.
4. **B** — A tag becomes a cost dimension only after activation in Billing, and activation allocates from that point forward, not retroactively. Activate early.
5. **B** — A Compute Savings Plan is the most flexible (any family/size/Region, EC2/Fargate/Lambda) and survives architectural change — right for a stable-but-evolving baseline. A 3-year Standard RI locks you to one type; Spot is for stateless; "no commitment" leaves the discount on the table.
6. **C** — Break-even utilization ≈ (1 − discount). At a 40% discount, ~60% utilization. Below that, the wasted idle commitment costs more than you saved. (Commit to the *floor*, not the average, to stay well above this.)
7. **B** — Rightsize first so you commit to the smaller, true baseline; committing to an over-provisioned fleet locks in capacity you're about to shrink.
8. **B** — Compute Optimizer sees CPU/network for free but is blind to memory unless the agent reports it; a memory-blind downsize can OOM. Enable memory metrics before trusting a memory-sensitive call.
9. **B** — A fast, no-network, every-request transform is the CloudFront Function's whole purpose (sub-ms, ~$0.10/1M). A/C need network/runtime/origin-tier → Lambda@Edge; D is origin-tier, which CF Functions can't do.
10. **B** — Lambda@Edge: full runtime, network access, all four triggers, ~$0.60/1M + duration, us-east-1-only. CloudFront Functions: viewer-tier, sub-ms, no network (except KeyValueStore), ~$0.10/1M.
11. **C** — Lambda@Edge functions are created in `us-east-1` and CloudFront replicates them to edge locations.
12. **B** — The origin can only trust `x-tenant-id` if the edge guarantees it; that means *removing* any client-supplied copy on the untrusted path, not just adding it on the trusted path. Otherwise a client forges the header directly.
13. **C** — Global Accelerator gives static anycast IPs and does TCP/UDP at the edge; CloudFront is HTTP/caching and its functions are HTTP-tier. (GA also carries a fixed hourly cost CloudFront doesn't.)
14. **C** — Failover auto-retries idempotent methods (GET/HEAD/OPTIONS); it does *not* auto-retry a non-idempotent write, because a retried POST could double-apply. Design write paths accordingly.

</details>

---

If you scored under 10, re-read the lecture for the questions you missed — especially the Savings Plan break-even arithmetic (Q6) and the CloudFront-Function-vs-Lambda@Edge split (Q9–Q12), which the homework and challenge both lean on. If you scored 13 or 14, you're ready for the [homework](./homework.md).
