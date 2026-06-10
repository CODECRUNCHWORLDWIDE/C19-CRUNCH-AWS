# Lecture 1 — When to Pick Lambda vs Fargate vs EKS vs EC2: A Real Flowchart You Can Defend in a Design Review

> **Duration:** ~2 hours of reading + sketching.
> **Outcome:** You can draw the compute-decision flowchart from memory, attach a real dollar number to each branch, and defend the pick when a principal engineer pushes back. You can decode the EC2 instance-family alphabet soup, pick an EBS volume type, and design an ASG with a mixed-instances Spot policy.

If you only remember one thing from this lecture, remember this:

> **The compute decision is a cost decision, a latency decision, and an operational-burden decision — usually in that order. The platform you already know is rarely the right answer, and "we'll just use Kubernetes" is the most expensive default in the building.**

---

## 1. The spectrum, and why it is a spectrum

People talk about Lambda, Fargate, EKS, and EC2 as four products. They are better understood as four points on one axis: **how much of the machine you manage.**

```
 You manage MORE                                          You manage LESS
 ◀──────────────────────────────────────────────────────────────────────▶
   EC2            ECS-on-EC2        ECS Fargate / EKS-Fargate        Lambda
   (raw VMs)      (your nodes,      (no nodes; AWS runs the          (no servers;
                   AWS schedules     container in a microVM)          AWS runs the
                   containers)                                        function)
                              EKS-on-EC2 (your nodes, k8s API)
```

At the left, you patch the OS, you size the box, you own the AMI, you wake up when a kernel CVE drops. At the right, you hand AWS a zip file and a handler name and never think about a server again — but you accept cold starts, a 15-minute ceiling, and per-millisecond billing that punishes long-running or steady high-throughput work.

Everything in between is a trade of operational burden for control and, sometimes, cost. The art is knowing where on the axis a given workload belongs. The science is the cost math, which we do at the end.

A second axis runs orthogonal to the first: **how spiky is the traffic?** Idle-heavy, bursty workloads love the scale-to-zero right side. Steady, predictable, high-utilization workloads love the committed-capacity left side, where Savings Plans and Spot crush the per-unit cost. Plot your workload on both axes before you argue about platforms.

---

## 2. EC2: the substrate everything else is built on

Fargate runs on Firecracker microVMs on EC2 hardware. EKS nodes are EC2 instances. Even Lambda runs on Firecracker on EC2. You cannot reason about the higher layers without reasoning about EC2, so we start here.

### 2.1 The instance-family alphabet soup

The first letter is the **family** (the workload shape). The number is the **generation**. A trailing `g` means **Graviton** (arm64). A trailing `d` means local NVMe instance store. Other suffixes (`n`, `e`, `i`, `flex`) tune network, memory, or flexibility.

| Family | Optimized for | CPU:mem ratio | Reach for it when… | Example (2026) |
|--------|---------------|---------------|--------------------|----------------|
| `t`    | Burstable, cheap | 1:2 to 1:4   | Dev boxes, low-traffic services that idle | `t4g.small` |
| `m`    | Balanced       | 1:4           | General web/app servers, the safe default | `m7g.large` |
| `c`    | Compute        | 1:2           | CPU-bound: encoding, batch, game servers, ML preprocessing | `c7g.xlarge` |
| `r`    | Memory         | 1:8           | In-memory caches, big JVM heaps, analytics | `r7g.xlarge` |
| `i`    | Storage (NVMe) | 1:8 + local SSD | Databases needing local IOPS, search indices | `i4i.large` |
| `g`    | GPU (graphics/inference) | varies | Rendering, ML inference on GPU | `g6.xlarge` |
| `p`    | GPU (training) | varies        | Model training, HPC | `p5.48xlarge` |
| `inf`/`trn` | Accelerators | varies     | Inferentia/Trainium for cost-efficient ML | `inf2.xlarge` |

**The Graviton rule of thumb (2026):** if your workload is arm64-clean — pure Python, Go, Java, Node, most container images that publish `linux/arm64` — move to a `g`-suffix family. You get roughly **20% better price/performance** and often lower energy. The only reason not to is a binary dependency that only ships x86_64 (rare and shrinking). We use Graviton everywhere we can this week.

**Burstable (`t`) instances are a trap if you don't understand CPU credits.** A `t4g.small` gives you a baseline of ~20% of a vCPU and accrues credits when idle that it spends when busy. Run it at 100% CPU continuously and you either get throttled or pay for "unlimited" mode that quietly bills you for the overage. `t` is for *bursty, idle-heavy* work, not steady load. For steady load, `m`/`c`/`r` is cheaper *and* predictable.

### 2.2 Sizing: read the ratio, not the marketing

Sizing is a two-step move. First pick the family from the bottleneck (CPU? memory? local IO?). Then pick the size so that the resource you are bottlenecked on is ~60–70% utilized at steady state, leaving headroom for spikes. A service that uses 3 GB of RAM and barely touches the CPU belongs on `r` (memory-dense), not `c` — on `c` you pay for compute you never use. Right-sizing is the cheapest FinOps win there is; **Compute Optimizer** will hand you the recommendation.

### 2.3 AMIs: what's baked in

An **AMI** (Amazon Machine Image) is the boot disk template: OS, pre-installed packages, your agent, your app. Two philosophies:

- **Golden AMI:** bake everything in with Packer at build time. Fast boot, immutable, reproducible. The right call for ASGs and high-scale fleets.
- **Bootstrap at boot:** launch a base AMI and run user-data / cloud-init / Ansible at first boot. Slower, but flexible. Fine for low-scale or dev.

For EKS you almost never build your own node AMI. You use the **EKS-optimized AL2023 AMI** or, better, **Bottlerocket** — a minimal, immutable, container-only OS with a read-only root filesystem and automatic updates. Bottlerocket's attack surface is a fraction of a general-purpose Linux box, and it boots fast, which matters when Karpenter is launching nodes in response to pending pods.

### 2.4 Storage attached to compute

| Type | What it is | IOPS/throughput | Durability | Reach for it when… |
|------|------------|-----------------|------------|--------------------|
| **EBS gp3** | Network SSD, the default | 3,000 IOPS / 125 MB/s baseline, scalable to 16k/1000 | Survives stop/terminate | Almost always. Decouple IOPS from size — no more over-provisioning capacity to buy IOPS like gp2. |
| **EBS io2 Block Express** | High-end network SSD | up to 256k IOPS, sub-ms | Survives stop/terminate, 99.999% | You genuinely need >64k IOPS or a 99.999% volume — a busy production database. |
| **EBS st1 / sc1** | Throughput / cold HDD | high MB/s, low IOPS | Survives stop/terminate | Big sequential reads: logs, data lake staging. Cheap per GB. |
| **Instance store** | Local NVMe on the host | Highest, lowest latency | **Gone on stop/terminate** | Scratch, caches, shuffle space, replicated databases that don't need single-node durability. Free with the instance. |

The mistake juniors make: putting durable state on instance store because it benchmarks fast, then losing it on the next instance replacement. Instance store is ephemeral by definition. If losing it would page you, it belongs on EBS.

### 2.5 The suffix soup, decoded

The first letter and the generation number get you 80% of the way; the trailing letters tune the last 20%, and they show up constantly in real instance names. Learn to read them so `m7gd.4xlarge` parses on sight instead of intimidating you.

| Suffix | Means | Reach for it when… |
|--------|-------|--------------------|
| `g`    | Graviton (arm64) | Always, if arm64-clean. ~20% better price/perf. |
| `i`    | Intel (when the family default is AMD/Graviton) | A workload pinned to Intel-specific instructions (AVX-512 in some builds). |
| `a`    | AMD EPYC | Slightly cheaper than Intel for x86 work; rarely the deciding factor. |
| `d`    | Local NVMe instance store attached | You want ephemeral local SSD (scratch, shuffle, cache) bundled in. |
| `n`    | Network-optimized (higher bandwidth) | Network-bound work: proxies, caches, high-throughput data movers. |
| `e`    | Extra memory or extra storage (family-dependent) | The base ratio is just shy of what you need. |
| `flex` | Flexible/burstable general-purpose (e.g. `m7i-flex`) | Steady-ish general work that doesn't sustain 100% CPU — cheaper than the full `m7i`. |

So `m7gd.4xlarge` is: balanced family, gen 7, Graviton, with local NVMe, 4xlarge size. `c7gn.large` is compute-optimized Graviton with the network-optimized NICs. You will not memorize every combination — you will learn to *decompose* the name, which is the actual skill.

### 2.6 Right-sizing in practice (not in theory)

The textbook says "bottleneck family, then 60–70% utilization." In practice you do this:

1. **Start one size up from your guess** in dev, instrument CPU/memory/network, and let it run under realistic load for a few days.
2. **Read Compute Optimizer**, which will tell you "this instance is over-provisioned, drop to `m7g.large`" or "this one is CPU-bound, you're throttling." It's free and it's usually right.
3. **Right-size down** until the bottleneck resource sits at ~65% at steady state, with spike headroom. The fear of "what if we need more" is what makes bills enormous; the ASG (or Karpenter, or Lambda's auto-scaling) *is* the answer to "what if we need more." You do not buy headroom by oversizing a single box — you buy it with horizontal scale.

The single most common cloud-cost finding, across every FinOps audit ever run, is **over-provisioned compute that nobody ever revisited.** Right-sizing is boring and it is the highest-ROI thing on this page.

### 2.7 Placement groups

- **Cluster:** packs instances close on the network for lowest latency / highest throughput (HPC, tightly-coupled jobs). Single-AZ, so it concentrates failure.
- **Spread:** forces instances onto distinct hardware (max 7 per AZ) for anti-affinity. Use for a handful of critical, must-not-fail-together instances.
- **Partition:** groups into partitions on distinct racks (HDFS, Cassandra, Kafka). Big distributed systems that already understand rack awareness.

---

## 3. Auto Scaling Groups, launch templates, and Spot

If you run EC2 at all in production, you run it under an **Auto Scaling Group**, never as a pet instance. An ASG keeps `desired` instances healthy, replaces failures, and scales between `min` and `max` on a policy.

### 3.1 Launch templates (not launch configurations)

Launch **configurations** are deprecated — AWS will not let you create new ones in many regions. Use **launch templates**: versioned specs of AMI, instance type, security groups, IAM instance profile, user-data, and block device mappings. Versioning matters: you roll forward to v3, and if it's bad you point the ASG back at v2 — an instant rollback.

### 3.2 Scaling policies

- **Target tracking** (the default you want): "keep average CPU at 50%." AWS does the math and adjusts `desired`. Simple, self-correcting.
- **Step scaling:** "+2 instances if CPU > 70% for 3 minutes, +4 if > 85%." More control, more to get wrong.
- **Scheduled:** "scale to 10 at 08:00 on weekdays." For known patterns.

Pair the scaling policy with a **health check** (EC2 status checks *and* ALB target-group health) and a **lifecycle hook** if you need to drain connections before an instance is terminated.

### 3.3 The mixed-instances policy and Spot economics

This is the production-grade pattern, and it is where the savings live. A **mixed-instances policy** lets one ASG span many instance types and mix On-Demand with Spot.

```jsonc
// Conceptual shape of a mixed-instances policy (CloudFormation / SDK fields)
{
  "MixedInstancesPolicy": {
    "LaunchTemplate": {
      "LaunchTemplateSpecification": { "LaunchTemplateId": "lt-0abc", "Version": "$Latest" },
      "Overrides": [
        { "InstanceType": "m7g.large" },
        { "InstanceType": "m6g.large" },
        { "InstanceType": "c7g.large" },
        { "InstanceType": "r7g.large" }
      ]
    },
    "InstancesDistribution": {
      "OnDemandBaseCapacity": 1,
      "OnDemandPercentageAboveBaseCapacity": 0,
      "SpotAllocationStrategy": "capacity-optimized"
    }
  }
}
```

What that policy says: **always keep at least 1 On-Demand instance** (the base — your floor of guaranteed capacity), and **make everything above the base Spot** (`OnDemandPercentageAboveBaseCapacity: 0`). Spread across four interchangeable instance types so that if one type's Spot pool dries up, AWS pulls from another.

`SpotAllocationStrategy: capacity-optimized` is the one to use in 2026. It launches from the Spot pools with the *deepest available capacity*, which minimizes interruptions — far better than the old `lowest-price`, which chased the cheapest pool straight into the most-frequently-reclaimed one.

**Spot interruption handling.** Spot is spare capacity at 60–90% off, and AWS can reclaim it with a **2-minute notice** delivered to instance metadata, plus an earlier **rebalance recommendation** when a pool is getting tight. The discipline:

1. Only put **interruption-tolerant** work on Spot: stateless web tiers, batch, CI runners, EKS worker nodes draining gracefully.
2. **Diversify** across instance types and AZs so no single pool is a single point of failure.
3. **Handle the signal:** drain connections / cordon-and-drain the node / checkpoint the job within the 2-minute window. On EKS, the **AWS Node Termination Handler** (or Karpenter's native interruption handling) does this for you.

Spot is not "cheap and risky." Diversified and capacity-optimized, it is "cheap and managed-risk." The risky version is one instance type in one AZ on `lowest-price`.

---

## 4. The four platforms, head to head

Now the spectrum with the operational reality attached.

### 4.1 Lambda

**What it is:** you upload a handler (zip or container image up to 10 GB), AWS runs it on demand on a Firecracker microVM, scales from zero to thousands of concurrent executions, and bills per **GB-second** plus per-request.

**Limits that decide whether your workload fits:**
- **15-minute** max execution. Long jobs do not fit.
- **10 GB** max memory (CPU scales with memory — more RAM means more vCPU).
- **6 MB** synchronous payload (request + response). Big uploads need S3 presigned URLs or streaming.
- **250 MB** unzipped zip package, or **10 GB** container image.
- **Cold starts:** first invocation in a new environment pays init latency — tens of ms for a tiny Python function, hundreds of ms to seconds for a fat dependency tree or a JVM. **SnapStart** (now Python and Java in 2026) snapshots the initialized environment to cut this. **Provisioned concurrency** pre-warms environments and eliminates it — at a standing cost.

**Pick Lambda when:** traffic is spiky or idle-heavy, executions are short (< a few seconds), you want zero servers, and a cold-start p99 in the hundreds of ms is acceptable. Event handlers, API backends with bursty traffic, glue between AWS services, cron jobs. **Our FastAPI service fits Lambda** via the Lambda Web Adapter — see Lecture 2's sibling exercise.

**Avoid Lambda when:** you need sustained high throughput (per-ms billing on a box that's always busy is more expensive than a reserved instance), long-running work, big payloads, websockets-at-scale, or sub-10ms tail latency with no cold-start tolerance.

### 4.2 ECS Fargate

**What it is:** you write an ECS **task definition** (containers, CPU, memory, IAM roles), and Fargate runs it on a microVM with **no node for you to manage**. No cluster fee on ECS. You pay per **vCPU-second and GB-second** for the size you requested, rounded to the second, with a 1-minute minimum.

**Pick Fargate when:** you have a containerized service, you want it always-on (so Lambda's per-ms model is a loser), and you do **not** want to run Kubernetes. This is the **boring-correct** answer for a huge fraction of services. No node patching, no cluster operators, no Karpenter to babysit. ECS is genuinely simpler than EKS, and ECS Fargate is the simplest production container platform AWS offers.

**ECS Fargate Spot** exists and is ~70% off — for interruption-tolerant tasks, same 2-minute notice model.

**Avoid Fargate when:** you need the Kubernetes API and ecosystem (operators, CRDs, Helm charts, a service mesh), you need daemon-style workloads on every node, GPUs (Fargate has no GPU support), or you're running at a scale where managing your own EC2 nodes under EKS is meaningfully cheaper per-unit.

### 4.3 ECS-on-EC2

**What it is:** ECS scheduling the containers, but onto **EC2 instances you own** (in an ASG). You patch the nodes; you get GPUs, instance store, custom AMIs, and bin-packing efficiency. You can run the nodes on Spot and Savings Plans.

**Pick ECS-on-EC2 when:** you want ECS's simplicity (no Kubernetes) but need GPUs, instance store, or the cost efficiency of densely bin-packed self-managed nodes under a Savings Plan. It's the middle path for ECS shops with cost or hardware constraints Fargate can't meet.

### 4.4 EKS

**What it is:** AWS-managed upstream **Kubernetes**. You get the real k8s API and the entire CNCF ecosystem. AWS runs the control plane (the part that's genuinely hard to operate) for **$0.10/hour (~$73/month) per cluster**, idle or not. You run the worker nodes — managed node groups, Karpenter-provisioned nodes, or Fargate profiles — and you own the operational surface: CNI, Karpenter, the LB Controller, IRSA, the CSI driver, upgrades.

**Pick EKS when:** you're multi-team or multi-service at scale, you need the Kubernetes ecosystem (Argo, Istio/Linkerd, operators, CRDs), you're multi-cloud and want a portable substrate, or you're running enough compute that the control-plane fee disappears into the noise and Karpenter+Spot crushes your per-unit cost. **EKS pays off at scale; it punishes you at small scale.**

**Avoid EKS when:** you have three services and two engineers. The $73/month is the *cheap* part — the expensive part is the human who has to own Karpenter, the LB Controller, IRSA, node upgrades, and the next CVE. If "we'll just use Kubernetes" is the reflex for a small team, that's the most expensive default in the building.

### 4.5 The comparison table

| Dimension | Lambda | ECS Fargate | ECS-on-EC2 | EKS |
|-----------|--------|-------------|------------|-----|
| You manage | Code only | Code + task def | Code + nodes | Code + nodes + k8s ops |
| Cold start | Yes (ms–s) | ~task start (s) | ~task start (s) | ~pod sched + maybe node launch (s–min) |
| Scale to zero | Yes, native | No (min tasks) | No | No (min nodes) |
| Idle cost | $0 | per-task vCPU/GB-s | node hours | $73/mo + node hours |
| Best traffic shape | Spiky/idle | Steady, always-on | Steady, dense | Steady, multi-service |
| GPU | No | No | Yes | Yes |
| Ecosystem | AWS events | ECS | ECS | All of CNCF |
| Ops burden | Lowest | Low | Medium | Highest |
| Per-unit cost at scale | High | Medium | Low | Lowest (Spot) |

---

## 5. The flowchart you can defend

Sketch this on the whiteboard. The reviewer is testing whether you reason from the workload, not from the tool you like.

```
START: characterize the workload.
│
├─ Is each unit of work < 15 min, event-or-request-driven,
│  and is traffic spiky or idle-heavy?
│        │
│        ├─ YES → cold-start p99 of 100s of ms acceptable?
│        │          ├─ YES → LAMBDA. (Add provisioned concurrency / SnapStart if not.)
│        │          └─ NO  → still maybe Lambda + provisioned concurrency; price it.
│        │                   If too costly → FARGATE.
│        └─ NO ↓
│
├─ Is it a long-running / always-on containerized service?
│        │
│        ├─ Do you need GPUs, instance store, or dense Spot bin-packing for cost?
│        │        ├─ YES, and you don't need k8s → ECS-on-EC2.
│        │        └─ YES, and you need k8s/CNCF  → EKS (+ Karpenter on Spot).
│        └─ NO (commodity container, no special hardware) ↓
│
├─ Do you NEED the Kubernetes API / CNCF ecosystem / multi-cloud portability?
│        ├─ YES → EKS (managed node groups + Karpenter + LB Controller + IRSA).
│        └─ NO  → FARGATE.  ← the boring-correct default for most services.
│
└─ Special case: embarrassingly parallel batch with a queue of jobs?
         → AWS BATCH over a Spot compute environment (or EKS + Karpenter for k8s shops).
```

Two guardrails to state out loud in the review:

1. **"We already run Kubernetes" is a reason, not an excuse.** If the org already operates EKS well, the marginal cost of one more service on it is low and "put it on EKS" is defensible. If the org does *not* already run it, "let's stand up EKS for this one service" needs the cost math to justify $73/month + an owner.
2. **Default down the ladder, not up.** Start at Lambda or Fargate. Move toward EC2 only when a concrete requirement (GPU, instance store, k8s ecosystem, per-unit cost at scale) forces you there. Going the other way — starting at EKS and wondering why the bill is high — is the common, expensive mistake.

---

## 6. Real cost math (2026, `us-east-1`)

Numbers move; the *method* doesn't. Always re-price before a review. Here is the method, worked for a service handling **1,000,000 requests/month**, each request 100 ms of compute at the equivalent of ~0.5 vCPU and ~512 MB.

### 6.1 Lambda

- Memory 512 MB → 0.5 GB. Duration 100 ms → 0.1 s. GB-seconds per request = 0.5 × 0.1 = **0.05 GB-s**.
- 1M requests → 50,000 GB-s. Compute price ~**$0.0000166667 / GB-s** → 50,000 × 0.0000166667 ≈ **$0.83**.
- Request price ~**$0.20 / 1M** → **$0.20**.
- **Lambda total ≈ $1.03 / 1M requests**, and **$0 when idle**. (Provisioned concurrency, if used, adds a standing GB-second charge whether or not requests arrive.)

### 6.2 Fargate (always-on, 1 task: 0.5 vCPU, 1 GB)

Fargate bills for the task's lifetime, **not per request**. So we price the month, not the million.
- vCPU: 0.5 × **$0.04048 / vCPU-hour** × 730 h ≈ **$14.78**.
- Memory: 1 GB × **$0.004445 / GB-hour** × 730 h ≈ **$3.24**.
- **One task ≈ $18.02 / month**, regardless of whether it served 1M or 10M requests (until you need more tasks).
- Add the ALB: ~**$16.20/month** base ($0.0225/hour × 730) **plus LCUs** (typically a few dollars at this scale).
- **Fargate + ALB ≈ $35–40 / month** for the whole service at this load. At 1M req that's ~$0.035/1k req; at 10M it's ~$0.0035/1k req. **Fargate gets cheaper per request as traffic rises** until you saturate the task.

### 6.3 EKS (Karpenter on Spot)

- **Control plane: $73/month, idle or not.** This is the floor.
- Worker capacity for one small service on Spot `m7g.large`-class: a Spot `m7g.large` is roughly **$0.02–0.03 / hour** (vs ~$0.0816 On-Demand) → ~**$15–22/month** for one node, and Karpenter will bin-pack many pods onto it.
- ALB via the LB Controller: ~**$16–20/month** as above.
- **EKS for one service ≈ $73 + ~$20 + ~$18 ≈ $111/month.** *For one service, EKS is the most expensive option.* Now put **40 services** on that same cluster and the $73 is amortized to under $2/service, the Spot nodes bin-pack tightly, and EKS becomes the **cheapest per-unit** option. That crossover is the entire EKS cost story.

### 6.4 EC2 (ASG, On-Demand vs Spot vs Savings Plan)

- One `m7g.large` On-Demand: **$0.0816/hr × 730 ≈ $59.57/month**.
- Same on a 1-year Compute Savings Plan: ~**30–40% off** → ~$36–42/month.
- Same on Spot, capacity-optimized: ~**60–70% off** → ~$18–24/month.
- No control-plane fee, but you patch the box and you run the orchestration yourself. EC2 wins on raw per-unit cost for steady, high-utilization, interruption-tolerant work — and loses on operational burden.

### 6.5 The commitment dimension: On-Demand, Spot, Savings Plans

Every cost number above assumed On-Demand pricing, which is the *most expensive* way to buy steady compute. The same vCPU has three other price points, and which one you can use is itself a platform-decision input:

- **On-Demand** — pay the list hourly rate, no commitment, walk away any time. The right price *only* for genuinely unpredictable or short-lived capacity. It is the default, and the default is rarely the cheapest.
- **Spot** — spare capacity at 60–90% off, reclaimable on a 2-minute notice. The cheapest compute AWS sells, available on EC2, ECS-on-EC2, EKS nodes, Fargate Spot, and AWS Batch — but **not** on the EKS control plane or on Lambda. For interruption-tolerant, stateless, diversified workloads it is the obvious win; for a singleton stateful process it is a foot-gun.
- **Compute Savings Plans** — commit to a steady dollar-per-hour of compute spend for 1 or 3 years and get ~30–66% off across EC2, Fargate, *and* Lambda, with the flexibility to move between them. The right tool for a predictable steady-state floor.
- **EC2 Instance Savings Plans / Reserved Instances** — deeper discount, narrower flexibility (locked to an instance family/region). Use only when you are certain of the shape for the full term.

The interaction with the platform decision is the part people miss: **Lambda cannot use Spot**, so its only lever is a Compute Savings Plan on its steady baseline. **Fargate can use Spot** (Fargate Spot) for interruption-tolerant tasks and Savings Plans for the always-on floor. **EKS-on-Spot** is the cheapest of all *because* Karpenter diversifies across Spot pools automatically — which is the entire reason EKS's per-unit cost can undercut everything else at scale. When you price a platform for a review, price it on the *cheapest commitment model that workload can actually use*, not on On-Demand — and state which model you assumed. A benchmark that compares On-Demand EC2 to Spot EKS is comparing prices, not platforms.

### 6.6 The parts people forget

- **NAT Gateway data processing** (~$0.045/GB) on anything egressing to the internet through NAT. Week 4's VPC endpoints exist precisely to dodge this for S3/ECR/STS traffic. If your benchmark pulls images and reads S3 through NAT, that line item is real.
- **ALB LCUs** — the ALB base price is the floor; LCUs (new connections, active connections, bandwidth, rule evaluations) add to it under load.
- **CloudWatch Logs ingestion** (~$0.50/GB ingested) — chatty Lambda logging at 1M requests adds up faster than the compute.
- **EKS control-plane fee** — the $73/month that does not appear on any per-request calculation but absolutely appears on the bill.

> **The headline:** at 1M req/month, **Lambda ≈ $1, Fargate ≈ $35–40, EKS ≈ $111.** At 1B req/month of steady traffic, the ordering flips — Lambda's per-ms model becomes the most expensive and EKS-on-Spot the cheapest per unit. **There is no universal answer; there is only your traffic shape and your scale.** That is why the deliverable this week is a table, not an opinion.

---

## 7. AWS Batch: the fifth option people forget

The flowchart's last branch — "embarrassingly parallel batch with a queue of jobs" — deserves its own paragraph, because reaching for an ASG or a hand-rolled EKS Job controller here is a common over-build.

**AWS Batch** is a managed scheduler for batch workloads. You define a **compute environment** (managed: "use Spot across these instance families, scale 0→256 vCPUs as the queue grows"; or unmanaged: bring your own ASG), a **job queue**, and **job definitions** (a container image, vCPU/memory, retries, an array size). You submit jobs; Batch provisions exactly enough Spot capacity to drain the queue, runs each job in a container on EC2 or Fargate, and **scales the environment back to zero** when the queue empties. Array jobs let one submission fan out into thousands of indexed children — the classic "process every file in this S3 prefix" shape.

The decision is sharp:

- **Use Batch when** the work is a *queue of independent jobs* — overnight transcoding, Monte Carlo simulations, genomics pipelines, bulk image processing, ETL backfills. Each job is independent, interruption-tolerant, and the fleet should be zero when there's nothing to do. Batch on a Spot compute environment is the cheapest way to run this and you write almost no orchestration.
- **Don't use Batch for** request/response services (that's Lambda/Fargate/EKS), for tightly-coupled MPI-style jobs that need a cluster placement group and low-latency interconnect (that's EC2 in a cluster placement group, or AWS ParallelCluster), or for workflows with complex inter-job dependencies and human approvals (that's Step Functions, Week 10).

The trap is hand-rolling Batch's behavior on a raw ASG — scaling logic, retry, dead-letter, array fan-out — when Batch already does it. The opposite trap is reaching for Batch for a steady stream that never goes idle, where a long-lived Fargate or EKS consumer of an SQS queue is simpler. Match the tool to the *shape of the work queue*, not to the language the jobs are written in.

---

## 8. A worked decision, end to end

To make the flowchart concrete, walk one workload through it the way you would at a whiteboard. **Workload:** a thumbnail-generation service. An upload lands in S3; something must produce three resized variants. Traffic is bursty — quiet for hours, then a customer bulk-uploads 4,000 images in two minutes.

1. **Characterize.** Each unit of work is one image → a few hundred ms of CPU-bound resize. Event-driven (S3 `ObjectCreated`). Spiky to the extreme. No sub-10ms latency requirement — a few seconds end-to-end is fine.
2. **First branch.** Unit of work < 15 min? Yes (sub-second). Event-driven? Yes. Spiky? Extremely. → the Lambda branch.
3. **Cold-start tolerance?** A thumbnail that appears 1.5 s after upload instead of 0.3 s is invisible to the user. Cold start is acceptable. → **Lambda**, triggered by S3 events, scaling to thousands of concurrent executions during the burst and back to **$0** when idle.
4. **Sanity-check the rejected options.** Fargate would need either always-on tasks (paying for the quiet hours) or scale-from-zero with a cold-scale cliff exactly when 4,000 events arrive at once. EKS adds the $73 floor and an operational owner for a workload that is *defined* by being idle most of the time. Both lose on this traffic shape.
5. **Find the edge that flips it.** If the same service grew to a *steady* 2,000 images/second all day, Lambda's per-ms billing on constantly-busy capacity would become the most expensive option, and a Fargate or EKS consumer of an SQS queue (or AWS Batch for backfills) would overtake it. **State that reversal condition out loud** — it is what turns a pick into a defensible decision.

That five-step trace is the exact muscle the mini-project's decision doc exercises: characterize, branch, tolerance-check, reject-with-a-number, name-the-reversal. Do it for the thumbnail service in your head now; you'll do it for a named product in writing on Friday.

---

## 9. What to carry into the rest of the week

- The **spectrum** (manage-more ↔ manage-less) and the orthogonal **traffic-shape** axis.
- The **EC2 family table** and the **Graviton rule**: arm64-clean → `g`-suffix → ~20% cheaper.
- The **mixed-instances + `capacity-optimized` Spot** pattern as the production-grade ASG default.
- The **flowchart** — default down the ladder; move up only when a concrete requirement forces it.
- The **cost method** — always price the month *and* per-request, and never forget NAT, LCUs, logs, and the EKS control-plane floor.

Lecture 2 goes deep on the right-hand side of the flowchart's hardest branch: **running EKS in production** — Karpenter, IRSA, the AWS Load Balancer Controller, and the Spot node economics that make EKS worth its operational weight once you're at scale.
