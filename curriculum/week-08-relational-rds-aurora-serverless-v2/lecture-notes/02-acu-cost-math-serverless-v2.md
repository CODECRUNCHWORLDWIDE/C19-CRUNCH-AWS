# Lecture 2 — ACU Cost Math: When Aurora Serverless v2 Is Cheaper and When It's a Trap

> **Reading time:** ~70 minutes. **Hands-on time:** ~40 minutes (you build the spreadsheet and run the break-even formula on your own numbers).

Lecture 1 was the architecture. This lecture is the spreadsheet, and it is the most commercially important hour in the entire week. Aurora Serverless v2 (ASv2) is marketed as "it scales to match your load and you only pay for what you use." That sentence is true and it is also the bait. ASv2 is **not a different database** — it is the same Aurora cluster from Lecture 1, with the same shared-storage engine, with the *instance billing mode* swapped from "fixed instance class, billed per hour whether busy or idle" to "elastic capacity in ACUs, billed per second of capacity provisioned." Everything that makes it attractive (no idle waste, instant-ish scaling) and everything that makes it a trap (per-ACU price premium, the floor you pay at 3 a.m., the scale-up stall) falls out of that one change. By the end of this lecture you can compute the monthly cost of any ASv2 configuration by hand, compute the cost of the equivalent provisioned cluster, and find the **break-even point** where one beats the other — which is exactly what the week's challenge asks you to produce across three load profiles.

> **A note on the dollar figures.** The *rates* below (per-ACU-hour, per-instance-hour) are illustrative `us-east-1` numbers in the right ballpark for 2026. AWS changes pricing; the **method** is what you memorize, and you re-pull the live rates from <https://aws.amazon.com/rds/aurora/pricing/> before any real decision. The break-even *formula* does not change when the rates do.

## 2.1 — What an ACU actually is

An **Aurora Capacity Unit (ACU)** is a bundle of compute resources: **approximately 2 GiB of RAM** plus a corresponding, AWS-managed slice of vCPU and network bandwidth. You do not pick CPU and memory separately — you pick a *number of ACUs*, and AWS gives you the bundle. The cluster is configured with a **range**: `minCapacity` and `maxCapacity`, each in 0.5-ACU increments, from **0.5 ACU** up to **256 ACU**. The cluster's actual capacity floats inside that range, second by second, tracking CPU, memory pressure, and the number/intensity of connections.

Billing is **per second** (with a 1-second minimum), at a per-ACU-hour rate. Call the rate `R_acu`. A useful 2026 ballpark for Aurora PostgreSQL Standard in `us-east-1` is:

```
R_acu ≈ $0.12 per ACU-hour
```

So a cluster sitting at a steady 4 ACU for one hour costs `4 × $0.12 = $0.48`. If it sat at 4 ACU for the whole month (730 hours): `4 × $0.12 × 730 = $350.40` per writer instance. Readers in a Serverless v2 cluster are *also* ASv2 instances with their own capacity, billed the same way and scaling independently.

**Scale-to-zero / auto-pause.** Since the 2024–2025 updates, ASv2 can set `minCapacity = 0` and truly pause an idle cluster to zero ACU after an inactivity window, resuming on the next connection (with a resume latency, typically a handful of seconds). When paused you pay **$0 for compute** (you still pay for storage). This is genuinely new and it changes the dev/test math dramatically — but it is a *trap of its own* for anything latency-sensitive, because the first connection after a pause eats the resume penalty.

## 2.2 — The provisioned comparator, priced the same way

To find a break-even you need the other side. A **provisioned** Aurora instance is billed per hour at a fixed rate by instance class, regardless of load. The relevant memory-optimized Graviton classes and rough 2026 `us-east-1` rates:

| Class | vCPU | RAM (GiB) | ~ACU-equivalent (RAM/2) | ~$/hour | ~$/month (730h) |
|---|---:|---:|---:|---:|---:|
| `db.r7g.large`   | 2  | 16  | 8   | $0.276 | $201 |
| `db.r7g.xlarge`  | 4  | 32  | 16  | $0.552 | $403 |
| `db.r7g.2xlarge` | 8  | 64  | 32  | $1.104 | $806 |
| `db.r7g.4xlarge` | 16 | 128 | 64  | $2.208 | $1,612 |

The crucial column is **"~ACU-equivalent (RAM/2)"**: since 1 ACU ≈ 2 GiB RAM, a `db.r7g.large` (16 GiB) is roughly **8 ACU** of capacity. Now compare the *rates per unit of capacity*:

- Provisioned `db.r7g.large`: `$0.276 / 8 ACU-equiv = $0.0345 per ACU-equiv-hour`.
- Serverless v2: `$0.12 per ACU-hour`.

**An ASv2 ACU costs roughly 3–4× a provisioned ACU-equivalent, hour for hour, at full capacity.** (Older comparisons quote ~2×; the gap widened as Graviton provisioned rates dropped. Re-pull the live numbers — but it is *always a premium*, never a discount, at equal sustained capacity.) That is the entire economic story in one line:

> **Serverless v2 charges a premium per unit of capacity. You come out ahead only if the capacity you *avoid paying for* (idle troughs, off-hours, unprovisioned headroom) is worth more than the premium you pay on the capacity you *do* use.**

## 2.3 — The break-even formula

Here is the math, made explicit. Over a billing window of `H` hours, let the ASv2 capacity at time `t` be `acu(t)`. Then:

```
Cost_serverless = R_acu × ∫ acu(t) dt        (per instance; sum over writer + readers)
                = R_acu × (average ACU over the window) × H
```

For a provisioned instance of capacity `C_acu` (its ACU-equivalent) running the whole window:

```
Cost_provisioned = R_prov × H               (R_prov is the instance's $/hour)
```

Set them equal and solve for the **average ACU at which they cost the same**:

```
R_acu × avgACU × H = R_prov × H
avgACU_breakeven   = R_prov / R_acu
```

The `H` cancels. The break-even depends only on the rates. Plug in the `db.r7g.large` comparator:

```
avgACU_breakeven = $0.276 / $0.12 ≈ 2.3 ACU
```

**Read that as the rule of thumb you will quote in design reviews:** for a `db.r7g.large`-class workload, if your ASv2 cluster's *time-averaged* capacity is **below ~2.3 ACU**, Serverless v2 is cheaper. Above it, the provisioned instance is cheaper — and the more steadily you sit above it, the worse ASv2 looks, because you are paying the 3–4× premium on every ACU all day.

Generalize: `avgACU_breakeven = R_prov / R_acu`. For `db.r7g.xlarge`: `$0.552 / $0.12 ≈ 4.6 ACU`. For `db.r7g.2xlarge`: `$1.104 / $0.12 ≈ 9.2 ACU`. The break-even average ACU is always roughly **(instance ACU-equivalent) ÷ 3.5** — i.e., you have to be idle most of the time for ASv2 to win against the provisioned box of the same peak size.

## 2.4 — The three load profiles, worked

The challenge has you measure three profiles. Here they are with numbers so you know what "good" looks like. Take the comparator as a single `db.r7g.large` writer (`$0.276/h`, 8 ACU-equiv) and an ASv2 writer configured `0.5–8 ACU`. One month = 730 hours.

**Profile A — Steady production (the trap).** The app holds a flat ~6 ACU of load 24/7 (busy enough to need the box, never idle).

```
Provisioned: $0.276 × 730                     = $201/mo
Serverless:  6 ACU × $0.12 × 730              = $525/mo
```

ASv2 costs **2.6× more**. This is the canonical trap: a steady production workload on Serverless v2 because someone read the marketing. The fix is provisioned, ideally with a Reserved Instance / Aurora compute Savings-Plan-equivalent on top (another ~30–40% off the $201). **Steady load → provisioned, always.**

**Profile B — Bursty (it depends, and the average is what matters).** The app idles at 0.75 ACU for 20 hours a day and bursts to 8 ACU for 4 hours (business peak).

```
avg ACU = (0.75 × 20 + 8 × 4) / 24 = (15 + 32) / 24 = 1.96 ACU
Serverless:  1.96 × $0.12 × 730               = $172/mo
Provisioned (sized for the 8-ACU peak = r7g.large): $201/mo
```

Here ASv2 wins, **$172 vs $201** — because the time-averaged capacity (1.96 ACU) sits *below* the 2.3-ACU break-even. But notice how *close* it is, and how sensitive it is to the burst: widen the peak to 6 hours and the average climbs to 2.5 ACU and ASv2 *loses*. **Bursty load → compute the average; do not eyeball it.** This is exactly why the challenge makes you measure, not guess.

**Profile C — Idle-heavy dev/test (the slam dunk).** A dev cluster used ~2 hours on a workday, idle nights and weekends. With `minCapacity = 0` and auto-pause, it sits at 0 ACU ~90% of the time and ~2 ACU when in use.

```
Active hours/mo ≈ 2h × 22 workdays = 44h at ~2 ACU; paused otherwise.
Serverless:  2 ACU × $0.12 × 44h              ≈ $10.56/mo compute
Provisioned (smallest, db.t4g.medium-equivalent or r7g.large idling): $50–$201/mo
```

ASv2 with scale-to-zero is **5–20× cheaper** for this profile. This is where Serverless v2 is unambiguously the right call: dev/test, per-tenant micro-clusters in a SaaS that are mostly idle, unpredictable early-stage product traffic before you know your steady-state. **Idle-heavy → Serverless v2, use min=0.**

Tabulate it — this table is the deliverable shape for the challenge:

| Profile | avg ACU | ASv2 $/mo | Provisioned $/mo | Winner | Margin |
|---|---:|---:|---:|---|---:|
| A — Steady (~6 ACU 24/7) | 6.00 | $525 | $201 | **Provisioned** | 2.6× |
| B — Bursty (4h peak) | 1.96 | $172 | $201 | **Serverless v2** | 1.17× |
| C — Idle dev/test (min=0) | ~0.12 effective | ~$11 | ~$50–201 | **Serverless v2** | 5–20× |

## 2.5 — The five hidden costs that move the break-even

The formula in §2.3 is the first-order answer. Five real-world factors shift it, and missing any of them is how engineers get the decision wrong:

**1. The floor (`minCapacity`) is billed even when idle.** If you set `minCapacity = 4` "to avoid scale-up stalls," you pay `4 × $0.12 × 730 = $350/mo` *minimum*, before a single query runs. A non-zero floor is the most common ASv2 cost mistake. The floor is insurance against the cold-buffer problem (next point); price the insurance. If you can tolerate `min=0.5` or `min=0`, do.

**2. The cold-buffer / scale-up stall.** ASv2 scales fast (capacity can roughly double in seconds), but scaling *up* does not instantly warm the buffer cache. A cluster that scaled from 0.5 to 8 ACU under a traffic spike has 8 ACU of CPU but a buffer cache that was sized for 0.5 ACU moments ago — so the first wave of the spike hits disk (storage I/O) while the cache refills. For latency-sensitive workloads (p99 SLOs, checkout paths), this stall is unacceptable, and the "fix" is a higher floor — which, per point 1, erodes the cost advantage. **Latency-sensitive + spiky is the worst case for ASv2's economics**, because you are forced to pay a high floor *and* you got ASv2 for the spikes.

**3. Readers scale independently and add up.** A writer + 2 readers, each ASv2, each with a floor, triples the floor cost. Three readers at `min=2` is `3 × 2 × $0.12 × 730 = $1,051/mo` of floor alone. People forget the readers when they estimate.

**4. I/O-Optimized vs Standard.** Aurora **Standard** bills storage + **per-I/O-request**. Aurora **I/O-Optimized** bills *no* per-I/O charge but a ~25% higher per-ACU/per-instance compute rate and ~2.25× the storage rate. The break-even is roughly **"if I/O is more than ~25% of your Standard bill, switch to I/O-Optimized."** For write-heavy or full-table-rewrite-heavy workloads (recall Lecture 1's migration I/O), I/O-Optimized often wins and *also* makes your bill predictable (no I/O surprise from a `VACUUM FULL`). This applies to both provisioned and Serverless v2.

**5. RDS Proxy is not free.** The proxy you add on Tuesday is billed per vCPU-hour of the instance(s) it fronts. It is usually worth it (it prevents `max_connections` meltdown from a Lambda/EKS fleet, and it lets you run a *smaller* instance because you are not paying RAM for thousands of idle backend connections), but it is a line item. Include it.

## 2.6 — A pricing function you can actually run

Reduce the whole lecture to code you can call. Drop this into a file and run it against your measured average-ACU numbers from the challenge. It is plain Python, no dependencies.

```python
#!/usr/bin/env python3
"""Aurora Serverless v2 vs provisioned break-even calculator.

Rates are illustrative us-east-1 2026 ballparks. Re-pull live numbers from
https://aws.amazon.com/rds/aurora/pricing/ before any real decision.
"""
from dataclasses import dataclass

R_ACU = 0.12          # $ per ACU-hour (Serverless v2, Standard)
HOURS_PER_MONTH = 730

# Provisioned class -> ($/hour, ACU-equivalent = RAM_GiB / 2)
PROVISIONED = {
    "db.r7g.large":   (0.276, 8),
    "db.r7g.xlarge":  (0.552, 16),
    "db.r7g.2xlarge": (1.104, 32),
    "db.r7g.4xlarge": (2.208, 64),
}


@dataclass
class Instance:
    """One node: either serverless (avg_acu set) or provisioned (klass set)."""
    avg_acu: float | None = None      # serverless: time-averaged ACU over the window
    klass: str | None = None          # provisioned: an entry in PROVISIONED


def monthly_cost(node: Instance) -> float:
    if node.klass is not None:
        rate, _ = PROVISIONED[node.klass]
        return rate * HOURS_PER_MONTH
    assert node.avg_acu is not None, "serverless node needs avg_acu"
    return node.avg_acu * R_ACU * HOURS_PER_MONTH


def breakeven_avg_acu(klass: str) -> float:
    """Average ACU at which serverless == this provisioned class."""
    rate, _ = PROVISIONED[klass]
    return rate / R_ACU


def cluster_cost(nodes: list[Instance]) -> float:
    return sum(monthly_cost(n) for n in nodes)


if __name__ == "__main__":
    # Profile B from the lecture: 1 writer + 2 readers, all serverless, avg 1.96 ACU each
    serverless_cluster = [Instance(avg_acu=1.96) for _ in range(3)]
    # Provisioned comparator: 1 writer + 2 readers, all db.r7g.large
    provisioned_cluster = [Instance(klass="db.r7g.large") for _ in range(3)]

    sv = cluster_cost(serverless_cluster)
    pr = cluster_cost(provisioned_cluster)
    be = breakeven_avg_acu("db.r7g.large")

    print(f"Serverless v2 cluster (3 x 1.96 ACU avg): ${sv:,.2f}/mo")
    print(f"Provisioned  cluster (3 x db.r7g.large):  ${pr:,.2f}/mo")
    print(f"Break-even average ACU per node:           {be:.2f} ACU")
    print("Winner:", "Serverless v2" if sv < pr else "Provisioned")
```

Run it:

```bash
python3 breakeven.py
```

Expected output:

```
Serverless v2 cluster (3 x 1.96 ACU avg): $515.26/mo
Provisioned  cluster (3 x db.r7g.large):  $604.44/mo
Break-even average ACU per node:           2.30 ACU
Winner: Serverless v2
```

Note the cluster-level result: even though *per-node* Profile B was close, across a 3-node cluster the absolute dollar gap is ~$89/mo. Multiply by a fleet of per-tenant clusters and the decision is worth real money — which is the entire reason a senior engineer is expected to do this math instead of clicking the "Serverless" radio button because it sounds modern.

## 2.7 — How to *measure* average ACU (not guess it)

The formula needs `avgACU`, and the only honest way to get it is from CloudWatch, not from intuition. ASv2 publishes the `ServerlessDatabaseCapacity` metric (current ACU) and `ACUUtilization` per instance. To get the time-averaged ACU over a window:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name ServerlessDatabaseCapacity \
  --dimensions Name=DBInstanceIdentifier,Value=week8-asv2-writer \
  --start-time "$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time   "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 3600 \
  --statistics Average \
  --query 'sort_by(Datapoints,&Timestamp)[].Average' \
  --output text
```

Average those hourly averages to get the window's `avgACU`, feed it into `breakeven.py`, and you have a *measured* — not assumed — decision. That is the deliverable the challenge grades: a measured average ACU per profile, run through the formula, with the winner named and the dollar margin stated.

## 2.8 — The decision tree (commit this to memory)

When someone in a design review asks "provisioned or Serverless v2?", you do not say "it depends" and trail off. You walk this tree:

1. **Is the load steady (utilization rarely dips below ~half the peak)?** → **Provisioned**, plus a Reserved/Savings commitment. ASv2 will cost 2–3×. (Profile A.)
2. **Is it dev/test, or a mostly-idle per-tenant cluster?** → **Serverless v2 with `min=0`** (scale-to-zero). 5–20× cheaper, and you do not care about the resume stall. (Profile C.)
3. **Is it bursty with real idle troughs?** → **Measure the time-averaged ACU.** If `avgACU < R_prov/R_acu` (~2.3 ACU for an r7g.large-shaped peak), Serverless v2 wins. If above, provisioned wins. (Profile B.)
4. **Is it latency-sensitive *and* spiky (p99 SLO on a checkout path)?** → **Provisioned**, or ASv2 with a high floor — but recognize the high floor erases the savings, so usually **provisioned**. The scale-up stall (§2.5.2) is the deal-breaker.
5. **Is it write-heavy / I/O-heavy (lots of `UPDATE`, big rewrites)?** → Layer the **I/O-Optimized** decision on top of either: if I/O > ~25% of a Standard bill, switch.

## 2.9 — The scale-to-zero math, in detail

The 2024–2025 addition of `minCapacity = 0` (true auto-pause to zero ACU) is the single biggest change to the ASv2 cost story since launch, and it deserves its own treatment because it both *creates* the best use case and *introduces* a new trap.

How it works: when a cluster set to `min=0` sees no connections for the configured inactivity window (a handful of minutes), it pauses to **zero ACU**. Compute billing stops entirely — you pay only storage. On the next connection, it resumes, ramping from 0 to the needed capacity. The resume is not instant: the first connection after a pause eats a **resume latency** of typically a few seconds (the engine has to come back up and warm enough cache to serve the query).

The cost win is dramatic for the right shape. Take a per-tenant analytical cluster that is genuinely used for an hour a day at ~2 ACU and idle the other 23:

```
With min=0.5 (old floor):
  active:  2 ACU × 1h × $0.12                 = $0.24/day
  idle:    0.5 ACU × 23h × $0.12              = $1.38/day   <- the floor tax
  total                                       = $1.62/day  ≈ $49/mo

With min=0 (scale-to-zero):
  active:  2 ACU × 1h × $0.12                 = $0.24/day
  idle:    0 ACU × 23h × $0.12                = $0.00/day
  total                                       = $0.24/day  ≈ $7/mo + storage
```

The floor tax was **86%** of the old bill. Removing it cuts the cluster from ~$49 to ~$7/mo. Now multiply by a fleet: 200 mostly-idle per-tenant clusters go from ~$9,800/mo to ~$1,400/mo. *That* is the number that makes per-tenant micro-clusters a real architecture and not a curiosity — and it is exactly the kind of figure the design exam expects you to produce when someone proposes "a cluster per tenant."

The trap: `min=0` is wrong for anything latency-sensitive. The resume latency lands on the *first user* after an idle period — a checkout, a login, an API call that now takes 3–5 extra seconds. For a customer-facing OLTP path, that is a visible regression and an SLO violation. **Scale-to-zero is for workloads where a cold first-request is acceptable: dev/test, internal tooling, batch analytics, mostly-idle per-tenant stores that tolerate a warm-up.** It is not for the front door.

## 2.10 — A worked sensitivity analysis (why "measure, don't guess" is the whole lesson)

The reason the challenge makes you *measure* the average ACU rather than estimate it is that the decision is exquisitely sensitive to small changes in the load shape. Walk the Profile-B burst example and watch the winner flip as the peak widens:

| Peak duration/day | Idle ACU (rest) | Peak ACU | avg ACU | ASv2 $/mo | Provisioned $/mo | Winner |
|---|---:|---:|---:|---:|---:|---|
| 2h | 0.75 | 8 | 1.35 | $118 | $201 | Serverless v2 |
| 4h | 0.75 | 8 | 1.96 | $172 | $201 | Serverless v2 |
| 6h | 0.75 | 8 | 2.56 | $224 | $201 | **Provisioned** |
| 8h | 0.75 | 8 | 3.17 | $278 | $201 | **Provisioned** |

The winner flips somewhere between a 4-hour and a 6-hour daily peak — right around the **2.3-ACU break-even** from §2.3. A two-hour difference in your estimate of "how long is the busy window" changes the *correct architecture decision*. No human eyeballs that reliably from a traffic chart. You pull the `ServerlessDatabaseCapacity` metric, average it, and let the number decide. An engineer who guesses "it's bursty, use Serverless" gets it wrong half the time; an engineer who measures gets it right every time. The 30 minutes of CloudWatch work is the difference.

## 2.10a — Per-tenant SaaS: the architecture the cost math unlocks

The single most important commercial application of everything in this lecture is the **per-tenant cluster** pattern for multi-tenant SaaS, and it is exactly what the Wednesday design exam will probe. Lay the three isolation models against the ACU math:

- **Pool** — all tenants in one shared cluster, separated by a `tenant_id` column and row-level security. One provisioned `db.r7g.2xlarge` ($806/mo) serves all 500 tenants. Cheapest per tenant ($1.61/tenant/mo), but a noisy tenant degrades everyone and a `tenant_id`-filter bug leaks data across tenants.
- **Silo** — one cluster per tenant. Hard isolation (separate KMS keys, separate failure domains, per-tenant PITR). Historically expensive — 500 provisioned `db.r7g.large` clusters at $201/mo = **$100,500/mo**, absurd. This is why silo was "only for the regulated enterprise tier."
- **Bridge** — schema-per-tenant in shared clusters. A middle ground.

Now apply scale-to-zero Serverless v2 to the silo model and watch it become viable:

```
500 silo tenants, each a Serverless v2 cluster, min=0, avg 0.3 ACU effective
  (mostly idle, occasional light use):
    500 × 0.3 ACU × $0.12 × 730                 = $13,140/mo compute
  vs the old provisioned silo:
    500 × $201                                  = $100,500/mo
  vs pool (one r7g.2xlarge):
    $806/mo
```

Scale-to-zero cuts the silo cost by **87%** — but pool is still **16× cheaper** than even the cheap silo. So the decision tree for the design exam:

1. **Default to pool** for cost, unless isolation requirements forbid it.
2. **Go silo** when a tenant demands hard isolation (compliance, a contractual single-tenant guarantee, per-tenant encryption keys) — and use **Serverless v2 with min=0** to make the idle-heavy silo affordable.
3. **Mix**: pool for the long tail of small tenants, silo-on-Serverless-v2 for the enterprise tier that pays for isolation. This hybrid is what most mature SaaS converges on, and "I'd pool the free tier and silo the enterprise tier on Serverless-v2-with-min=0, here are the two cost numbers" is a senior-level answer.

The point that ties it back to this lecture: **you cannot have this conversation without the ACU math.** "Silo is too expensive" was true on provisioned and is false on scale-to-zero Serverless v2 for idle-heavy tenants. The architecture decision *changed* because the billing mode changed. That is why the math is not a finance detail — it is an architecture input.

## 2.10b — RDS Proxy in the cost equation

The RDS Proxy you add on Tuesday is billed per vCPU-hour of the instance capacity it fronts (a published per-vCPU-hour rate; re-check pricing). It looks like pure added cost, but it frequently *saves* money by letting you run a smaller database instance:

- Without a proxy, a fleet of 50 EKS pods (or a Lambda function at 200 concurrent executions) opens hundreds-to-thousands of direct connections. Each PostgreSQL backend connection costs ~5–10 MiB of server RAM, so 1,000 connections is 5–10 GiB of RAM spent on *connection overhead* before a single query runs. You size the instance up just to hold the connections.
- With a proxy multiplexing those clients onto, say, 40 backend connections, the database needs far less RAM for connections, so you can run a smaller (cheaper) instance — or, on Serverless v2, sit at a lower ACU because you are not burning capacity on idle backends.

So the proxy's line item is offset (often more than offset) by the smaller database it enables. The cost framing: **add the proxy's per-vCPU-hour cost, then subtract the instance/ACU savings it buys.** For a large fleet the net is usually negative (you save money); for a tiny single-client workload the proxy is pure overhead and you skip it. Include it in the challenge's accounting either way.

## 2.11 — Where the comparison gets murky: Reserved Instances and Savings commitments

The §2.2 provisioned rates are **on-demand**. In production you rarely run steady provisioned Aurora on-demand — you buy a commitment. Aurora supports Reserved Instances (1- or 3-year, all-upfront / partial / no-upfront) that discount the provisioned instance rate by roughly **30–55%** depending on term and payment. That *widens* the gap against Serverless v2 for steady workloads:

```
Profile A (steady ~6 ACU), per writer node:
  Serverless v2:                  6 × $0.12 × 730        = $525/mo
  Provisioned on-demand:          $0.276 × 730           = $201/mo
  Provisioned 1yr RI (~40% off):  $0.166 × 730           = $121/mo
```

With a Reserved Instance, the steady workload is **4.3× cheaper** on provisioned than on Serverless v2. This is why "steady → provisioned" in the decision tree is not a close call — once you layer the commitment on, ASv2 for steady load is indefensible. Serverless v2 has **no** equivalent long-term discount (it is inherently usage-based), so it cannot claw the gap back. The corollary: ASv2's advantage is confined to workloads where the *avoided idle capacity* outweighs *both* the per-ACU premium *and* the commitment discount you forgo. That is a narrower window than the marketing implies — which is the whole reason this lecture exists.

## 2.12 — What to take into the challenge

- An **ACU ≈ 2 GiB RAM** + matching CPU, billed **per second** at ~`$0.12`/ACU-hour. The range is **0.5–256 ACU** (or **0** with scale-to-zero).
- An ASv2 ACU costs a **3–4× premium** over a provisioned ACU-equivalent. ASv2 only wins by *avoiding idle capacity*, not by being cheaper per unit.
- **Break-even average ACU = `R_prov / R_acu`** (~2.3 ACU for an r7g.large-shaped workload). The window length cancels — it is rate-only.
- **Steady → provisioned. Idle/dev → Serverless v2 with min=0. Bursty → measure the average and apply the formula.**
- The five hidden costs: the **floor**, the **scale-up/cold-buffer stall**, **independent reader scaling**, **I/O-Optimized vs Standard**, and **RDS Proxy**.
- Get `avgACU` from the **`ServerlessDatabaseCapacity`** CloudWatch metric — **measure, don't guess**.

The challenge this week converts your Exercise-1 provisioned cluster to Serverless v2 `0.5–8 ACU`, re-runs `pgbench` under steady/burst/idle profiles, pulls the measured average ACU from CloudWatch, and produces exactly the §2.4 table for *your* numbers with the break-even called. Bring this lecture to the spreadsheet.

## 2.13 — Five cost mistakes that show up in real Aurora bills

A field guide to the ways teams overpay, so you can spot them in a review:

1. **A non-zero floor on an idle cluster.** `minCapacity = 2` on a dev cluster that is idle 90% of the time pays `2 × $0.12 × 730 = $350/mo` for nothing. Fix: `min=0` with auto-pause. The single most common ASv2 overspend.
2. **Serverless v2 on a steady production workload.** The §2.4 Profile A trap: 2–3× over-pay versus provisioned, 4× once you add a Reserved Instance. Fix: provisioned + RI for anything with sustained utilization.
3. **Forgetting the readers.** Estimating "the writer averages 2 ACU" and ignoring that two readers each carry their own floor and their own scaled capacity. A 3-node cluster is three ACU bills, not one.
4. **Aurora Standard on a write-heavy / migration-heavy workload.** Per-I/O charges balloon under heavy `UPDATE` traffic or frequent table rewrites (Lecture 1 §1.12a). Fix: I/O-Optimized if I/O exceeds ~25% of the Standard bill — and it makes the bill predictable.
5. **Orphaned manual snapshots and retained cross-region copies.** Snapshots outlive the cluster and bill per GiB-month forever. A forgotten cross-region copy bills in *two* regions. Fix: a lifecycle/cleanup discipline and the mini-project's "describe returns `[]`" teardown check.

Every one of these is a number you can find in Cost Explorer and a line you can defend removing. FinOps on the data tier is just this: know the five traps, audit for them, and quote the saving. That is the habit Week 8 builds and the capstone's cost report demands.

## 2.14 — The one-paragraph version (for when someone asks in a hallway)

"Aurora Serverless v2 bills capacity in ACUs — about 2 GiB of RAM each — per second, at roughly triple the per-unit price of a provisioned instance. It only saves money by *avoiding idle capacity*, so it wins for dev/test and mostly-idle per-tenant clusters (especially with scale-to-zero), loses badly on steady production load (use provisioned plus a Reserved Instance there), and is a coin-flip on bursty load that you settle by measuring the time-averaged ACU from CloudWatch and comparing it to the break-even average ACU, which is just the provisioned hourly rate divided by the per-ACU-hour rate — about 2.3 ACU for an r7g.large-shaped workload. Watch the floor, the readers, the scale-up stall, and I/O-Optimized." If you can say that cold, you have the lecture.
