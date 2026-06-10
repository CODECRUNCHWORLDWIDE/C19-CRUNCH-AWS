# Week 5 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 6. Answer key at the bottom — don't peek.

---

**Q1.** You are sizing compute for a service that holds a large in-memory cache (~28 GB) and barely touches the CPU. Which EC2 family is the right starting point?

- A) `c7g` — compute-optimized; the cache lookups are CPU work.
- B) `r7g` — memory-optimized (1:8 vCPU:memory); you are bottlenecked on RAM, not CPU.
- C) `t4g` — burstable; the cache idles most of the time.
- D) `i4i` — storage-optimized; the cache is "storage."

---

**Q2.** What does the `g` in `m7g.large` tell you?

- A) The instance has a GPU.
- B) It is a "general" tier (as opposed to "graphics").
- C) The CPU is AWS Graviton (arm64), which means you need an `arm64` image and you get roughly 20% better price/performance.
- D) It is a "guaranteed" capacity reservation.

---

**Q3.** A teammate puts a production database's data directory on **instance store** (local NVMe) because it benchmarked far faster than gp3. What is the problem?

- A) Instance store cannot exceed 1 TB.
- B) Instance store is **ephemeral** — it is wiped on stop or terminate (including the next instance replacement), so durable database state will eventually be lost.
- C) Instance store requires an `unsafe` flag at launch.
- D) Nothing — instance store is the correct choice for any database.

---

**Q4.** You configure an ASG mixed-instances policy with `OnDemandBaseCapacity: 1`, `OnDemandPercentageAboveBaseCapacity: 0`, and `SpotAllocationStrategy: capacity-optimized`, with four interchangeable instance types in the overrides. What does this buy you over a single-type, `lowest-price` Spot ASG?

- A) Nothing; allocation strategy is cosmetic.
- B) It guarantees one On-Demand instance as a capacity floor, makes everything above it Spot, and draws Spot from the *deepest-capacity* pools across four types — minimizing interruptions instead of chasing the cheapest (and most-reclaimed) pool.
- C) It makes Spot instances non-interruptible.
- D) It doubles the cost for redundancy.

---

**Q5.** A four-person team with no existing Kubernetes footprint wants to deploy three new HTTP services. Someone proposes standing up EKS "so we can scale later." Per Lecture 1's flowchart, what is the defensible default?

- A) EKS — it is the most scalable, so it is always the safe choice.
- B) ECS Fargate — for a small team with commodity HTTP services and no need for the Kubernetes ecosystem, Fargate is the boring-correct default; EKS adds a $73/mo floor plus a Karpenter/IRSA/LB-Controller operational owner that three services don't justify.
- C) EC2 with hand-rolled systemd units — cheapest per unit.
- D) Lambda — all HTTP services should be serverless.

---

**Q6.** Which workload is the *worst* fit for AWS Lambda as the primary compute?

- A) A bursty webhook receiver that is idle most of the day.
- B) An event handler that runs for ~300 ms per invocation.
- C) A steady, always-busy video-transcoding service where each job runs 40 minutes at sustained 100% CPU.
- D) A cron job that runs once an hour for 5 seconds.

(C is worst on *two* independent grounds — name both in your head before checking the key.)

---

**Q7.** On EKS, why can't Karpenter provision the node that runs Karpenter itself?

- A) Karpenter is not allowed to run on Spot.
- B) Chicken-and-egg: the controller that launches nodes must already be running *somewhere* to launch the first node. So the standard pattern is a small On-Demand **managed node group** for system controllers (Karpenter, CoreDNS, the LB Controller), with Karpenter then provisioning everything else.
- C) Karpenter requires a Fargate profile to run.
- D) It can; this is a non-issue.

---

**Q8.** In an IRSA setup, an IAM role's trust policy contains this condition: `"...:sub": "system:serviceaccount:app:fastapi-reader"`. A teammate changes `StringEquals` to `StringLike` and the value to `system:serviceaccount:app:*` to "make it more flexible." What did they just break?

- A) Nothing; the wildcard only affects logging.
- B) They widened the trust so that **any** service account in the `app` namespace can assume the role, recreating the over-privileged-blast-radius problem IRSA exists to prevent. The whole value of IRSA is pinning the specific `:sub`.
- C) The role can no longer be assumed at all.
- D) The OIDC provider must be re-registered.

---

**Q9.** A pod needs to read one S3 prefix. Which credential strategy is correct, and why are the others wrong?

- A) Bake an access key into the container image — simplest.
- B) Use the node's instance profile — the node already has a role.
- C) IRSA: give the pod's service account its own IAM role scoped to that one prefix. Baking keys leaks them into the registry forever; the node profile grants its permissions to *every* pod on the node.
- D) Use the EKS control-plane role.

---

**Q10.** The AWS Load Balancer Controller can target an ALB at node ports ("instance mode") or at pod IPs directly ("IP mode"). Why is IP mode generally preferred in a modern EKS cluster, and what makes it possible?

- A) IP mode is cheaper because it uses fewer IPs.
- B) The VPC CNI gives every pod a real VPC IP, so the ALB can target pods directly — removing the node→kube-proxy→pod hop and working cleanly with Fargate (which has no node port).
- C) Instance mode is deprecated.
- D) IP mode disables health checks, which speeds things up.

---

**Q11.** You define a `StorageClass` for the EBS CSI driver with `volumeBindingMode: WaitForFirstConsumer`. Why not the default `Immediate`?

- A) `Immediate` is faster and always correct.
- B) EBS volumes are **AZ-scoped**. With `Immediate`, the volume might be created in `eu-west-1a` while the scheduler later places the pod in `eu-west-1b`, where it can never attach. `WaitForFirstConsumer` defers creation until the pod is scheduled, so the volume is born in the pod's AZ.
- C) `WaitForFirstConsumer` encrypts the volume; `Immediate` does not.
- D) The CSI driver only supports `WaitForFirstConsumer`.

---

**Q12.** At **1,000,000 requests/month** for a single small service, your Lecture 1 cost math gave roughly: Lambda ≈ \$1, Fargate+ALB ≈ \$35–40/mo, EKS ≈ \$110/mo. At **1,000,000,000 requests/month of steady traffic**, what happens to the ordering, and why?

- A) The ordering is identical at any scale; cost scales linearly for all three.
- B) The ordering flips: Lambda's per-millisecond billing on a now-constantly-busy workload becomes the most expensive, while EKS-on-Spot (with the $73 control-plane fee amortized to near-zero per request and tightly bin-packed Spot nodes) becomes the cheapest per unit. There is no universal answer — only your traffic shape and scale.
- C) Fargate becomes free above 100M requests.
- D) EKS becomes more expensive because the control-plane fee scales with requests.

---

**Q13.** You scale an EKS Deployment from 0 to 1 and measure two very different cold-start numbers depending on conditions. Which split correctly explains the two measurements?

- A) The two numbers are measurement noise; EKS cold start is constant.
- B) One number is "pod scheduled onto an already-warm node" (seconds — just image-already-cached pod start + readiness); the other is "no node available, so Karpenter must launch a Spot node first" (tens of seconds to a minute — `RunInstances` + node join + pod start). EKS cold start depends entirely on whether a node already exists.
- C) The difference is whether the pod runs on Graviton or x86.
- D) The difference is the ALB warm-up only.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — A memory-bound workload (large cache, light CPU) belongs on the memory-optimized `r` family (1:8 vCPU:memory). On `c` you would pay for compute you never use; on `t` you would get throttled under sustained access; `i` is for local-NVMe IOPS, not RAM.

2. **C** — The trailing `g` denotes AWS Graviton (arm64). You must publish an `arm64` (or multi-arch) image, and you get roughly 20% better price/performance. GPUs are the `g`-*family* (e.g. `g6`), which is different from the `g`-*suffix* processor code — a deliberate trap in the naming.

3. **B** — Instance store is ephemeral local NVMe: blazing fast, free with the instance, and **gone on stop/terminate**, including the routine instance replacement an ASG or a node upgrade performs. Durable state belongs on EBS (which survives stop/terminate). Instance store is for scratch, caches, and shuffle space.

4. **B** — `OnDemandBaseCapacity: 1` guarantees a one-instance On-Demand floor; `OnDemandPercentageAboveBaseCapacity: 0` makes everything above it Spot; `capacity-optimized` launches from the deepest-capacity Spot pools (fewest interruptions) and diversifies across the four override types so no single pool is a single point of failure. `lowest-price` on a single type chases the cheapest, most-frequently-reclaimed pool.

5. **B** — Default *down* the ladder. Three commodity HTTP services on a four-person team with no existing cluster is the textbook Fargate case: no node patching, no cluster fee, no Karpenter/IRSA/LB-Controller surface to own. EKS pays off at scale and across many services; here it is the most expensive default, and "so we can scale later" is not a present requirement.

6. **C** — A 40-minute, sustained-100%-CPU, always-busy job fails Lambda on *two* independent grounds: it exceeds the **15-minute** execution ceiling, and per-millisecond billing on a constantly-busy box is far more expensive than a reserved/Spot instance. The other three (bursty, short, idle-heavy) are textbook Lambda fits.

7. **B** — Chicken-and-egg: the controller that provisions nodes must already be running to provision the first node. The standard pattern is a small On-Demand managed node group hosting Karpenter and the other system controllers, with Karpenter then provisioning the bulk of workloads on Spot.

8. **B** — The `:sub` pin is the entire security value of IRSA. `system:serviceaccount:app:fastapi-reader` means *only* that one service account may assume the role. Switching to `StringLike` with `app:*` lets any service account in the namespace assume it — recreating the over-privileged blast radius IRSA exists to eliminate. Pin the subject; never wildcard it without a deliberate reason.

9. **C** — IRSA: the pod's service account gets its own least-privilege role (one prefix, one action). Baked keys live in the registry forever and cannot be rotated cleanly; the node instance profile grants its permissions to *every* pod co-located on that node, so one compromised pod inherits the node's full access. The control-plane role is unrelated to pod credentials.

10. **B** — The VPC CNI assigns every pod a real VPC IP, so the ALB can register pod IPs directly as targets. That removes the node→kube-proxy→pod hop (lower latency, cleaner health checks) and works with Fargate, which has no node port for instance-mode targeting. Instance mode still works with managed node groups; IP mode is simply the better default.

11. **B** — EBS volumes are AZ-scoped. `Immediate` binding can create the volume in one AZ before the scheduler places the pod in another, leaving an unattachable volume. `WaitForFirstConsumer` waits until the pod is scheduled, then provisions the volume in the pod's AZ. (Encryption is a separate `parameters` flag — `encrypted: "true"` — and should always be on; it is not what the binding mode controls.)

12. **B** — The ordering flips with scale and traffic shape. Lambda's per-ms model is cheapest when idle-heavy and most expensive when constantly busy; EKS's $73 control-plane fee is brutal for one tiny service but amortizes to nothing across a large, steadily-utilized, Spot-bin-packed fleet. The benchmark table exists precisely because there is no scale-independent winner.

13. **B** — The two numbers are "warm node already present" (seconds: pod start + readiness, image likely cached) versus "no node, Karpenter must launch one first" (tens of seconds to a minute: `RunInstances`, node join, then pod start). Reporting both — not averaging them — is the honest way to characterize EKS cold start, which is dominated by whether capacity is already on.

</details>

---

If you scored under 9, re-read the lectures for the questions you missed — especially the IRSA mechanics (Q8/Q9) and the cost-flips-with-scale story (Q12), which the mini-project leans on hardest. If you scored 11+, you're ready for the [homework](./homework.md).
