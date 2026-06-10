# Challenge 1 — The three-way benchmark: cold-start, p50/p99, and per-1M cost

> **Estimated time:** 90–120 minutes (plus the deploy time you already spent in the exercises). This is the canonical shape of senior compute work: you do not *believe* a platform is faster or cheaper, you *show* it, with a table anyone can reproduce.

You have deployed the same FastAPI service three ways:

- **Fargate** — ECS Fargate behind an ALB (Exercise 1).
- **EKS** — Karpenter Spot Graviton nodes behind an ALB, IRSA-scoped (Exercise 2).
- **Lambda** — container-image Lambda + HTTP API + CloudFront (Exercise 3).

Your job is to measure all three on the three axes that decide real design reviews — **cold-start latency, steady-state p50/p99 latency, and per-1M-request cost** — and produce one defensible table plus a short interpretation. The table is the artifact the mini-project's decision doc is built on.

## The rules of a fair benchmark

A benchmark that is not fair is worse than no benchmark, because it launders a prejudice into a number. Hold these constant across all three platforms:

1. **Same region.** All three in the same region (the one your Week-4 VPC lives in). Cross-region latency would swamp the signal.
2. **Same request mix.** Use the same three endpoints in the same ratio. A reasonable mix: 70% `/healthz` (trivial), 20% `/compute?n=200000` (CPU burn), 10% `/read?key=public/hello.txt` (S3 round-trip).
3. **Same load generator and the same invocation.** Pick `hey` or `oha`. Use identical `-z` (duration), `-c` (concurrency), and target paths. Document the exact command in your results.
4. **Warm before you measure the warm path.** Send a warm-up burst, then measure. Cold start is measured *separately and deliberately* (see below) — never mixed into the steady-state percentiles.
5. **Right-size comparably.** Lambda at 1024 MB (~0.58 vCPU); Fargate task at 0.5 vCPU / 1 GB; EKS pod requesting 0.5 vCPU / 512 MB on a Spot Graviton node. Note the differences in your writeup — they are part of the honesty.

## Step 1 — Measure cold start (the number everyone asks about)

**Lambda.** The cleanest cold-start signal in the building. Force a cold environment, send one request, read the `Init Duration` from the `REPORT` log line:

```bash
FN=$(aws cloudformation describe-stacks --stack-name LambdaApigwCloudfrontStack \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionName'].OutputValue" --output text)

# Bump the function config to evict all warm environments, then hit it once:
aws lambda update-function-configuration --function-name "$FN" \
  --description "force-cold-$(date +%s)" >/dev/null
sleep 5
API=$(aws cloudformation describe-stacks --stack-name LambdaApigwCloudfrontStack \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
curl -s -o /dev/null -w "first-request total: %{time_total}s\n" "$API/healthz"

# The authoritative number is in the log, not curl's wall time:
aws logs filter-log-events --log-group-name "/aws/lambda/$FN" \
  --filter-pattern "REPORT" --query "events[-1].message" --output text
# -> ...Init Duration: 1180.42 ms ... Duration: 6.10 ms ...
```

Repeat the force-cold cycle ~5 times and report the **median cold-start `Init Duration`** and the **median warm `Duration`**. (Measure against the direct `ApiUrl`, not CloudFront, so CloudFront's own latency does not contaminate the Lambda cold-start number. Measure CloudFront separately if you want the edge contribution.)

**Fargate.** "Cold start" means *task start* — scale the service from 0 to 1 task and time until the ALB target is healthy:

```bash
CLUSTER=...; SERVICE=...   # from your Exercise 1 stack outputs
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" --desired-count 0 >/dev/null
# wait until 0 running, then:
START=$(date +%s)
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" --desired-count 1 >/dev/null
# poll the target group until one target is "healthy", then:
echo "task cold start (0->healthy): $(( $(date +%s) - START ))s"
```

Expect tens of seconds — image pull (mitigated by your Week-4 ECR endpoint), container boot, then ALB health-check passes. Report it as a **second-scale** number; it is a different animal from Lambda's ms-scale init.

**EKS.** The worst-case cold start, and the most interesting: scale the Deployment from 0 and watch the cascade — pending pod → Karpenter launches a Spot node (~30–60 s) → pod schedules → readiness passes:

```bash
kubectl scale deployment/fastapi -n app --replicas=0
# let Karpenter consolidate the now-empty node away (consolidateAfter: 1m), then:
START=$(date +%s)
kubectl scale deployment/fastapi -n app --replicas=1
kubectl rollout status deployment/fastapi -n app --timeout=300s
echo "pod cold start incl. node launch: $(( $(date +%s) - START ))s"
```

Then repeat **without** forcing the node away (pod scheduled onto an existing warm node) to separate "pod start" from "pod start + node launch." Report both. This split is the whole point: EKS cold start depends entirely on whether a node is already there.

## Step 2 — Measure steady-state p50/p99

Warm each platform, then run identical load. Example with `oha` (substitute your URLs):

```bash
# Warm-up burst (results discarded):
oha -z 20s -c 20 "$FARGATE_URL/healthz" >/dev/null

# Measured run — same flags for all three:
oha -z 60s -c 20 "$FARGATE_URL/compute?n=200000"
oha -z 60s -c 20 "$EKS_URL/compute?n=200000"
oha -z 60s -c 20 "$LAMBDA_CF_URL/compute?n=200000"
```

`oha` prints the latency histogram and the percentiles directly. Record **p50** and **p99** for each platform on each endpoint. (If you use `hey`, it prints the same distribution under "Latency distribution.") Run the S3-reading `/read` endpoint too — it exposes whether the S3 round-trip through a VPC endpoint vs Lambda's networking shows up.

## Step 3 — Compute per-1M-request cost

This is where most benchmarks cheat by pricing only the obvious line. Do not. Use Lecture 1 §6 as your worksheet and the live 2026 pricing pages (cite the region and date). For each platform compute:

- **Lambda:** `GB-seconds × $/GB-s + requests × $/1M`. At 1024 MB and your measured warm `Duration`, this is exact arithmetic. Add CloudWatch log ingestion at your observed log volume.
- **Fargate:** the **monthly** task cost (vCPU-hours + GB-hours) divided by your monthly request count, **plus** the ALB base + LCUs, **plus** NAT data if any of your traffic egresses through NAT. Fargate's per-request cost *falls* as traffic rises — show that by computing it at 1M and at 100M.
- **EKS:** the **$73/month control-plane fee** + Spot node-hours + ALB + EBS (if any), divided by request count. Compute it for **one service** (brutal per-request cost) **and** amortized across, say, 40 services sharing the cluster (where it wins). The crossover is the story.

State every assumption inline. A reviewer should be able to redo your arithmetic from your numbers.

## Step 4 — The table

Produce exactly this table (fill in *your* measured numbers; the values below are illustrative shape, not answers to copy):

```
| Platform        | Cold start (median)      | Warm p50 | Warm p99 | $/1M req (1 svc) | $/1M req (at scale) | Idle cost |
|-----------------|--------------------------|---------:|---------:|-----------------:|--------------------:|----------:|
| Lambda + CF     | ~1.2 s (init) / 6 ms warm |   ~8 ms |  ~340 ms |          ~$1.0   |              ~$1.0  |     $0    |
| ECS Fargate+ALB | ~45 s (task 0->healthy)   |  ~12 ms |   ~40 ms |         ~$35/mo  |   falls w/ traffic  |  per-task |
| EKS Spot + ALB  | ~70 s (incl. node) /      |  ~11 ms |   ~38 ms |        ~$110/mo  |   lowest at 40 svc  | $73/mo +  |
|                 | ~8 s (warm node)          |          |          |                  |                     |   nodes   |
```

## Acceptance criteria

- [ ] You report a **median cold start** for all three, with Lambda's `Init Duration`, Fargate's task-0-to-healthy time, and EKS's *two* numbers (warm-node and node-launch).
- [ ] You report **warm p50 and p99** for at least the `/compute` endpoint on all three, generated with the **same** load command (documented verbatim).
- [ ] You compute **per-1M-request cost** for all three, including at least one "forgotten" line item (NAT, LCU, control-plane fee, or log ingestion). EKS cost is shown for one service *and* amortized.
- [ ] You produce the **single comparison table** above with your real numbers.
- [ ] You write a **150–300 word interpretation** that names, for *this* workload at *this* scale, which platform wins and why — and identifies the traffic shape or scale at which the answer flips.
- [ ] You note the **platform on which you ran the load generator** and the region; a benchmark from a laptop in another continent measures your home WiFi, not the platform.
- [ ] You tore everything down (`aws eks list-clusters` is empty) after capturing the numbers.

## Going further (no extra grade)

- Add a **Fargate Spot** row (one capacity-provider change) and compare per-task cost to on-demand Fargate.
- Add **Lambda provisioned concurrency** (e.g. 2 pre-warmed envs) and show the cold-start p99 collapse — then price the standing GB-second charge so the trade-off is explicit.
- Re-run Lambda with **SnapStart** enabled (Python is supported in 2026) and compare the cold start to the cold container-image baseline.
- Port the Fargate task and EKS node pool to **Graviton arm64** (if not already) and re-measure — you should see ~20% off compute. (Exercises 1–3 already build arm64 images, so you may already be there.)
- Push **higher concurrency** (`-c 100`) and watch where each platform's p99 degrades: Lambda hits concurrency limits, Fargate needs more tasks (target-tracking autoscaling), EKS needs Karpenter to add a node mid-test. The shape of the degradation is itself a finding.

## Submission

Commit to your Week 5 repo at `challenges/challenge-01-three-way-benchmark/`:

- `results.md` — the comparison table, the exact load-generator commands, your cost arithmetic with cited 2026 pricing, and the 150–300 word interpretation.
- `raw/` — the raw `oha`/`hey` output files and the Lambda `REPORT` lines you pulled, so the grader can verify the percentiles came from real runs.

The grader re-runs your documented load command against your endpoints (or reviews your screenshots if torn down) and checks the numbers reproduce within ~30%. The most common review-fail: "the table claims Lambda p99 is 8 ms but the raw `oha` output shows 340 ms because the run included a cold start." Separate the cold path from the warm path, every time.

---

**References**

- AWS Lambda pricing & `REPORT` line fields: <https://aws.amazon.com/lambda/pricing/> and <https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html>
- AWS Fargate pricing: <https://aws.amazon.com/fargate/pricing/>
- Amazon EKS pricing (control-plane fee): <https://aws.amazon.com/eks/pricing/>
- Application Load Balancer pricing & LCUs: <https://aws.amazon.com/elasticloadbalancing/pricing/>
- `oha` load generator: <https://github.com/hatoo/oha>
- `hey` load generator: <https://github.com/rakyll/hey>
- CloudWatch Logs Insights (querying `Init Duration`): <https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html>
