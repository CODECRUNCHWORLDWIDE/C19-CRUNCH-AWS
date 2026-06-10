# Week 5 Homework

Six problems that revisit the week's topics and push them slightly further than the exercises did. The full set should take about **6 hours**. Work in your Week 5 Git repository (`c19-week-05-<yourhandle>`) so each problem produces at least one commit you can point to later. Several problems create billable resources — **`cdk destroy` (or `tofu destroy`) every night**, and watch the EKS control-plane line and the NAT Gateway line of Cost Explorer.

Each problem includes:

- A short **problem statement**.
- **Deliverables** — the concrete artifacts you commit.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

A grading **rubric** is at the bottom.

> Cost discipline for the week: the EKS control plane bills `$0.10/hour (~$73/month)` from the moment the cluster exists, idle or not. Problems 3 and 5 stand one up. Do them in a single focused sitting and tear the cluster down the same night. A weekend of forgotten control plane is `~$5`; a forgotten month is `~$73`.

---

## Problem 1 — Decode the instance family for four workloads

**Problem statement.** You are sizing four real workloads. For each, pick a specific EC2 instance family **and** size (e.g. `c7g.2xlarge`), and justify it in one sentence from the CPU : memory : network : storage profile. Then state whether Graviton (`arm64`) is a safe pick for that workload and why. The four workloads:

1. A latency-sensitive stateless HTTP API, CPU-bound, ~3.5 GB resident per process, no local disk needs.
2. An in-memory analytics cache holding ~200 GB of hot data, modest CPU.
3. A nightly batch transcode that is embarrassingly parallel, CPU-bound, and tolerant of interruption.
4. A self-managed Postgres needing sustained `>80,000` IOPS on its data volume.

**Deliverables.** A file `notes/instance-sizing.md` with one section per workload: the chosen family + size, the one-sentence justification, the Graviton verdict, and — for workload 4 — the EBS volume type you would attach and why.

**Acceptance criteria.**

- Workload 1 lands on a compute-optimized family (`c`-class), Graviton flagged safe for a clean stateless API.
- Workload 2 lands on a memory-optimized family (`r`/`x`-class) sized so RAM comfortably exceeds 200 GB.
- Workload 3 names a Spot-friendly strategy (mixed instance types) and flags interruption tolerance as the reason.
- Workload 4 attaches **io2 Block Express** (not gp3) with a one-sentence reason that gp3 caps at 16,000 IOPS per volume.
- Committed.

**Hint.** The `g` suffix means Graviton (`c7g`, `m7g`, `r7g`). Graviton is safe when nothing in the dependency tree ships x86-only native binaries; recompiled Python/Go/Rust/Node services are almost always clean. gp3 tops out at 16,000 IOPS and 1,000 MB/s per volume; io2 Block Express goes to 256,000 IOPS. `r7g` gives ~8 GB RAM per vCPU; an `r7g.8xlarge` is 256 GB.

**Estimated time.** 40 minutes.

---

## Problem 2 — A mixed-instances Spot launch template that survives a capacity event

**Problem statement.** Write a CDK stack (TS or Python) that creates an **Auto Scaling Group** with a **launch template** and a **mixed-instances policy** that: keeps a base of **1 On-Demand** instance, fills the rest from **Spot** using the `price-capacity-optimized` allocation strategy, and **diversifies across at least four instance types** drawn from at least two families (so a single instance-type capacity crunch cannot starve the group). Set `min=1, max=6, desired=2`. Do **not** deploy public IPs; place the ASG in the Week-4 private subnets.

**Deliverables.** The CDK stack under `homework/p2-mixed-asg/` plus a file `homework/p2-mixed-asg/SYNTH.md` pasting the synthesized `AWS::AutoScaling::AutoScalingGroup` `MixedInstancesPolicy` block.

**Acceptance criteria.**

- `cdk synth` succeeds.
- The synthesized `InstancesDistribution` shows `OnDemandBaseCapacity: 1`, `OnDemandPercentageAboveBaseCapacity: 0`, and `SpotAllocationStrategy: price-capacity-optimized`.
- The `LaunchTemplate.Overrides` list contains **four or more** instance types spanning **two or more** families (e.g. `c7g.large`, `c7i.large`, `m7g.large`, `m7i.large`).
- One sentence in `SYNTH.md` explaining why diversification across types and AZs is the whole point of a Spot ASG.
- Committed.

**Hint.** In CDK, `autoscaling.AutoScalingGroup` accepts `mixedInstancesPolicy` with `instancesDistribution` and a `launchTemplate` plus `launchTemplateOverrides: [{ instanceType: ec2.InstanceType.of(...) }, ...]`. `price-capacity-optimized` is the strategy AWS now recommends over plain `capacity-optimized` — it weighs both interruption risk and price. Mixing `c7g`/`m7g` (Graviton) with `c7i`/`m7i` (Intel) requires a multi-arch AMI or two overrides keyed to arch; for this exercise keep all four on the same architecture to keep one AMI.

**Estimated time.** 1 hour.

---

## Problem 3 — IRSA, proven by the negative

**Problem statement.** Reproduce the most instructive security result of the week. On the EKS cluster from Exercise 2 (stand it up if you tore it down), confirm that the IRSA-bound pod can read its **allowed** S3 prefix and **cannot** read a forbidden prefix in the same bucket. Capture both outcomes: a successful `aws s3 cp` from inside the pod against `s3://$DATA_BUCKET/allowed/...`, and an `AccessDenied` against `s3://$DATA_BUCKET/secret/...`. Then dump the pod's effective identity with `aws sts get-caller-identity` from inside the pod and show it is the **IRSA role**, not the node instance role.

**Deliverables.** A file `notes/irsa-proof.md` containing:

1. The `kubectl exec` output of `aws sts get-caller-identity` showing the assumed-role ARN ends in the IRSA role, not the node role.
2. The successful read from `allowed/` and the `AccessDenied` from `secret/`.
3. Two sentences explaining the trust-policy condition that scopes the role to exactly one service account (`StringEquals` on the OIDC provider's `:sub`).

**Acceptance criteria.**

- `get-caller-identity` from inside the pod returns an ARN of the form `arn:aws:sts::<acct>:assumed-role/<IRSA-role>/botocore-session-...` — **not** the EKS node group instance role.
- The read from `allowed/` succeeds; the read from `secret/` returns `AccessDenied`.
- Your explanation correctly names the `:sub` condition (`system:serviceaccount:<ns>:<sa>`) as what binds the role to one pod identity.
- The cluster is **torn down** afterward (note the `cdk destroy` command and timestamp in the file).
- Committed.

**Hint.** Exec a debug shell: `kubectl exec -it deploy/fastapi -- /bin/sh`, then `aws sts get-caller-identity`. If it shows the node role, your service account is missing the `eks.amazonaws.com/role-arn` annotation or the pod predates the annotation (restart it). The IAM policy on the IRSA role should scope `s3:GetObject` to `arn:aws:s3:::$DATA_BUCKET/allowed/*` only — that single resource ARN is what produces the `AccessDenied` on `secret/`.

**Estimated time.** 1 hour 15 minutes.

---

## Problem 4 — The honest per-1M-request cost table

**Problem statement.** Using the **2026 list prices** from Lecture 1, build a per-1M-request cost model for the three deployments of the week, at a single traffic profile: **1,000,000 requests/month**, each request running **120 ms of compute** and returning a **20 KB** response. Compute the cost for each platform including the parts people forget. Use these assumptions:

- **Lambda:** 1 GB memory, 120 ms billed duration, `arm64`. Lambda price `$0.0000133334` per GB-second (arm64) + `$0.20` per 1M requests. Ignore free tier.
- **Fargate:** one task, 0.25 vCPU / 0.5 GB, running 24/7 for a 730-hour month (it does not scale to zero). Fargate `$0.04048` per vCPU-hour + `$0.004445` per GB-hour (`arm64`). Plus one ALB: `$0.0225/hr` + assume `2` LCU-hours average at `$0.008`/LCU-hour.
- **EKS:** the `$0.10/hr` control-plane fee for the month, plus **one** `c7g.large` Spot node assumed at `$0.026/hr` running 730 hours (the app shares the node, so attribute the whole node to it for this exercise).

For each platform also add **CloudWatch Logs ingestion** at `$0.50/GB`, assuming each platform emits `0.5 GB` of logs for the 1M requests.

**Deliverables.** A file `notes/cost-1m.md` with a table of the three platforms' monthly totals (compute, request/LB/control-plane component, and logs shown separately), plus a 150–250 word reading of the result.

**Acceptance criteria.**

- All three totals computed with components shown separately (no single mystery number).
- Lambda's compute line is computed as `1,000,000 × 0.120 s × 1 GB × $0.0000133334` plus the `$0.20` request charge.
- Fargate's and EKS's costs are dominated by the **always-on floor** (the task/node runs 730 hours regardless of the 1M requests), and your reading says so explicitly.
- The reading states the crossover intuition: at 1M req/month Lambda wins on price; the floor-based platforms only win once request volume is high enough to amortize the always-on cost.
- Committed.

**Hint.** Lambda compute: `1e6 × 0.120 × 1 × 0.0000133334 ≈ $1.60`, plus `$0.20` requests ≈ `$1.80` before logs. Fargate 0.25 vCPU: `730 × 0.25 × $0.04048 + 730 × 0.5 × $0.004445 ≈ $7.39 + $1.62 ≈ $9.01`, plus ALB `730 × ($0.0225 + 2×$0.008) ≈ $28.91`. EKS: control plane `730 × $0.10 = $73` + node `730 × $0.026 ≈ $18.98`. Add `0.5 GB × $0.50 = $0.25` logs to each. The numbers tell the story — write what they say.

**Estimated time.** 50 minutes.

---

## Problem 5 — Lambda Web Adapter cold-start budget

**Problem statement.** On the Lambda deployment from Exercise 3, measure the **cold-start penalty** and decide whether **provisioned concurrency** is worth it at a stated traffic shape. First, force a cold start (deploy a fresh version, then hit `/healthz` once) and capture the `Init Duration` from the CloudWatch log line. Then hit it ten times warm and record warm latency. Finally, compute the monthly cost of **2 units of provisioned concurrency** and state, in writing, the traffic shape at which you would turn it on versus leave it off.

**Deliverables.** A file `notes/cold-start.md` containing:

1. The cold-start log line showing `Init Duration` (and `Duration`).
2. A small table: cold p100 vs warm p50/p99 from your ten warm calls.
3. The provisioned-concurrency cost computation and a one-paragraph recommendation.

**Acceptance criteria.**

- A real `Init Duration` value is captured from CloudWatch Logs Insights or the `REPORT` line (not invented).
- The warm latencies are clearly lower than the cold p100, and the table reports both.
- The provisioned-concurrency cost is computed (`PC price/GB-s × memory × seconds-in-month × units`) and the recommendation ties the on/off decision to a concrete request-rate threshold (e.g. "below ~1 req/min the cold starts dominate, so PC; above steady traffic the function stays warm and PC is waste").
- Resources torn down; note the teardown command.
- Committed.

**Hint.** Find the init line in Logs Insights: `filter @type = "REPORT" | fields @initDuration, @duration | sort @timestamp desc | limit 5`. Container-image Lambdas (Web Adapter) have larger init than zip Lambdas — that is expected and is part of the trade-off you are documenting. Provisioned concurrency for 1 GB arm64 is billed per GB-second at the PC rate (`~$0.0000097` GB-s for arm64) for the whole month it is provisioned; `2 units × 1 GB × 2,628,000 s/month × rate` is the monthly floor. If you provision, you are paying for warm capacity 24/7 — only justified when cold-start p99 actually breaches an SLO.

**Estimated time.** 1 hour.

---

## Problem 6 — OpenTofu parity for the Fargate service + reflection

**Problem statement.** Re-implement the **Exercise 1 Fargate service** (cluster, task definition, service, ALB, target group, security groups, task execution role) in **OpenTofu** instead of CDK, deploying into the same Week-4 VPC. You do not need autoscaling — just a single task behind an ALB returning `{"status":"ok"}` on `/healthz`. Then reflect on the CDK-vs-OpenTofu trade-off for this kind of workload.

**Deliverables.** The OpenTofu config under `homework/p6-fargate-tofu/` (`main.tf`, `variables.tf`, `outputs.tf`) and a file `notes/cdk-vs-tofu.md` (200–300 words).

**Acceptance criteria.**

- `tofu init && tofu plan` succeeds against your account.
- The config reuses the **existing** Week-4 VPC and private subnets via `data` sources (it does not create a new VPC).
- `tofu apply` produces a reachable ALB; `curl http://<alb-dns>/healthz` returns `{"status":"ok"}` (paste the output into the note).
- The reflection answers: which tool you would reach for on an AWS-only shop vs a multi-cloud shop, and one concrete thing CDK does better and one thing OpenTofu does better for this stack.
- Everything torn down with `tofu destroy`; note the command.
- Committed.

**Hint.** Pull the VPC and subnets with `data "aws_vpc"` filtered by the Week-4 `Name` tag and `data "aws_subnets"` filtered by tier tag. Use the `aws_ecs_cluster`, `aws_ecs_task_definition` (with `container_definitions = jsonencode([...])`), `aws_ecs_service`, `aws_lb`, `aws_lb_target_group` (target_type `ip` for Fargate awsvpc), and `aws_lb_listener` resources. The task execution role needs the AWS-managed `AmazonECSTaskExecutionRolePolicy` so the agent can pull from ECR and write logs. Point the task at the **same ECR image** you built in Exercise 1 — no rebuild needed.

**Estimated time.** 1 hour 15 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 40 min |
| 2 | 1 h 0 min |
| 3 | 1 h 15 min |
| 4 | 50 min |
| 5 | 1 h 0 min |
| 6 | 1 h 15 min |
| **Total** | **~6 h 0 min** |

---

## Grading rubric

Total **100 points**. A pass is 70.

| Criterion | Points | What earns full marks |
|-----------|-------:|-----------------------|
| **Instance-family judgment** (P1) | 15 | Four correct family+size picks with sound one-line justifications; io2 chosen for the high-IOPS volume; Graviton verdicts correct. |
| **Mixed-instances Spot ASG** (P2) | 15 | `OnDemandBaseCapacity: 1`, `price-capacity-optimized`, four+ types across two+ families; diversification rationale correct. |
| **IRSA proven by the negative** (P3) | 20 | Pod identity shown to be the IRSA role; allowed read succeeds and forbidden read returns `AccessDenied`; `:sub` condition explained; cluster torn down. |
| **Per-1M cost table** (P4) | 15 | Three totals with components split; Lambda math correct; always-on floor of Fargate/EKS identified; crossover intuition stated. |
| **Cold-start budget** (P5) | 15 | Real `Init Duration` captured; warm vs cold table; PC cost computed; on/off recommendation tied to a concrete request rate. |
| **OpenTofu parity + reflection** (P6) | 15 | `tofu apply` yields a working `/healthz`; reuses Week-4 VPC via data sources; reflection honest and specific. |
| **Hygiene (all)** | 5 | Every billable resource torn down; clean commits; no secrets or account IDs leaked in notes. |

**Automatic deductions.**

- −15 if the EKS cluster from P3 is left running after submission (a climbing control-plane line in Cost Explorer is the tell).
- −10 if any Fargate task, ALB, NAT Gateway, or EC2/ASG instance is left running after submission.
- −10 if any real account ID, access key, or OIDC provider URL with account context is committed in plaintext.
- −5 if `cdk synth` or `tofu plan` fails on any IaC problem.

When you've finished all six, push your repo and open the [mini-project](./mini-project/README.md) — it fuses the three-way benchmark into the one-page compute decision doc that the capstone's compute-hybrid layer is built on.
