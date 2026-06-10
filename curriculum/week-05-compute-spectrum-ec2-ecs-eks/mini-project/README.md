# Mini-Project — The Compute Decision Doc

> Write a **one-page compute decision document**, backed by your three-way benchmark, that recommends which platform you would pick for a *named, real* product — and defends that pick the way you would in front of a principal engineer. The doc is one page. The credibility behind it is the entire week: three working deployments, a fair benchmark table, and honest cost math.

This is the deliverable that the rest of Week 5 was building toward. Anyone can say "use Fargate, it's simpler" or "use EKS, it scales." A senior engineer writes the *decision* down, attaches the *numbers*, names the *assumptions*, and states what would *change their mind*. That last part — the reversal conditions — is what separates a decision doc from an opinion. A reviewer's first question is always "at what point is this the wrong call?" and your doc must answer it before they ask.

This decision frame and the IRSA/Karpenter EKS setup you built this week feed **directly into the capstone's compute-hybrid layer** (EKS + Fargate + Lambda behind one CloudFront distribution). The capstone does not ask you to pick *one* platform — it asks you to put each workload on the *right* platform. This mini-project is the rehearsal: do it once, for one product, with the numbers in hand.

**Estimated time:** ~7.5 hours (split across Friday and Saturday in the suggested schedule). Most of the time is the benchmark and the cost arithmetic; the writing is the last hour.

---

## What you will produce

Two files, committed to your Week 5 repo at `mini-project/`:

1. **`decision.md`** — the one-page decision doc (the deliverable a reviewer reads first). One page means **one page**: ~600–900 words plus the benchmark table. Ruthless editing is part of the skill.
2. **`benchmark.md`** — the supporting three-way benchmark from Challenge 1 (table, raw numbers, cost arithmetic, load-generator commands). This is the evidence `decision.md` cites. It can be longer; it is the appendix.

You are not building new infrastructure. You are using the three deployments from Exercises 1–3 and the benchmark from Challenge 1, and turning them into a written recommendation. If you skipped the challenge, you cannot write this doc — there is nothing to cite.

---

## Step 1 — Pick a real product (not a toy)

The decision is meaningless in the abstract. Choose a **concrete product with a concrete traffic shape**, and write it down at the top of the doc. Pick one of these, or bring your own (real or from a previous job, anonymized):

- **A.** A B2B SaaS API for a mid-market HR tool. ~2M requests/day, business-hours-heavy (10× peak/trough), p99 budget 250 ms, one 4-person platform team, cost-sensitive but not desperate.
- **B.** A consumer mobile-app backend. ~50M requests/day, diurnal but global (flatter than B2B), p99 budget 150 ms, a 12-person backend org already running other services on Kubernetes.
- **C.** An internal data-processing API hit by a nightly batch and almost nothing during the day. ~500K requests/night in a 2-hour window, otherwise idle, p99 irrelevant (batch), one part-time owner.
- **D.** A webhook-ingest endpoint for a payments integration. Spiky and unpredictable (0 to 5K req/s in seconds when a partner replays events), strict idempotency, a small team.

Each of these has a *different right answer*, and the differences are exactly the axes from Lecture 1: traffic shape (spiky vs steady), scale (2M/day vs 50M/day), p99 budget, team size and existing platform investment, and idle fraction. Name your product, name its numbers, and the rest of the doc writes itself from the benchmark.

---

## Step 2 — Map your benchmark onto the product

Your Challenge 1 table measured the *same code* on the three platforms. Now project it onto your product's actual traffic:

- Take your **measured warm p50/p99** and check it against the product's p99 budget. Does Lambda's cold-start p99 violate the budget given the product's traffic shape (i.e., how often will a request hit a cold environment)?
- Take your **per-1M-request cost** and multiply by the product's monthly request volume. For Fargate and EKS, compute how many tasks/nodes the peak concurrency requires, and price the *fleet*, not one task.
- For EKS, decide honestly whether the **$73/month + operational owner** is amortized. Product B (12 engineers already on k8s) amortizes it trivially; Product A (4-person team, no existing cluster) does not.
- For the spiky products (C, D), weight the **idle cost** heavily — Lambda's $0-idle is worth real money when the thing is idle 22 hours a day.

Write these projections into `benchmark.md`. The decision doc then *cites* them.

---

## Step 3 — Write the decision doc

`decision.md` follows this structure. Keep it to one page.

### Required sections

1. **Product & constraints (3–5 bullets).** The named product, its request volume, traffic shape, p99 budget, team size, and existing platform investment. Numbers, not adjectives.
2. **Recommendation (1–2 sentences).** "We recommend **X** for this workload." Lead with the answer. A reviewer should know your pick from the first line.
3. **The reasoning (2–3 short paragraphs), each tied to a number from your benchmark.**
   - The **cost** argument: cite your per-1M figure × the product's volume, and the fleet/idle math.
   - The **latency** argument: cite your p50/p99 against the budget, and address cold start explicitly for the spiky/idle products.
   - The **operational-burden** argument: who owns it, what they have to patch/upgrade/debug, and whether the team already carries that burden.
4. **What we rejected and why (2–3 bullets).** For each platform you did *not* pick, one sentence on the specific number or constraint that ruled it out. "Rejected EKS: at 2M req/day on a 4-person team with no existing cluster, the $73/mo control-plane fee plus a Karpenter/IRSA/LB-Controller operational owner is not justified by the per-unit savings, which our benchmark shows only materialize past ~20 services."
5. **Reversal conditions (the section reviewers actually grade, 2–4 bullets).** What would change this decision? "If request volume crosses ~30M/day, re-run the math: Fargate's per-request cost stops falling once we saturate tasks, and EKS-on-Spot's per-unit cost overtakes it." "If we adopt Kubernetes for two other services, the EKS amortization flips and this workload should move onto the shared cluster."
6. **The benchmark table.** Paste the Challenge 1 table inline (it is the evidence). Link to `benchmark.md` for the raw numbers and arithmetic.

### Voice

Write it the way a senior engineer writes a design-review doc: opinionated, concrete, no hedging without a reason, and every claim load-bearing with a number. Banned phrases: "it depends" (without saying *on what, quantitatively*), "best practices," "industry standard," "scalable" (as a standalone virtue — scalable to *what*, at *what cost*). If you delete a sentence and the recommendation is unchanged, the sentence was filler.

---

## Acceptance criteria

The rubric is below. Each box maps to a deliverable.

### The decision (40%)

- [ ] `decision.md` names a **specific product** with **quantified** constraints (volume, traffic shape, p99 budget, team size, existing platform).
- [ ] It leads with a **clear recommendation** in the first one or two sentences.
- [ ] Each of the three reasoning paragraphs (cost, latency, ops) cites at least one **number from your own benchmark**, not a generic claim.
- [ ] It is **one page** (~600–900 words plus the table). Over-length is a fail; this skill is partly editing.

### The evidence (35%)

- [ ] `benchmark.md` contains the **three-way comparison table** from Challenge 1 with *your* measured numbers.
- [ ] It shows the **cost projection onto the product's volume** (per-1M × monthly volume, fleet sizing, idle weighting) — not just the raw per-1M figure.
- [ ] It includes at least one **"forgotten" cost line** (NAT, ALB LCU, EKS control-plane fee, or log ingestion) in the arithmetic.
- [ ] Cold start is reported **separately** from steady-state percentiles for all three platforms.

### The defense (25%)

- [ ] The **"what we rejected"** section gives a specific, numeric reason for each platform not chosen.
- [ ] The **"reversal conditions"** section names at least two concrete thresholds (a request volume, a team-size change, a latency requirement) that would flip the decision, each tied to a mechanism in your benchmark.
- [ ] A peer reviewer reading only `decision.md` could restate your recommendation, your top reason, and the one condition that would change your mind.

---

## Worked example of the *shape* (not the answer)

So you know the altitude expected, here is the *opening* of a strong doc for Product D (the spiky payments webhook) — your product and numbers will differ:

> **Recommendation:** Lambda + API Gateway, with reserved concurrency capped at 200 and a DLQ on the async path.
>
> **Why.** This endpoint is idle 22 hours a day and spikes to 5K req/s without warning. Our benchmark puts Lambda at ~$1.0/1M requests and **$0 when idle**; at this product's ~30M requests/month that is ~$30/month of compute, versus ~$35–40/month for a *single always-on* Fargate task that would still need autoscaling headroom for the 5K-req/s spike — and would be paying for that headroom during the 22 idle hours. Lambda absorbs the spike natively by scaling concurrency; Fargate would need pre-provisioned tasks or eat a cold-scale latency cliff exactly when the partner replays events.
>
> **The cold start we are accepting:** our benchmark measured a ~1.2 s container-image init. For a webhook, the partner retries on timeout and we ack idempotently, so a sub-2 s p99 on the first request of a spike is within budget. If it were not, provisioned concurrency (priced at ~$X/mo for 5 warm envs in `benchmark.md`) buys it down.

Notice every sentence carries a number, the rejected option is dispatched with a specific cost comparison, and the cold-start risk is named and bounded rather than hidden. That is the bar.

---

## What the right answer looks like for each sample product

You will not be graded on picking the "correct" platform — there isn't one — but on whether your reasoning is honest and numeric. Still, it helps to see the *shape* of a defensible call for each sample product, so you know whether your own reasoning is in the right neighborhood. (These are sketches of the argument, not answers to copy. Your benchmark numbers drive the real decision.)

- **Product A (B2B SaaS, 2M/day, 4-person team).** The honest call is usually **Fargate**. Business-hours traffic with a 10× peak/trough means scale-to-zero isn't worth much (it's busy all workday), but a 4-person team with no existing cluster cannot justify EKS's control-plane fee *plus* an operational owner for three services. The reversal: if the org adopts Kubernetes elsewhere, the EKS amortization flips. Lambda is plausible if the p99 budget (250 ms) tolerates cold starts at the traffic's idle edges — check your measured cold-start number against how often a request lands cold.
- **Product B (consumer mobile, 50M/day, 12-person k8s org).** The honest call is usually **EKS**. At 50M/day the control-plane fee is rounding error, the team already pays the k8s operational tax, and Karpenter-on-Spot delivers the lowest per-unit cost your benchmark measured. Fargate is the runner-up and you dispatch it on per-unit cost at this volume. Lambda loses on sustained-busy per-ms economics — show the figure.
- **Product C (nightly batch, idle all day).** The honest call is usually **Lambda** (or **AWS Batch** if jobs exceed 15 min or need GPU). 22 hours idle makes Lambda's $0-idle decisive; a Fargate task or EKS node sitting idle all day is pure waste. The reversal: if the nightly window's concurrency exceeds Lambda's account limits, or a single job exceeds 15 minutes, move to Batch on a Spot compute environment.
- **Product D (spiky payments webhook).** The honest call is usually **Lambda** with reserved concurrency and a DLQ — see the worked example below. The spike-from-zero shape is exactly what Lambda absorbs and what Fargate/EKS handle worst without pre-provisioned headroom you pay for during the 22 idle hours.

Notice the pattern: **traffic shape decides idle-vs-busy, scale decides per-unit economics, and team size decides whether the EKS operational tax is already paid.** Your benchmark supplies the numbers; these three axes supply the structure.

## The five sentences of a defensible decision

Every strong compute decision doc, regardless of product, can be compressed to five sentences. If you cannot write these five, you do not yet have a decision — you have a preference. Draft them *before* you write the prose; the prose is just these five sentences with the evidence attached.

1. **The pick.** "For `[product]` at `[volume / traffic shape]`, we run it on `[platform]`."
2. **The dominant reason.** "The deciding factor is `[cost | latency | operational burden]`, because `[one number from the benchmark]`."
3. **The dispatched alternative.** "We did not pick `[runner-up]` because `[the specific number that ruled it out]`."
4. **The accepted risk.** "We are accepting `[cold start | per-request cost at scale | ops burden]`, bounded by `[mitigation and its cost]`."
5. **The reversal.** "We revisit this if `[a measurable threshold]` crosses `[a value]`, because `[the mechanism in the benchmark that flips]`."

A reviewer who reads only those five sentences should be able to nod. If sentence 2 has no number, you are hand-waving. If sentence 5 is missing, you wrote a bet, not a decision.

## Common failure modes (how this gets marked down)

These are the recurring ways the doc fails review. Read them before you write so you don't ship one.

- **The cost figure doesn't match the benchmark.** The doc claims "~$30/month" but `benchmark.md` computes $44 once the ALB and log ingestion are included. Every number in `decision.md` must trace to `benchmark.md`. Graders check this first.
- **Cold start hidden inside the p99.** You report "Lambda p99 = 9 ms" but the raw run included a 1.2 s cold start that you averaged away. Cold start is always its own number, reported separately, for all three platforms.
- **EKS priced for one service only.** The control-plane fee makes EKS look absurd at one service — but the *product* might justify a shared cluster. Show both the one-service number and the amortized number, then state which applies to *this* product and why.
- **No reversal conditions.** The single most common fail. A decision without "what would change my mind" is graded as an opinion. Name at least two thresholds, each tied to a mechanism (not "if it gets bigger" — *how much* bigger, and *what* in the benchmark flips).
- **Adjectives doing a number's job.** "Highly scalable," "very cost-effective," "production-grade." Delete every one and replace it with the figure it was standing in for. If there's no figure, the claim wasn't real.
- **The runner-up dispatched with a vibe.** "We didn't pick EKS because it's complex." Complex *how*, costing *what*? Dispatch it with the specific number or constraint, the way the worked example does.

## Pre-flight checklist (before you write a word)

Confirm you have the raw material. If any box is empty, go get the number — do not write around the gap.

- [ ] Three working deployments existed and you captured **warm p50/p99** for each (Challenge 1).
- [ ] You have a **median cold start** for each platform, measured separately from the warm path.
- [ ] You have **per-1M-request cost** for each platform, including at least one "forgotten" line item.
- [ ] You have the **EKS cost both ways** — one service and amortized across a fleet.
- [ ] You picked a **named product** with quantified constraints (volume, traffic shape, p99 budget, team size, existing platform).
- [ ] You projected the benchmark onto that product's **actual monthly volume and peak concurrency** (fleet sizing, not one task).

## How this maps to the capstone

This is not a throwaway exercise. The capstone's required architecture has a **compute-hybrid layer**: EKS with Karpenter Spot nodes for batch and long-running tasks, ECS Fargate for one stateful sidecar, and Lambda for the event-handler layer — all behind one CloudFront distribution. The capstone does not let you put everything on the platform you like; it forces a per-workload decision, and your capstone defense will include questions of the exact shape this doc rehearses: "why is the event handler on Lambda and not a Fargate consumer?" "at what volume would you move the batch layer off EKS?" The IRSA role you scoped in Exercise 2 and the decision frame you build here are the literal inputs to that layer. Treat this mini-project as the first draft of three paragraphs you will defend out loud in Week 15.

## Submission

Push to your Week 5 repo at `mini-project/`:

- `decision.md` — the one-page decision doc.
- `benchmark.md` — the supporting benchmark and cost arithmetic.

The instructor reviews by reading `decision.md` first (and grading whether it stands alone), then checking that every number it cites traces to `benchmark.md`, then spot-checking that `benchmark.md`'s numbers are consistent with the raw output from Challenge 1. The most common review-fail: a confident recommendation whose cited cost figure does not match the benchmark, or a missing reversal-conditions section. Decisions without reversal conditions are not decisions; they are bets.

**Before you log off:** confirm `aws eks list-clusters` is empty and your Fargate service desired-count and the CloudFront distribution are torn down. The decision doc does not require the infrastructure to stay running — only the numbers, which you have already captured.

---

## FAQ

**"My benchmark numbers don't match Lecture 1's headline figures. Did I do it wrong?"**
Probably not. Lecture 1's numbers are illustrative `us-east-1` list prices for a specific made-up workload; your region, your instance choices, your measured durations, and your request mix will differ. The grade is on whether *your* numbers are internally consistent and your arithmetic is shown — not on matching the lecture. If anything, numbers that differ and that you can *explain* are stronger evidence you measured rather than copied.

**"Can I recommend two platforms (e.g. Lambda for reads, Fargate for writes)?"**
Yes, and for some products that *is* the right answer — it's literally what the capstone's compute-hybrid layer does. But then your doc must (a) draw the split at a clear boundary (which workload, why), and (b) justify the operational cost of running two platforms instead of one. A split recommendation that doesn't acknowledge the added operational surface is weaker than a clean single pick.

**"What if the honest answer is 'it depends'?"**
Then say *on what, quantitatively*. "It depends" is banned as a terminal answer but fine as the setup for "it depends on whether daily volume crosses 30M requests; below that, Fargate; above, EKS — here's the crossover math." That's not hedging; that's a decision with a hinge.

**"How long should the benchmark appendix be?"**
As long as it needs to be to let a reviewer redo your arithmetic — no longer. The *decision* is one page and that limit is enforced. The *benchmark* is an appendix and has no length limit, but padding it doesn't help; a tight, reproducible appendix beats a sprawling one.

**"I tore down my infrastructure. Can I still write the doc?"**
Yes — the doc requires the *numbers*, which you captured in Challenge 1, not the running infrastructure. In fact you *should* have torn it down (the EKS control plane bills idle). The submission checklist explicitly confirms teardown.

## Grading walkthrough (what the reviewer does, in order)

So there are no surprises, here is the exact path a reviewer takes:

1. **Read `decision.md` alone, cover the rest.** Can they restate your pick, your top reason, and your one reversal condition from this file only? If not, the doc fails the "stands alone" bar (this is the 25% defense weight).
2. **Trace every number.** For each figure cited in `decision.md`, find it in `benchmark.md`. A figure that doesn't trace is a fabrication and zeroes the evidence section.
3. **Spot-check the arithmetic.** Pick one platform's cost line in `benchmark.md` and redo it from the cited 2026 prices. If it's off by more than rounding, the evidence section loses points.
4. **Check for the forgotten line.** Is NAT, LCU, control-plane fee, or log ingestion in the cost math? A compute-only cost model is the most common evidence fail.
5. **Check the reversal conditions.** Are there at least two, each a measurable threshold tied to a benchmark mechanism? "If it gets bigger" doesn't count.

Optimize for that path. A doc that survives step 1 and step 5 is most of the grade.

## Stretch (no extra grade)

- Write a **second** decision doc for a *different* product from the list and watch the recommendation flip on the same benchmark. The discipline of "same data, different right answer" is the whole point of the week.
- Add a **fourth platform** (AWS Batch for Product C's nightly batch) to the benchmark and the doc.
- Add a **"two-year TCO"** projection that includes the engineer-hours of operating each platform, not just the AWS bill. For a 4-person team, the human cost of operating EKS often dwarfs the control-plane fee — make that explicit with an hourly rate and an honest estimate.
