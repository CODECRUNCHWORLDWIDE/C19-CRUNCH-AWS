# Lecture 1 — Defending the Capstone: How the Review Runs and the Questions You Will Be Asked

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you assemble your one-event walk and your cost-per-request number, the two artifacts the oral is built around).

This is the lecture about the thing the whole course was for. You have built the Event-Driven SaaS Backbone over three capstone weeks. This week you stand in front of two peers and one lead reviewer and *defend* it — a 30-minute oral where you walk a single request through the system and answer the questions a senior reviewer asks when they are deciding whether to trust your design in production. The lecture has one job: to make that 30 minutes feel like a conversation you are ready for rather than an ambush. We will cover how a real architecture review actually runs, the artifacts the reviewer expects in front of them, the exact question set a senior engineer reaches for, and the cost-per-request math you must be able to produce on demand. The chaos drill (Lecture 2) gives you the failure data; this lecture teaches you to present it.

## 1.1 — What an architecture review is, and what it is not

A junior engineer thinks an architecture review is a presentation: you show slides, the reviewer nods, you pass. That is not what it is. **An architecture review is an adversarial collaboration whose output is a list of risks and a decision about whether the design is safe to operate.** The reviewer is not there to admire your diagram. They are there to find the thing that pages someone at 3 a.m., the data-loss window you did not notice, the single point of failure you drew as redundant, and the bill that doubles when you 10x the traffic. Their job is to find those *before* production does. Your job is to have already found them.

This reframes how you prepare. You do not prepare to *defend* in the sense of deflecting; you prepare to *own*. The strongest thing you can say in a review is "yes, that is a weakness — here is the blast radius, here is why I accepted it, and here is the mitigation if it gets worse." A reviewer who hears that trusts you more than one who hears "no, that can't happen" — because the second answer is almost always wrong, and the reviewer knows it. The senior skill being graded is *calibrated honesty about your own system*: knowing exactly where it is strong, exactly where it is weak, and being able to say so with a number attached.

A review is also not a pass/fail quiz with a hidden answer key. There is rarely one right architecture. The reviewer is testing whether you understand the *trade-offs you took* — not whether you took the trade-offs they would have taken. If you chose DynamoDB single-table over Aurora for the transactional state, the reviewer does not care that they would have chosen Aurora; they care that you can articulate *why* DynamoDB, what it costs you (the read patterns you gave up, the operational simplicity you gained), and when you would revisit the choice. A defensible decision you can disagree with beats an "optimal" decision the author cannot explain.

## 1.2 — The agenda: how the 30 minutes is spent

A well-run review has a shape. The cohort oral follows it, and so does a real operational-readiness review at a serious company. Here is the agenda, with the minutes:

1. **Context and one-line spec (2 min).** You state, in one sentence, what the system does and for whom. "A multi-tenant event-driven SaaS backbone: tenants send events over an HTTP API, the system processes them through an EventBridge spine into DynamoDB and an analytics lake, and serves a recommendation feature from a SageMaker endpoint." No diagram yet. If you cannot say it in a sentence, you do not understand it yet.

2. **The architecture diagram and the request walk (8 min).** You put up *one* diagram and walk a *single* request through it end to end. This is the heart of the review and the subject of §1.3. You do not enumerate every service; you trace one event from the edge to its resting place and back, naming each hop and what could go wrong at it.

3. **Failure modes and the chaos-drill results (8 min).** You present what you broke on purpose and what happened. The AZ-failover recovery time against your RTO. The DynamoDB throttle and its mitigation. The Lambda concurrency exhaustion and where the back-pressure landed. This is where the postmortem from Lecture 2 earns its keep — you are not speculating about failure, you have *measured* it.

4. **Cost (4 min).** The weekly dollar figure, the per-request cost, the idle bill, and the three optimizations you would make first. §1.6.

5. **Q&A — the reviewer drives (8 min).** The reviewer picks at whatever the first 22 minutes left exposed. This is the part you cannot script, but §1.4 and §1.5 are the questions they will almost certainly ask, so you can rehearse the answers.

Notice the proportion: roughly half the time is the request walk and the failure modes. A review that is all diagram and no failure data is a junior review. The reviewer learns more from "here is what happened when I killed an AZ" than from any architecture slide.

## 1.3 — The single-event walk: the most important eight minutes

The request walk is where you prove you understand your own system as a *running thing* and not a diagram. You take one concrete request — a tenant POSTing one event — and you narrate its entire journey, naming every hop, the failure mode at each hop, and the observability that would tell you it failed. For the capstone, the walk goes roughly:

1. **Edge.** The request hits CloudFront. WAF evaluates it against the managed rule groups and your custom rate-limit rule. *Failure mode:* a malformed or abusive request is blocked here — show where you'd see the WAF block count. A CloudFront Function rewrites a header; Lambda@Edge injects the tenant ID from the signed cookie. *Failure mode:* a Lambda@Edge error fails the request at the edge — and Lambda@Edge errors are *hard* to debug because the logs land in the Region nearest the viewer, not your home Region. Name that.

2. **API layer.** CloudFront routes to the API Gateway HTTP API (for CRUD) or the ALB in front of EKS (for long-lived work). *Failure mode:* API Gateway throttles at its account/stage limit; the ALB returns 503 if no healthy EKS targets. Show the metric for each.

3. **Compute.** API Gateway invokes the handler Lambda. *Failure mode:* cold start adds latency; reserved concurrency exhaustion returns a 429 (this is the drill you ran). The Lambda validates, writes to DynamoDB, and publishes to the EventBridge custom bus.

4. **The event spine.** EventBridge routes the event by rule to its targets: an SQS queue (with a DLQ) for retry-able work, a Step Functions Express execution for orchestration, and Kinesis Firehose for the analytics tap to S3. *Failure mode:* a poison-pill message exhausts its retries and lands in the DLQ — show the DLQ depth alarm. EventBridge's archive lets you replay.

5. **Data at rest.** DynamoDB single-table holds transactional state; a Stream fans out changes to a Lambda; the change replicates to the second Region via Global Tables. Aurora Postgres (multi-AZ writer + cross-region read replica) holds analytical state. *Failure mode:* a hot partition throttles DynamoDB (the drill); the Aurora writer fails over to a standby AZ (the AZ drill); the cross-region replica's replication lag *is* your RPO — name the number.

6. **The inference path and the response.** The recommendation Lambda invokes the SageMaker real-time endpoint (Path A) and Bedrock Claude (Path B), and the response flows back out through CloudFront. *Failure mode:* the SageMaker endpoint's single instance is a SPOF unless you ran ≥2 across AZs — a reviewer *will* catch this if you didn't.

The discipline: **at every hop, name the failure mode and the signal.** "Here is where it breaks, and here is the metric or trace that tells me it broke." A walk that names hops but not failures is a tour, not a defense. A walk that names failures and signals is the thing that earns a reviewer's trust.

There is one more thing the walk must demonstrate, and it is the thing that ties the whole Week-12 observability investment together: **trace correlation**. The reason you can narrate a single request across six hops is that one trace ID, propagated by OpenTelemetry from the edge through every Lambda, EKS pod, and the SageMaker call, stitches the hops into one timeline in X-Ray. When a reviewer asks "how would you actually debug a slow request in production?", the answer is "I pull its trace — the trace ID is in the access log and the response header — and X-Ray shows me exactly which hop spent the time." Without trace correlation, a distributed request is six disconnected log streams you grep by timestamp and hope; with it, it is one waterfall you read at a glance. The single-event walk is, in effect, you reading that waterfall out loud. If your capstone's traces *don't* correlate end to end (a common gap when the ADOT context propagation isn't wired through every hop), the walk exposes it — which is itself a finding worth surfacing before the reviewer does.

A subtle point that separates seniors: the walk should also name the hops where you *deliberately broke* the trace for a reason. EventBridge and SQS are asynchronous boundaries; a synchronous trace ends at the publish and a *new* trace (linked by the event's correlation ID, carried in the event payload) begins at the consumer. You do not pretend the async hop is one synchronous trace; you explain that you carry the correlation ID through the event so the two traces *link*, and you can follow a request across the async boundary even though it is two traces, not one. Naming that — synchronous tracing up to the bus, correlation-ID linking across it — is the kind of detail that tells a reviewer you understand distributed tracing's real boundaries, not just the happy-path demo.

## 1.4 — The senior-reviewer question set, part one: reliability

These are the questions a senior reviewer asks about whether the system stays up. Have a one-sentence answer with a number for each, *before* the review.

**"What is the blast radius of your largest single failure?"** The blast radius is how much of the system one fault can take down. The reviewer wants to know you have *thought in blast radii*. Good answer: "The largest single failure is losing the DynamoDB single-table — every write path depends on it. Blast radius is total for writes, but Global Tables gives me a second-Region copy with a few-seconds replication lag, so my mitigation is a Route 53 failover to the second Region with an RPO equal to the replication lag. Reads degrade gracefully because the analytics lake is a separate store." Bad answer: "Nothing is a single point of failure," which is never true and which the reviewer will immediately disprove by pointing at your single SageMaker instance.

**"What are your single points of failure?"** Every system has them; the question is whether you *know* yours. Walk the components that exist exactly once: the EventBridge custom bus (managed, regionally redundant — acceptable), the SageMaker endpoint if you ran one instance (a real SPOF — name it and the fix: ≥2 instances across AZs), the NAT Gateway if you ran one (a SPOF for egress — name the cost trade-off of three vs one). The reviewer is not looking for *zero* SPOFs; they are looking for an author who has *enumerated* them and made a deliberate cost/risk call on each.

**"What is your RTO and RPO, and how do you know?"** This is the question the chaos drill exists to answer. RTO is how fast you recover; RPO is how much data you can lose. The weak answer states targets ("RTO 5 minutes, RPO 1 minute"). The strong answer states targets *and the measurement*: "RTO target 5 minutes; the AZ-failover FIS drill measured actual recovery at 142 seconds. RPO target 1 minute; my Aurora cross-region replica lag runs ~8 seconds at steady state and the DynamoDB Global Table replication is sub-second, so my RPO floor is the replica lag, comfortably inside target." A reviewer trusts a measured number infinitely more than a target.

**"What is your dependency on a single managed-service control plane?"** A sharper reviewer probes a subtler reliability property: the difference between a *data-plane* and a *control-plane* dependency. Your running requests use the data plane (DynamoDB `GetItem`, Lambda invoke, S3 `GetObject`) — historically the most resilient surface in any cloud. But your *recovery* may depend on a control plane (creating resources, changing Route 53 records, scaling an ASG), which can be slower or degraded during a large regional event. The senior answer: "My failover path is data-plane-heavy by design — Route 53 health checks flip traffic without a control-plane call, Global Tables replicate continuously, and the standby is pre-provisioned (warm), so failover does not require *creating* anything mid-incident. The one control-plane dependency I have is promoting the Aurora replica, which I've timed at ~90 seconds, and I documented that as the slowest link in my RTO." Naming the data-plane/control-plane distinction, and architecting your *recovery* to lean on the more-resilient data plane, is a depth signal most cohorts miss — and it is exactly the resilience thinking the AWS Builders' Library articles teach.

**"What is your graceful-degradation story?"** Not every failure should be total. The reviewer wants to know which features *degrade* rather than *break* when a dependency is down. Good answer: "If the SageMaker endpoint is unavailable, the recommend Lambda catches the error and returns a cached or default recommendation rather than a 500 — the feature degrades to 'less personalized' instead of 'down.' If the Bedrock comparison call fails, I drop it silently; it is an enhancement, not a requirement. If the analytics lake write fails, I let it — it is re-derivable. The *core* write path (DynamoDB) is the only thing that, if down, takes the product down, and that is the one I gave the strongest DR." Distinguishing the must-not-fail core from the can-degrade periphery, and matching your reliability investment to that hierarchy, is the reliability-meets-cost judgment a reviewer most wants to see.

**"Walk me through what pages you at 3 a.m."** The reviewer wants your alarm catalog and your on-call story. Name the alarms that page (the 99.9% SLO burn-rate alarm, the DLQ-depth alarm, the Aurora-failover event, the WAF block-rate spike) versus the ones that just ticket (cost anomaly, a single retried message). The senior signal is *alarm discipline*: every page is actionable, nothing pages that a human cannot act on, and the runbook for each page is one click away. If everything pages, nothing does — alarm fatigue is a reliability failure.

## 1.5 — The senior-reviewer question set, part two: correctness, security, and operations

**"Where can you lose or duplicate data?"** Event-driven systems duplicate by default (at-least-once delivery) and can lose data at every hop that lacks a DLQ. The reviewer wants: where is delivery at-least-once (so where do you need idempotency), where is the DLQ that catches what fails, and what is the data-loss window if a component is down. Good answer: "EventBridge and SQS are at-least-once, so every consumer is idempotent via a conditional write on an idempotency key in DynamoDB. Every async hop has a DLQ. The only loss window is if Firehose's buffer is in flight when an AZ drops — bounded by the buffer interval, and it is analytics data I can re-derive, so I accepted it." Naming idempotency-by-design and the bounded loss window is the senior move.

**"Show me the IAM blast radius of your CI role."** A reviewer who has read the Week 7 lecture knows your pipeline IAM role is more dangerous than your prod role, because it can change everything. They will ask what your GitHub Actions OIDC role can do. The right answer is a permission boundary that scopes it, a trust policy locked to your specific repo and branch (`token.actions.githubusercontent.com` with a `sub` condition), and no long-lived keys. If your CI role is `AdministratorAccess` with a wildcard trust, the review fails there regardless of how good the architecture is.

**"What is the least-privilege story for the request path?"** Pick any Lambda and show its execution role. It should grant exactly the actions it needs on exactly the resource ARNs it touches — `sagemaker:InvokeEndpoint` on the one endpoint, `bedrock:InvokeModel` on the one model and inference profile, `dynamodb:PutItem`/`Query` on the one table. A `Resource: "*"` anywhere on the request path is a finding. (This is the same standard every IAM review in Weeks 2, 5, and 13 held you to; the capstone is where it compounds.)

**"How do you deploy a change safely?"** The operational-excellence question. Walk the pipeline: lint → test → CDK synth → a blue/green or canary deploy with automatic rollback on a CloudWatch alarm. Name the rollback trigger (the SLO burn-rate alarm) and the blast radius of a bad deploy (one canary's worth of traffic, not all of it). "I deploy on Friday at 5 p.m. with no canary" is the wrong answer, and the reviewer is listening for it.

**"What happens when you 10x the traffic?"** The scaling question. The reviewer wants you to find your own bottleneck. For the capstone it is usually one of: DynamoDB hot partitions (mitigated by write-sharding and on-demand mode), Lambda reserved concurrency (the drill showed you the ceiling), the SageMaker endpoint's instance count (fixed unless you added auto-scaling), or the Aurora writer (vertical-scale only for writes). Name *which* bends first and what you'd do — that is the answer of someone who has load-tested, not guessed.

## 1.6 — The cost-per-request math you must have ready

A senior reviewer always asks about cost, because in 2026 "it works" is table stakes and "it works and you can defend the bill" is the bar. You need three numbers at your fingertips, and a fourth derived from them.

**The weekly bill.** The actual dollar figure for one week of capstone operation, from the tagged Cost & Usage Report you built in Week 14. Not an estimate — the number from CUR-in-Athena, broken down by `service` tag. Be able to say "this week cost $X, and the breakdown is: Aurora $a, SageMaker endpoint $b, NAT Gateway $c, everything else $d." If one line item dominates, know *why*.

**The idle bill.** What the system costs per day if *nobody calls it*. This number explains your architecture choices better than anything else. The always-on SageMaker endpoint bills ~$83/month whether or not anyone calls it; the Aurora cluster bills for its provisioned capacity at idle; the NAT Gateway bills ~$32/month plus data for existing. The idle bill is why you destroy the endpoint nightly in non-prod, and the reviewer wants to hear that you know it.

**The per-request cost.** The weekly bill divided by the week's request count. This is the unit economic. "At current traffic each request costs $0.0004; at 10x traffic the fixed costs (Aurora, the endpoint, NAT) amortize, so per-request cost *falls* to $0.00008 — my architecture gets cheaper per unit as it scales, which is the property you want." Being able to say whether your per-request cost rises or falls with scale is the FinOps maturity signal.

**The break-even and the three optimizations.** From the per-request and idle numbers, name the three optimizations you would commit first and *why those three*. Almost always: (1) move steady-state compute to **Graviton/arm64** for ~20% off at zero code change; (2) commit a **Compute Savings Plan** for the steady-state baseline you will run regardless, trading flexibility for ~30-40% off; (3) kill the single biggest idle cost — usually the always-on SageMaker endpoint (move to serverless or Bedrock below the break-even traffic from Week 11) or the NAT Gateway (replace egress with VPC endpoints, the Week 4 trick). Naming three with a dollar estimate each is the cost-defense memo, which is also a homework deliverable.

A worked per-request calculation you can adapt — pull the real numbers from your own CUR and the live pricing pages:

```
weekly_bill            = $48.20   (from CUR-in-Athena, tagged by service)
requests_this_week     = 1,250,000
per_request_cost       = $48.20 / 1,250,000 = $0.0000386 per request

idle_daily_bill        = SageMaker endpoint  ($83/mo  ≈ $2.77/day)
                       + NAT Gateway          ($32/mo  ≈ $1.07/day)
                       + Aurora provisioned   (~$1.50/day at min ACU)
                       ≈ $5.34/day with zero traffic

# The idle bill is ~$37/week of the $48 weekly bill -> the system is
# ~77% fixed cost. That tells the reviewer: at low traffic you are paying
# for capacity, not usage. The first optimization (kill the idle endpoint)
# saves more than any per-request tuning.
```

The point is not these specific numbers — they are illustrative. The point is the *shape* of the reasoning: a weekly bill from real data, a per-request unit cost, an idle floor, and a ranked list of optimizations with dollars attached. That is what a senior reviewer means by "defend the cost."

A subtlety the strongest defenses include: the cost-per-request shape interacts with the reliability posture. A warm-standby DR posture (a running Aurora replica, a second-Region SageMaker endpoint) lowers your RTO but raises your idle bill; a backup-and-restore posture is nearly free at idle but has an RTO measured in hours. The reviewer wants to hear that you *chose* your point on that curve deliberately: "I run a cross-region read replica (warm) for the analytical store because a multi-hour RTO there is unacceptable, but I accept backup-and-restore for the cold lake because re-deriving it is cheap. That choice costs me ~$X/month and buys me an RTO of minutes instead of hours where it matters." Naming the cost of your DR posture, and why you bought it *there* and not elsewhere, is the senior FinOps-meets-reliability move that ties the cost answer back to the reliability answer.

## 1.7 — A worked failure narration: tracing a real incident through the system

The request walk (§1.3) traces a *healthy* request. The strongest defenses also rehearse a *failing* one — narrating a concrete incident end to end, because that is what a reviewer's "walk me through what pages you at 3 a.m." question is really asking. Here is the shape, using the DynamoDB hot-partition incident the chaos drill produces:

```
14:02:10  A tenant's bulk-import job hammers one partition key (all writes
          share PK=TENANT#noisy-neighbor). DynamoDB begins throttling that
          partition with ProvisionedThroughputExceededException.

14:02:14  The event-handler Lambda's writes to that PK start failing. Because
          the consumer is idempotent and the SDK retries with backoff, the
          first few throttles are invisible — back-pressure, not errors yet.

14:02:25  Retries exhaust. Failed events route to the SQS retry queue. The
          retry queue's depth climbs. SIGNAL: the "retry-queue-depth" alarm
          ticks toward its threshold (this tickets, it does not page yet).

14:02:40  The retry consumers also hit the hot partition and fail. Events
          that exhaust the retry policy land in the DLQ. SIGNAL: the
          "dlq-not-empty" alarm fires -> THIS PAGES. On-call is now engaged.

14:02:45  Crucially: the rest of the table is UNAFFECTED. Other tenants'
          writes (different partition keys) succeed normally. The blast
          radius is one tenant, not the system. SIGNAL: the per-tenant
          error-rate panel shows one tenant red, the rest green.

14:05:00  On-call follows the runbook playbook "DynamoDB hot partition":
          confirm the offending PK from the throttle metric's dimension,
          and (the prepared mitigation) the import path is switched to the
          write-sharded key form (PK=TENANT#noisy-neighbor#<0-15>), spreading
          the writes across 16 logical partitions.

14:06:30  Throttles drop to zero. The retry queue drains. The DLQ is
          reprocessed (a runbook step re-drives the DLQ once writes succeed).
          No data lost — every event was held, not dropped. RECOVERED.
```

Walking *that* in the review proves three senior things at once: you know the **blast radius** (one tenant, because the partition isolates the fault), you know the **signal at each stage** (which alarm tickets vs. pages), and you have a **prepared mitigation in a runbook** (write-sharding) rather than improvising at 3 a.m. A reviewer who hears this incident narrated cleanly stops worrying about whether you can operate the system. Rehearse one healthy walk *and* one failure walk; the failure walk is where the trust is won.

## 1.8 — The 10-minute walkthrough video and the portfolio

The capstone deliverable includes a 10-minute public walkthrough video, and it is not busywork — it is the artifact a hiring manager actually watches, and it doubles as the rehearsal for your live defense. Treat it as a deliberate piece of communication.

**What to show.** The one-screen diagram, the single-event walk on the *running* system (hit the API, show the request flow through your dashboards and traces), one chaos drill's before/after (inject the fault on camera, show the dashboard react, show the recovery), and the cost number. That is the whole story: it works, it is observable, it survives a fault, and you can defend the bill — in ten minutes.

**What to skip.** Do not narrate every line of CDK. Do not read the IAM policies aloud. Do not explain what DynamoDB *is* — your audience knows; explaining basics signals junior. Skip anything that is not "here is the system doing its job, and here is the trade-off I took."

**How to trace one event on camera.** The single most compelling ten seconds of any capstone video is watching one request you fire from the terminal appear, in real time, as a trace in X-Ray spanning CloudFront → Lambda → DynamoDB → the endpoint, and a metric tick on the dashboard. It proves the observability is real and that you understand your own system as a running thing. Practice this until it is smooth; it is worth more than any slide.

The portfolio repo around the video matters too. A README that opens with the one-line spec, the diagram, and a "deploy it yourself" section (the exact `cdk deploy --all` commands) tells a reviewer the system is reproducible. The `/runbook` with the postmortems and the cost-defense memo tells them you operate it, not just built it. This repo is the thing you point an interviewer at when they say "tell me about something you built" — make it the strongest single artifact in your portfolio, because for most of the cohort it will be.

## 1.9 — Walking the capstone through the five Well-Architected pillars

The same question set, organized differently, *is* the AWS Well-Architected review — the five-pillar lens that both your capstone defense and the AWS-shop system-design interview score against. A senior reviewer (and an AWS-shop interviewer) often runs the review pillar by pillar. Be able to walk your capstone through all five, with one concrete artifact per pillar:

**Operational Excellence.** "How do you operate this?" Your answer is the runbook: the alarm catalog, the top-10 incident playbooks, the on-call rotation template, the dashboards-as-code, and the safe-deploy pipeline (canary + alarm-based rollback). The artifact: point at `/runbook` and the CloudWatch dashboards defined in CDK. The anti-pattern the reviewer probes for is "we operate it by SSHing in and reading logs" — manual operations that do not scale and are not reproducible.

**Security.** "Who can do what, and how is data protected?" Your answer: IAM Identity Center for humans, Cognito for end users, IRSA on EKS and scoped execution roles on Lambda, permission boundaries on every developer role, KMS-CMK encryption everywhere, Secrets Manager (not env vars) for secrets, and the GuardDuty/Security Hub/Macie/Inspector baseline. The artifact: show one request-path Lambda's least-privilege role and the CI role's OIDC trust scoped to repo/branch. The anti-pattern: a `Resource: "*"` on the request path or `AdministratorAccess` on CI.

**Reliability.** "Does it stay up, and how do you know?" Your answer is the chaos drill: the measured AZ-failover RTO, the DynamoDB-throttle graceful degradation, the Lambda-concurrency back-pressure, the multi-AZ + cross-region DR posture, and the DLQ on every async hop. The artifact: the three postmortems with measured timelines. The anti-pattern: a documented RTO you never tested.

**Performance Efficiency.** "Does it perform, and does it scale?" Your answer: the right compute for each workload (Lambda for the event handler, EKS Spot for batch, Fargate for the stateful sidecar), DynamoDB single-table for low-latency transactional reads, the SageMaker endpoint for single-digit-ms inference, and the bottleneck you found under load (the 10x-traffic answer). The artifact: a load-test result showing p50/p99 at your target RPS. The anti-pattern: "we haven't load-tested it."

**Cost Optimization.** "Can you defend the bill?" Your answer is the cost-defense memo: the weekly bill from the tagged CUR, the idle bill, the per-request cost, and the three ranked optimizations (Graviton, a Savings Plan, killing the idle endpoint). The artifact: `COST-DEFENSE.md`. The anti-pattern: "I don't know what it costs."

If you can walk all five pillars with a concrete artifact each, you have not only passed the defense — you have rehearsed the AWS-shop system-design interview, because the rubric is identical.

## 1.10 — The two system-design interview variants

The syllabus's career pack drills two interview variants, and they probe for different things. Knowing which one you are in changes how you answer.

**The AWS-shop variant.** The interviewer expects explicit Well-Architected framing. They are testing whether you can take a vague product requirement ("design a multi-tenant event ingestion service") and decompose it into AWS primitives with the trade-offs named: API Gateway vs ALB at the edge, Lambda vs Fargate vs EKS for compute, DynamoDB vs Aurora for state, EventBridge vs SQS vs Kinesis for the spine — and then defend each choice on the five pillars. The capstone *is* this interview's answer; you have already built and defended exactly this. The move: state the requirement back, sketch the topology, name the trade-off at each fork, and close with the reliability and cost story. The interviewer is reassured by "I'd use DynamoDB single-table here because the access patterns are known and I want single-digit-ms reads at any scale; I'd accept the rigid query model and revisit if the access patterns proliferate."

**The FAANG-shop variant.** The interviewer wants generic distributed-systems reasoning with AWS as merely one allowed substrate. They are testing the fundamentals beneath the managed services: the back-of-envelope capacity estimate (QPS, storage, bandwidth), the data model and partitioning strategy, the consistency model (strong vs eventual, and where each is acceptable), idempotency under at-least-once delivery, the replication and failover story, and the bottleneck. Naming "DynamoDB" earns nothing here; naming "a partitioned key-value store with a hot-partition mitigation via write-sharding, eventual consistency on the global replica with a bounded staleness window, and idempotent consumers keyed on a dedup token" earns everything. The move: reason from first principles, *then* map to the managed service that implements it. The capstone gave you the first-principles version (you built the idempotency, the sharding, the replication); this interview asks you to articulate it without the brand names.

The shared skeleton of both: (1) clarify the requirement and constraints, (2) a capacity estimate, (3) the high-level topology, (4) the data model and partitioning, (5) the failure and scaling story, (6) the trade-offs you took. The difference is only whether you lead with AWS primitives (AWS-shop) or with distributed-systems concepts that *happen* to be implemented by AWS primitives (FAANG-shop). Practice the same capstone walk in both registers; Saturday's mock interview drills exactly this.

## 1.11 — A worked peer-review template

When you review a peer's capstone, your written deliverable is a risk list scored against the question set. Here is the template — fill one out per peer, and recognize that a *good* review finds real risks, not zero:

```markdown
# Architecture Review — <peer>'s Event-Driven SaaS Backbone

Reviewer: <you> · Date: <date> · Verdict: <go / go-with-conditions / no-go>

## Strengths (2–3)
- <e.g. measured AZ-failover RTO of 142s, comfortably inside the 300s target>
- <e.g. every async hop has a DLQ; consumers are idempotent on a dedup key>

## Risks (the deliverable — find the real ones)
| # | Risk | Pillar | Blast radius | Tag |
|---|------|--------|--------------|-----|
| 1 | SageMaker endpoint runs a single instance in one AZ | Reliability | Recommendation feature down for any AZ event | mitigate-now |
| 2 | CI role trust is repo-wide, not branch-scoped | Security | A compromised feature branch can deploy to prod | mitigate-now |
| 3 | No load test above 2x; 10x bottleneck unknown | Performance | Unknown — that's the risk | mitigate-later |
| 4 | NAT Gateway is single; egress SPOF | Reliability | All private-subnet egress | accept (documented, low-traffic) |

## Questions the author could not answer with a number
- <e.g. "What is the cross-region replica lag (the RPO floor)?">

## Recommendation
<One paragraph: is this safe to operate, and what must change first.>
```

A review whose Risks table is empty did not happen. Every real system has risks; your job as reviewer is to surface them, score them by pillar and blast radius, and tag each one's disposition. That writeup is itself a graded deliverable (the syllabus's "two peer architecture reviews, written, with diagrams").

## 1.12 — The reviewer's own failure modes (so you can recognize them)

A subtle skill this week teaches is recognizing when the *reviewer* is failing, because you will be a reviewer too — you review a peer's capstone. A bad reviewer:

- **Reviews the architecture they would have built**, not the one in front of them. They penalize "you used DynamoDB, I would have used Aurora" instead of testing whether the DynamoDB choice is defensible. Catch yourself doing this.
- **Bikesheds.** They spend the eight minutes of Q&A on the naming convention or the choice of Snappy vs ZSTD and never ask about the data-loss window. The fix: lead with blast radius, SPOFs, and RTO/RPO — the questions that matter — and only then sweat the small stuff if time remains.
- **Asks gotchas instead of risks.** "What's the default DynamoDB partition limit?" is trivia; "what happens to writes when one partition goes hot?" is a risk. A good reviewer asks risks.
- **Lets the author off easy.** A review that finds no risks did not happen. Every real system has risks; a review whose output is "looks great" failed to do its job. As a reviewer, your deliverable is a *written list of risks with severities* — if your list is empty, review again.

When you review your peer, your written output uses the §1.9 template: blast radius, SPOFs, RTO/RPO, data-loss windows, IAM, deploy safety, scaling bottleneck, and cost. Score each, name the risks, and tag them accept / mitigate-now / mitigate-later.

## 1.13 — Running the cohort review: the logistics that make it work

The cohort architectural review is a two-sided exercise: you defend your capstone in front of two peer reviewers and one lead reviewer, and you reviewer another cohort member's. A few logistics separate a review that produces real learning from one that wastes everyone's 30 minutes.

**Send the artifacts before the meeting, not during.** A reviewer who first sees your diagram at minute zero spends the whole review orienting instead of probing. Send the one-screen diagram, the repo link, the three postmortems, and the cost memo *the day before*. The reviewers arrive having already formed their questions. This is exactly how a real operational-readiness review works: the package circulates first, the meeting is the interrogation.

**Assign roles among the reviewers.** With two peers and a lead, split the question set so coverage is complete and no one bikesheds: one peer owns reliability (blast radius, SPOFs, RTO/RPO), the other owns security and cost (IAM, least privilege, the bill), and the lead owns operations and the curveballs (the 3-a.m. walk, the 10x question, safe deploys). Without assigned lanes, three reviewers all ask about the same shiny thing and the data-loss window never comes up.

**Timebox ruthlessly.** The agenda (§1.2) only works if someone holds the clock. The lead reviewer keeps time so the request walk doesn't eat the failure-modes section. When the author runs long on the diagram — and they always want to — the lead moves them on. The eight minutes of Q&A is the most valuable part; protect it.

**Capture the risks in writing, live.** One reviewer (or the lead) fills the §1.11 risk table *during* the review, not from memory afterward. The author leaves with a written risk list — their action items — and the reviewer's writeup is the graded deliverable. A review whose findings live only in people's heads evaporates by Monday.

**Receive feedback like an engineer, not a defendant.** When a reviewer finds a real risk, the correct response is "good catch — let me write that down," not an argument. You are not on trial; you are getting free senior review of your system. The author who argues every finding learns nothing; the author who captures them all and triages later gets the full value of three experienced people looking at their work. Defend your *decisions* (the trade-offs you took on purpose); accept your *risks* (the weaknesses you hadn't mitigated).

## 1.14 — Assembling your defense this week

Concretely, before Friday's oral, you assemble three artifacts:

1. **One diagram.** Not five — one, that fits on a screen, that you can walk a single request across. If your architecture needs five diagrams to explain, the reviewer's first finding is "this is too complex to operate." Force it onto one canvas with the request path as the spine.

2. **The single-event walk, rehearsed.** Out loud, on a timer, eight minutes, naming every hop's failure mode and signal. Rehearse it until you do not need the diagram to do it — that fluency is what tells a reviewer you operate this system rather than merely built it.

3. **The four cost numbers.** Weekly bill, idle bill, per-request cost, three optimizations. Written down, from real data, ready to recite.

The chaos-drill results (Lecture 2 and the exercises) slot into the failure-modes portion of the agenda. The cert map and interview drills are the career half of the week and the subject of the resources and Exercise 3. But the *defense* — the 30 minutes that the syllabus weights at 10% of the entire course and gates the certificate on — rests on these three artifacts and the question set above. Build them deliberately.

## 1.15 — A worked Q&A: strong answers versus weak ones

The eight minutes of Q&A is where defenses are won and lost, and the difference between a strong and a weak answer is almost always *a number and an owned weakness* versus *a deflection*. Here is the same exchange answered both ways, so you can hear the difference and rehearse the strong register.

**Reviewer: "What's your single biggest single point of failure?"**

> Weak: "I designed it to be highly available, so there isn't really one."
>
> Strong: "The DynamoDB single-table — every write path depends on it. In-Region it's managed and multi-AZ, so the realistic failure is a Region event, not an AZ one. My mitigation is Global Tables replicating to us-west-2 with sub-second lag, and a Route 53 health-checked failover. So the blast radius is total-for-writes *in-Region*, mitigated to an RPO equal to the replication lag — which I measured at under a second — and an RTO bounded by the Route 53 health-check interval. The one I'd flag as not-yet-mitigated is the SageMaker endpoint; I run two instances so it's multi-AZ, but it's single-Region, so a Region failover loses the recommendation feature until the standby endpoint warms. I accepted that because the feature degrades gracefully to a cached default."

The strong answer names the SPOF, the blast radius, the mitigation, the *measured* RPO, and — crucially — volunteers the weakness the reviewer hadn't asked about yet (the single-Region endpoint) along with the deliberate reason it's acceptable. That last move, surfacing your own unmitigated risk before the reviewer finds it, is the single most trust-building thing you can do in a defense.

**Reviewer: "How do you know your idempotency actually works?"**

> Weak: "The consumers are idempotent by design."
>
> Strong: "Each consumer does a conditional `PutItem` on a dedup key derived from the event ID — `attribute_not_exists(PK)` — so a duplicate delivery is a no-op, not a double-write. I proved it in the DynamoDB chaos drill: when throttling forced retries, the retried events re-delivered, and the table's item count matched the unique-event count exactly, with zero duplicates. The postmortem has the before/after counts."

The weak answer asserts a design property; the strong answer names the *mechanism* (the conditional write), the *evidence* (the chaos drill's count match), and the *artifact* (the postmortem). "By design" is what you say when you haven't tested it; "here's the count from the drill" is what you say when you have.

**Reviewer: "This is over-engineered for the traffic you have. Why all this DR?"**

> Weak: "The capstone spec required it."
>
> Strong: "Fair — for current traffic the warm cross-region posture is more than the workload needs, and it's ~$X/month of my idle bill. I built it to *demonstrate* the DR patterns and to have a measured RTO/RPO, which is the point of the capstone. In a real product at this traffic I'd drop to pilot-light DR — keep the Global Table and the S3 CRR, but not the running standby endpoint or the warm Aurora replica — which would cut the idle bill by roughly two-thirds at the cost of a longer RTO. Here's the break-even traffic where warm standby starts paying for itself."

This is the hardest question — the reviewer is testing whether you can critique your *own* system's cost/complexity. The strong answer agrees, quantifies the over-spend, explains *why* it's there (demonstration), and names what you'd actually ship in production with the cost delta. An author who can argue *against* their own architecture, with numbers, is an author the reviewer trusts completely.

The pattern across all three: agree where the reviewer is right, attach a number to everything, volunteer the weakness before it's found, and explain the deliberate trade-off. Rehearse your answers in this register. The reviewer is not trying to catch you out; they are trying to find out whether you understand your system well enough to be honest about it. Honesty with numbers is the whole game.

## 1.16 — The common defense mistakes (so you avoid them)

Across cohorts, the defenses that go badly fail in the same handful of ways. Pre-mortem your own against this list:

- **No measured numbers.** The author *says* "RTO is 5 minutes" but never ran the drill. The reviewer asks "how do you know?" and the defense unravels. Fix: run the chaos drills first, bring the measured timelines.
- **Over-claiming.** "Nothing can fail" / "it's fully highly available." Always false, and the reviewer disproves it in one question (your single-instance endpoint, your single NAT). Fix: enumerate your SPOFs *yourself*, with the deliberate reason each is acceptable.
- **The five-diagram sprawl.** The author needs five diagrams and ten minutes to explain the architecture, and the reviewer's first finding is "this is too complex to operate." Fix: force it onto one screen with the request path as the spine.
- **Defending decisions as if they were attacked.** The author argues every finding instead of capturing it. Fix: defend your *trade-offs* (the things you chose on purpose), accept your *risks* (the things you hadn't mitigated), and write the risks down.
- **No cost answer.** The author cannot say what the system costs. In 2026 this fails the Cost Optimization pillar outright. Fix: bring the four cost numbers, from the real CUR.
- **Reading the script.** The author reads the single-event walk off notes, which signals they don't actually operate the system. Fix: rehearse the walk out loud until you can trace a request without looking.
- **Skipping the failure walk.** The author shows only the happy path and never narrates an incident. The reviewer's "what pages you at 3 a.m." question catches them flat. Fix: rehearse one healthy walk *and* one failure walk (§1.7).
- **A leaked teardown.** The author's `cdk destroy` leaves an Aurora cluster or an endpoint billing. Per the "it runs on demand" promise, this fails the capstone regardless of the oral. Fix: prove zero resources and zero billing tail after `cdk destroy --all`.

Every one of these is avoidable with the three artifacts from §1.14 and the chaos data from Lecture 2. The defenses that go *well* are not the ones with the most impressive architecture — they are the ones where the author is calmly, numerically honest about a system they clearly operate.

## 1.17 — What you should be able to do now

After this lecture you should be able to:

- Explain what an architecture review is for (a risk list and a go/no-go decision) and why "calibrated honesty about your own system" is the skill being graded.
- Walk a single request end-to-end through the capstone, naming the failure mode and the signal at every hop.
- Answer the reliability question set: blast radius, SPOFs, measured RTO/RPO, and the 3-a.m. page walk.
- Answer the correctness/security/operations question set: data loss and duplication, the CI-role blast radius, least-privilege on the request path, safe deploys, and the 10x-traffic bottleneck.
- Produce the four cost numbers — weekly bill, idle bill, per-request cost, three ranked optimizations — from real data.
- Walk your capstone through all five Well-Architected pillars with one concrete artifact per pillar.
- Run a system-design interview in both the AWS-shop (Well-Architected) and FAANG-shop (distributed-systems) registers.
- Fill out a peer-review risk list that finds real risks and tags their disposition.
- Recognize a failing reviewer (and avoid being one when you review your peer).

## 1.18 — The exercises and challenge that go with this lecture

- **Exercise 1 — FIS AZ failover.** Build the experiment that produces your measured RTO number — the one the reliability question set demands.
- **Exercise 3 — Cert readiness gate.** The career-pack self-assessment against SAP-C02 / DOP-C02.
- **Challenge 1 — Defend the capstone live.** The 30-minute oral itself, with the peer-review writeup as the reciprocal deliverable.

Bring the three defense artifacts to Friday. The chaos data from Lecture 2 is what makes the failure-modes section real rather than hypothetical — do not arrive with a target you have not measured.
