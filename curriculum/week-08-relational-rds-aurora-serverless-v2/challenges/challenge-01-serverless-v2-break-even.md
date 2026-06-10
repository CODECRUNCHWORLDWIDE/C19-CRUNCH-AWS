# Challenge 1 — Aurora Serverless v2 Break-Even Analysis

> **Estimated time:** 120–150 minutes. Worth more than its time cost suggests — this is the exact analysis a senior engineer is paid to produce, and it is the kind of question a reviewer will fire at you in the mid-program design exam.

You have a provisioned Aurora cluster from Exercise 1 (writer + 2 readers, `db.r7g.large`). The product team is asking, "should we move this to Aurora Serverless v2 to save money?" The wrong engineer answers from intuition. **You answer with a measured break-even report.** This challenge has you convert the cluster to Serverless v2 (0.5–8 ACU), drive three realistic load profiles, capture the *measured* time-averaged ACU from CloudWatch, run it through the Lecture-2 break-even formula, and deliver a one-page decision with a recommendation per profile.

## What you will produce

A directory `challenge-01-break-even/` containing:

1. `serverless-stack.ts` — a CDK stack that deploys the same cluster shape **as Serverless v2** (`serverlessV2MinCapacity: 0.5`, `serverlessV2MaxCapacity: 8`).
2. `load-profiles.md` — the three load-driving recipes you ran (steady, burst, idle) with the exact `pgbench` commands.
3. `measurements.csv` — for each profile: the measured average ACU (from CloudWatch), the duration, and the computed monthly cost.
4. `breakeven.py` — the calculator from Lecture 2 §2.6, run against *your* measured numbers.
5. `REPORT.md` — the one-page decision: the §2.4-shape table filled with **your** numbers, the break-even average ACU, the per-profile recommendation, and the dollar margin.

## The starting point: convert the cluster to Serverless v2

The only change from Exercise 1 is the writer/reader instance type. Replace `ClusterInstance.provisioned(...)` with `ClusterInstance.serverlessV2(...)` and set the capacity range on the cluster.

```typescript
import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';

export class Week8ServerlessStack extends cdk.Stack {
  public readonly cluster: rds.DatabaseCluster;

  constructor(scope: Construct, id: string, props: cdk.StackProps & { vpc: ec2.IVpc }) {
    super(scope, id, props);

    this.cluster = new rds.DatabaseCluster(this, 'AuroraServerless', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_6,
      }),
      vpc: props.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      credentials: rds.Credentials.fromGeneratedSecret('crunchadmin', {
        secretName: 'week8/serverless/master',
      }),
      defaultDatabaseName: 'appdb',
      storageEncrypted: true,
      // --- the Serverless v2 capacity range -----------------------------
      serverlessV2MinCapacity: 0.5,   // floor billed even when idle
      serverlessV2MaxCapacity: 8,     // ceiling the cluster may scale to
      // -------------------------------------------------------------------
      writer: rds.ClusterInstance.serverlessV2('writer', {
        enablePerformanceInsights: true,
      }),
      readers: [
        rds.ClusterInstance.serverlessV2('reader1', { scaleWithWriter: true }),
        rds.ClusterInstance.serverlessV2('reader2', {}),
      ],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new cdk.CfnOutput(this, 'WriterEndpoint', { value: this.cluster.clusterEndpoint.hostname });
    new cdk.CfnOutput(this, 'ReaderEndpoint', { value: this.cluster.clusterReadEndpoint.hostname });
  }
}
```

> **Note on `scaleWithWriter`.** A reader marked `scaleWithWriter: true` tracks the writer's capacity so it is warm enough to be promoted on failover — relevant to the cold-buffer point from Lecture 2 §2.5.2. The second reader scales purely on its own load. Both choices have a cost; note which you made and why.

Deploy it (keep your Exercise-1 provisioned cluster's *measurements* for the comparison; you do not need both running at once):

```bash
cdk deploy Week8ServerlessStack
```

## The three load profiles

Connect from the Exercise-2 pod (or a bastion). Initialize a scale-10 dataset once: `pgbench -i -s 10 "host=$WRITER dbname=appdb user=crunchadmin"`. Then drive each profile and **let it run long enough for CloudWatch to capture a clean average** (at least 15–20 minutes per profile so the scaling settles).

**Profile A — Steady.** A flat, sustained write load that keeps the cluster busy continuously:

```bash
# sustained ~constant load for 20 minutes
pgbench -c 24 -j 8 -T 1200 "host=$WRITER dbname=appdb user=crunchadmin"
```

**Profile B — Burst.** Idle, then a sharp spike, repeated — so the time-average lands somewhere in the middle:

```bash
# alternate 2 min idle / 2 min heavy, for ~20 minutes:
for cycle in 1 2 3 4 5; do
  sleep 120                                                  # idle trough
  pgbench -c 32 -j 8 -T 120 "host=$WRITER dbname=appdb user=crunchadmin"  # spike
done
```

**Profile C — Idle.** Almost nothing — a single trickle of work, the dev/test shape:

```bash
# one tiny transaction every ~30s for 20 minutes (simulate a sleepy dev box):
for i in $(seq 1 40); do
  pgbench -c 1 -j 1 -t 1 "host=$WRITER dbname=appdb user=crunchadmin" >/dev/null
  sleep 30
done
```

> **Stretch the idle profile:** redeploy with `serverlessV2MinCapacity: 0` and re-run Profile C to see true scale-to-zero. Note the resume latency on the first transaction after a pause.

## Capture the measured average ACU

For each profile's window, pull `ServerlessDatabaseCapacity` and average it (Lecture 2 §2.7):

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name ServerlessDatabaseCapacity \
  --dimensions Name=DBInstanceIdentifier,Value=<your-asv2-writer-id> \
  --start-time "$(date -u -d '25 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time   "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 60 --statistics Average \
  --query 'Datapoints[].Average' --output text | tr '\t' '\n' \
  | awk '{ s += $1; n++ } END { printf "avg ACU over window: %.3f (n=%d)\n", s/n, n }'
```

Do this for the **writer and each reader** — readers scale independently and their ACU adds to the bill (Lecture 2 §2.5.3). Record everything in `measurements.csv`:

```csv
profile,node,avg_acu,window_minutes
A_steady,writer,5.92,20
A_steady,reader1,5.81,20
A_steady,reader2,2.10,20
B_burst,writer,1.94,20
...
```

## Run the formula and write the report

Run the Lecture-2 calculator against your measured averages, summing across writer + 2 readers:

```bash
python3 breakeven.py    # the script from Lecture 2 §2.6, edited with your avg_acu values
```

Then fill in the report table with **your** numbers:

| Profile | Σ avg ACU (3 nodes) | ASv2 $/mo | Provisioned $/mo (3× r7g.large) | Break-even avg ACU | Winner | Margin |
|---|---:|---:|---:|---:|---|---:|
| A — Steady | _your_ | _your_ | $604.44 | 2.30 | _your_ | _your_ |
| B — Burst  | _your_ | _your_ | $604.44 | 2.30 | _your_ | _your_ |
| C — Idle   | _your_ | _your_ | $604.44 | 2.30 | _your_ | _your_ |

## Acceptance criteria

You can mark this challenge done when:

- [ ] `Week8ServerlessStack` deploys a Serverless v2 cluster with `min=0.5, max=8` (and you ran the `min=0` stretch).
- [ ] You drove **all three profiles** with the documented `pgbench` recipes, each for ≥15 minutes.
- [ ] `measurements.csv` records the **measured** average ACU per node per profile, pulled from CloudWatch (not assumed).
- [ ] `breakeven.py` runs and prints the ASv2 vs provisioned monthly cost and the break-even average ACU per node.
- [ ] `REPORT.md` contains the filled table, the break-even ACU, and a **per-profile recommendation** with the dollar margin.
- [ ] Your recommendations match the Lecture-2 decision tree: **steady → provisioned, idle → Serverless v2 (min=0), burst → whichever the measured average says.**
- [ ] You name **at least two of the five hidden costs** (Lecture 2 §2.5) that you observed or accounted for — e.g., the reader floors, or the scale-up stall you saw at the start of a burst.
- [ ] `cdk destroy Week8ServerlessStack` leaves nothing billable.

## What "excellent" looks like

A pass produces the table. An **excellent** submission does three more things:

1. **Quantifies the scale-up stall.** Plot `ServerlessDatabaseCapacity` against `ReadLatency`/`WriteLatency` at the start of a Profile-B spike and show the latency bump while the buffer cache re-warms. That is the §2.5.2 cold-buffer problem, measured.
2. **Adds the I/O-Optimized axis.** Compute whether your write-heavy Profile A would be cheaper on I/O-Optimized by comparing the per-I/O Standard charge against the ~25% compute premium (Lecture 2 §2.5.4).
3. **States the per-tenant SaaS implication.** If each tenant got its own cluster, multiply your idle-profile saving by, say, 200 tenants. That number is why per-tenant micro-clusters on Serverless-v2-with-min=0 is a real architecture — and it is exactly the kind of thing the design exam will probe.

---

When your report names a winner per profile with a dollar margin, fold the result into the mini-project's cost-comparison deliverable.
