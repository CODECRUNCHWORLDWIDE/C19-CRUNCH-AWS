# Lecture 2 — Multi-Region DR: RTO/RPO and the Four Postures, Done Honestly

> **Reading time:** ~95 minutes. **Hands-on time:** ~75 minutes (you stand up Global Tables and an Aurora Global Database and measure replication lag).

Lecture 1 hardened a single Region. This lecture asks the harder question: **what happens when the Region itself goes away?** Not an AZ — Week 5 already made you multi-AZ — but the whole Region, or enough of it that your service is down. The answer is a *disaster-recovery posture*, and the senior skill is picking the right one **honestly**, because every posture is a trade between two numbers (how fast you recover and how much data you lose) and a third (what it costs you every month whether or not disaster ever strikes). By the end of this lecture you will define RTO and RPO precisely, place the four DR postures on the cost-vs-recovery curve, and know which AWS primitive implements each — DynamoDB Global Tables, Aurora Global Database, S3 Cross-Region Replication, multi-Region KMS keys, and Route 53 health-checked failover. Friday you fail over for real and write down the two numbers you *achieved*.

## 2.1 — RTO and RPO are numbers, not adjectives

Two numbers govern every DR decision. Get them precise and the rest is engineering.

- **RTO — Recovery Time Objective.** *How long until service is restored* after a disaster begins. A time budget. "RTO ≤ 5 minutes" means: from the moment the primary Region fails, you have five minutes to be serving traffic from somewhere else. RTO is about *recovery speed* — automation, pre-provisioned capacity, DNS TTLs.

- **RPO — Recovery Point Objective.** *How much data you can afford to lose*, measured in time. A data-loss budget. "RPO ≤ 1 second" means: when you recover, you may have lost at most the last one second of writes. RPO is about *replication lag* — how far behind your second Region's copy of the data was when the primary died.

A picture pins them down:

```
   writes happening normally           DISASTER            service restored
   ───────────────────────────────────────┼──────────────────────┼──────────────►  time
                                           │                      │
                          ◄─── RPO ───►    │   ◄────── RTO ──────► │
                     (data written in       (downtime: how long
                      this window is lost)    until you're back up)
```

RPO looks *backward* from the disaster (what did I lose?). RTO looks *forward* from the disaster (when am I back?). They are independent: you can have a tiny RPO and a huge RTO (your data is perfectly replicated, but you take an hour to spin up the standby) or vice versa. A DR plan states *both* as numbers and then proves them. "We're highly available" is not a DR plan; "RTO ≤ 5 min, RPO ≤ 1 s, last drilled 2026-06-12" is.

The brutal truth this lecture exists to teach: **lower RTO and RPO cost more money, every single month, forever — not just during the disaster that may never come.** That is the honesty in "pick your posture honestly." You are buying insurance, and the premium is real.

## 2.2 — The four postures on the cost-vs-recovery curve

AWS's canonical DR framing is four postures, ordered from cheapest/slowest to priciest/fastest. Learn them cold; a reviewer expects this exact vocabulary.

```
   recovery speed (lower RTO/RPO) ───────────────────────────────►
   cost ───────────────────────────────────────────────────────►

   Backup & Restore    Pilot Light      Warm Standby      Active/Active
   ───────────────    ────────────     ─────────────     ──────────────
   RTO: hours          RTO: 10s of min  RTO: minutes      RTO: ~0
   RPO: hours          RPO: minutes     RPO: seconds      RPO: ~0
   $: lowest           $: low           $: high           $: highest
```

### Backup & Restore — RTO hours, RPO hours, cheapest

Take backups (snapshots, S3 copies, AWS Backup plans) and store them — ideally cross-Region. On disaster, you *restore* from the latest backup into a recovered Region: launch infrastructure from IaC, restore the database from snapshot, repoint DNS. Nothing runs in the second Region until you need it, so the steady-state cost is just *storage of the backups* — pennies. The price is time: restoring a multi-terabyte database from a snapshot and standing up infra is an **hours-long** RTO, and your RPO is however old the last backup was (hours, if you back up nightly).

**Pick it when:** the workload can tolerate hours of downtime and hours of data loss — internal tools, batch systems, anything where "we're down till tomorrow morning" is survivable. Most things are *not* this, but plenty are, and paying for more is waste.

### Pilot Light — RTO tens of minutes, RPO minutes, low cost

Keep the **core data** continuously replicated and running in the second Region (the database replica is live, the "pilot light" is lit), but keep the *compute* off or minimal. On disaster you "turn up the lights": scale the compute from zero, point DNS at it. Because the data is already there and current, you skip the slow restore — RTO drops to **tens of minutes** (the time to scale compute) and RPO drops to **minutes** (replication lag, not backup age). Steady-state cost is the replicated storage + a tiny always-on data tier, not the full compute fleet.

**Pick it when:** you need faster-than-restore recovery but can tolerate the minutes it takes to scale compute, and you want to avoid paying for a full warm fleet.

### Warm Standby — RTO minutes, RPO seconds, high cost

Run a **scaled-down but fully functional copy** of the entire stack in the second Region — compute *running* (just smaller), data replicating continuously. On disaster you *scale up* the warm fleet to full capacity and shift traffic. Because everything is already running, RTO is **minutes** and RPO is **seconds** (sub-second replication). The cost is real: you are paying for a second, running (if smaller) copy of your compute 24/7. **Warm standby roughly adds your second Region's running cost to the bill, forever.**

**Pick it when:** minutes of downtime is the most you can accept and the workload is revenue-bearing enough to justify paying for a standing second fleet.

### Active/Active (Multi-Site) — RTO ~0, RPO ~0, highest cost

Both Regions serve **live production traffic** simultaneously. Failover is not "spin up the other side" — the other side is already serving; failover is just *shifting weight away from the dead Region* (Route 53 stops sending it traffic). RTO and RPO approach zero. The cost is two full production stacks plus the hardest part: **data consistency across two writers.** This is where the multi-region data primitives (Global Tables' last-writer-wins, Aurora Global's write-forwarding) and all of C22's distributed-systems content live. Active/active is the most expensive sentence in this course — two full stacks, plus the engineering to keep two writers consistent.

**Pick it when:** near-zero RTO/RPO is a hard requirement (payments, trading, anything where seconds of downtime is unacceptable) and the business funds two full production footprints.

### The honest decision

The decision is not "which is best" — active/active is always "best" on RTO/RPO and always worst on cost. The decision is: **what RTO and RPO does this workload actually require, and what is the cheapest posture that meets them?** A reviewer who hears "we went active/active" for an internal reporting tool will (correctly) call it waste. A reviewer who hears "we chose pilot light because the workload tolerates 20 minutes of recovery and we saved the cost of a warm fleet" hears an engineer who did the math. Thursday's exercise makes you attach a real monthly dollar figure to each posture for *your* capstone, so the choice is grounded.

## 2.3 — The multi-region primitives

A posture is implemented with primitives. Here are the four that matter, and what each gives you.

### DynamoDB Global Tables — multi-active, RPO ~ sub-second

A **Global Table** is a DynamoDB table replicated across Regions where **every replica is writable** (multi-active). Write in `us-east-1`, the item appears in `us-west-2` within typically a second. Conflicts (the same item key written in two Regions within the replication window) resolve **last-writer-wins** by a reconciliation timestamp — the most recent write wins, the other is discarded. This is *not* strong consistency across Regions; it is eventual consistency with a defined conflict rule, and your data model must tolerate that (idempotent writes, no read-modify-write races across Regions). For the capstone's transactional state, Global Tables give you a near-zero RPO with no failover step at all on the data tier — the second Region already has the data and can already take writes.

```typescript
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

new dynamodb.TableV2(this, 'AppTable', {
  partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
  billing: dynamodb.Billing.onDemand(),
  // The primary Region is the stack's Region; add replicas for the DR Region(s).
  replicas: [{ region: 'us-west-2' }],
  // A multi-Region KMS key per Region so each replica is encrypted with a local key.
  encryption: dynamodb.TableEncryptionV2.customerManagedKey(primaryKey, {
    'us-west-2': replicaKeyArn,
  }),
});
```

Note `TableV2` (the v2019.11.21 Global Tables model — use this, not the legacy v1). The `replicas` array is the entire multi-Region story for DynamoDB: declare the Region, and AWS handles the streaming replication and conflict resolution.

#### Last-writer-wins, in detail — what actually happens at a conflict

"Last-writer-wins" sounds simple until you ask *which clock decides who is last*. It is **not** your application's timestamp and it is **not** strict wall-clock ordering. Each replica stamps every write with a hidden, DynamoDB-managed reconciliation timestamp, and replication carries that timestamp alongside the item. When two writes to the *same item key* originate in different Regions inside the replication window (before either has propagated to the other), every replica independently applies the rule "**keep the write with the highest reconciliation timestamp; discard the other.**" Because the rule is deterministic and every replica sees both writes, all replicas *converge* on the same winner — that is the eventual consistency guarantee. The loser is not merged and not queued; it is silently dropped. There is no conflict exception, no error, no DLQ. The write that lost simply never happened, as far as the surviving data is concerned.

Walk a concrete race. Item `pk=ORDER#42` holds `{ status: "PENDING" }`. At nearly the same instant:

```text
   us-east-1 write:  status = "SHIPPED"   (reconciliation ts = T+10ms)
   us-west-2 write:  status = "CANCELLED" (reconciliation ts = T+ 4ms)
```

Both Regions accept their local write immediately (that is the multi-active promise — neither blocks on the other). Replication streams cross. Each Region now sees both candidate values and applies last-writer-wins by reconciliation timestamp: `T+10ms > T+4ms`, so **`SHIPPED` wins everywhere.** The `CANCELLED` write is gone — in *both* Regions, including the one that issued it. A user in us-west-2 who got a 200 OK for their cancellation will, a second later, see a shipped order. No error was ever raised.

That is the trap. The danger is not that conflicts resolve "wrong" — they resolve *deterministically and consistently*. The danger is that **a client received success for a write that the system later discarded.** Your data model has to make that survivable.

#### Designing so last-writer-wins cannot hurt you

The defensive patterns, in rough order of how often you reach for them:

- **Make writes commutative or idempotent.** If the operation is "set field X to value V" and V is derived from immutable inputs (an event ID, a content hash), replaying or losing one copy changes nothing — both Regions were writing the same V anyway.
- **Never do cross-Region read-modify-write on the same key.** `UpdateItem ... SET balance = balance - 10` issued in two Regions is the classic corruption: each reads the old balance, each subtracts 10, last-writer-wins keeps *one* decrement and the other vanishes — you lost $10 of debit. The fix is to **pin a key to a single Region's writers** (route all writes for a given customer/tenant to one Region; see write-forwarding below) or to model the operation as an append of immutable events rather than a mutation of a shared counter.
- **Use atomic counters only intra-Region.** DynamoDB's `ADD` atomic counter is atomic *within a Region*; across Regions it is still last-writer-wins on the resulting item value, so two Regions incrementing concurrently can lose increments.
- **Conditional writes do not cross Regions.** A `ConditionExpression` (`attribute_not_exists(pk)`, optimistic-lock version checks) is evaluated against the *local* replica only. Two Regions can both pass `attribute_not_exists(pk)` for the same new key because neither has seen the other's insert yet — and then last-writer-wins picks one. Conditional writes give you correctness *within* a Region, not a distributed lock *across* Regions.

The senior summary: **DynamoDB Global Tables give you a sub-second RPO and zero data-tier failover work, in exchange for surrendering cross-Region write ordering.** You buy that trade by designing keys that are either single-Region-owned or conflict-immune. If your write pattern genuinely needs a global serialization point on a shared key, Global Tables is the wrong primitive and you want a single-writer design (one Region owns writes, others forward to it).

### Aurora Global Database — sub-second replication, < 1 min managed failover

An **Aurora Global Database** has a primary Region with a writer and read replicas, plus up to five **secondary Regions** that are read-only and replicated at the *storage* layer — Aurora ships redo-log records, not SQL, so replication lag is typically **under one second** even across continents and the secondary adds almost no load on the primary. On disaster you perform a **managed failover** (planned, with no data loss, RTO seconds-to-a-minute) or an **unplanned failover** (promote a secondary when the primary Region is gone — fast, but you may lose the sub-second tail of unreplicated writes, which is your RPO). The secondary Region's instances are running (you pay for them — this is the warm-standby cost on the data tier), so promotion is fast.

#### A worked Aurora Global Database stack

A Global Database is three CloudFormation resources wired in a specific order: a `CfnGlobalCluster` (the logical global object), a **primary** `DatabaseCluster` that *joins* it, and a **secondary** `DatabaseCluster` in another Region that also joins it as a read-only member. The dependency order matters — the global cluster must exist before the primary attaches, and the primary must be available before the secondary can replicate from it. Because a secondary cluster lives in a *different Region*, it is a different CDK stack with a different `env.region`; the two stacks share the global-cluster identifier as the join key.

```typescript
import * as cdk from 'aws-cdk-lib';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

const ENGINE = rds.DatabaseClusterEngine.auroraPostgres({
  version: rds.AuroraPostgresEngineVersion.VER_16_4,   // Aurora PostgreSQL 16.x, GA in 2026
});

// ---- Stack A: primary Region (us-east-1) ----
export class AuroraGlobalPrimaryStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps & { vpc: ec2.IVpc; keyArn: string }) {
    super(scope, id, props);

    // 1) The logical global cluster. Create it first; the primary joins it.
    const global = new rds.CfnGlobalCluster(this, 'Global', {
      globalClusterIdentifier: 'capstone-global',
      engine: 'aurora-postgresql',
      engineVersion: '16.4',
      storageEncrypted: true,                 // required: a global cluster is always encrypted
      deletionProtection: true,
    });

    // 2) The primary cluster — the only writer. It joins the global cluster.
    const primary = new rds.DatabaseCluster(this, 'Primary', {
      engine: ENGINE,
      vpc: props.vpc,
      writer: rds.ClusterInstance.provisioned('Writer', {
        instanceType: ec2.InstanceType.of(ec2.InstanceClass.R6G, ec2.InstanceSize.XLARGE),
      }),
      readers: [
        rds.ClusterInstance.provisioned('ReaderA', { promotionTier: 1 }),  // intra-Region HA
      ],
      // Encrypt with a Region-local CMK. The secondary Region needs its OWN key (see 2.6).
      storageEncryptionKey: kms.Key.fromKeyArn(this, 'PrimaryKey', props.keyArn),
      backup: { retention: cdk.Duration.days(14) },
      cloudwatchLogsExports: ['postgresql'],
    });

    // 3) Attach the primary to the global cluster (the L1 join).
    const cfnPrimary = primary.node.defaultChild as rds.CfnDBCluster;
    cfnPrimary.globalClusterIdentifier = global.ref;
  }
}

// ---- Stack B: secondary Region (us-west-2), deployed AFTER the primary is available ----
export class AuroraGlobalSecondaryStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps & { vpc: ec2.IVpc; replicaKeyArn: string }) {
    super(scope, id, props);   // props.env.region === 'us-west-2'

    // The secondary cluster references the SAME globalClusterIdentifier and has NO writer of
    // its own — it is a read-only replica fed by storage-layer replication. On failover it is
    // promoted to writer. Note: it is encrypted with the us-west-2 REPLICA key, not the primary's.
    const secondary = new rds.CfnDBCluster(this, 'Secondary', {
      engine: 'aurora-postgresql',
      engineVersion: '16.4',
      globalClusterIdentifier: 'capstone-global',
      storageEncrypted: true,
      kmsKeyId: props.replicaKeyArn,          // us-west-2 multi-Region replica key
      dbSubnetGroupName: subnetGroup.ref,
      dbClusterParameterGroupName: paramGroup.ref,
    });

    new rds.CfnDBInstance(this, 'SecondaryReader', {
      dbClusterIdentifier: secondary.ref,
      dbInstanceClass: 'db.r6g.xlarge',
      engine: 'aurora-postgresql',
    });
  }
}
```

Two things people get wrong here. First, **the secondary is encrypted with a different KMS key than the primary** — KMS keys are Region-local, so a Global Database in two Regions uses two keys, and the clean way to make those keys *related* (same logical identity, for audit and for matching CRR's model) is multi-Region keys, covered in 2.6. Second, **deploy order is not optional**: `cdk deploy` the primary stack, wait for the global cluster and primary to reach `available`, *then* deploy the secondary. A pipeline that deploys both in parallel will fail because the secondary cannot join a global cluster whose primary is not yet ready.

The key DR fact: Aurora Global gives you **seconds RPO and a minute-ish RTO on the relational tier** — the warm-standby posture, in a managed box. The trade is that the secondary's instances cost money 24/7.

#### Managed planned failover vs unplanned failover — and the RPO each gives you

There are two ways to flip an Aurora Global Database, and they hand you *very different* RPO numbers.

- **Managed (planned) failover** — `failover-global-cluster`. AWS coordinates the switch: it stops new writes on the primary, waits for the secondary to catch up to *zero lag*, then promotes the secondary and demotes the old primary to a new read-only secondary. Because it drains replication before promoting, **planned failover is zero-data-loss (RPO = 0).** Use it for Region maintenance, drills, and graceful evacuations. RTO is typically under a couple of minutes. Crucially, planned failover **requires the primary Region to still be reachable** — you cannot drain a Region that is on fire.

- **Unplanned failover (detach-and-promote)** — `remove-from-global-cluster` on the secondary, which promotes it to a standalone writable cluster immediately. This is what you run when the primary Region is *gone* and you cannot wait for it. Promotion is fast (tens of seconds), but you accept whatever the replication lag was at the moment the primary died as your data loss — that **lag tail is your RPO**, typically sub-second but not zero, and *not* guaranteed if the primary failed mid-burst. After an unplanned failover the old global cluster is broken; you rebuild the global topology (re-add a new secondary) once the dead Region returns.

```bash
# Planned (graceful) — zero RPO, requires primary reachable:
aws rds failover-global-cluster \
  --global-cluster-identifier capstone-global \
  --target-db-cluster-identifier arn:aws:rds:us-west-2:111122223333:cluster:capstone-secondary

# Unplanned (primary Region is gone) — promote the secondary, accept the lag tail as RPO:
aws rds remove-from-global-cluster \
  --global-cluster-identifier capstone-global \
  --db-cluster-identifier arn:aws:rds:us-west-2:111122223333:cluster:capstone-secondary
```

The senior discipline: **drill the planned path so the muscle memory is there, but the real-disaster path is the unplanned one, and its RPO is the replication lag you must monitor continuously.** That lag is the `AuroraGlobalDBReplicationLag` CloudWatch metric (in milliseconds). If it is normally 800 ms, your honest Aurora RPO claim is "≤ ~1 s in steady state, worse during a write burst," not "zero." Alarm on it; a lag spike is a silent RPO regression.

#### Active-active on the relational tier: write-forwarding

Aurora Global secondaries are *read-only* by default — they cannot take writes, so the relational tier is warm-standby, not active-active. **Write-forwarding** changes that posture without giving up single-writer correctness. When you enable it, you can point application writes at the *secondary* Region's endpoint, and the secondary **transparently forwards those writes to the primary**, then waits for them to replicate back before returning (consistency-mode dependent). The application gets "I can write in either Region," but there is still exactly **one writer** — the primary — so there is no write-conflict problem to design around. You trade latency (a secondary-Region write makes a cross-Region round trip to the primary) for the operational simplicity of a single source of truth.

```sql
-- On the secondary, choose how much consistency the forwarded write guarantees on subsequent reads:
SET aurora_replica_read_consistency = 'GLOBAL';   -- read-your-writes globally (slowest, strongest)
-- 'SESSION'  → read-your-writes within this session   'EVENTUAL' → fastest, may not see your own write yet
```

This is the cleanest illustration of the whole multi-region-data theme. **DynamoDB Global Tables chose multi-writer + last-writer-wins** (fast local writes everywhere, you design around conflicts). **Aurora write-forwarding chose single-writer + forwarding** (no conflicts ever, you pay cross-Region latency on secondary writes). Neither is "more correct" — they sit at opposite ends of the CAP-flavored trade, and a senior engineer picks per workload: forwarding for relational data with real integrity constraints (balances, inventory) where a lost write is unacceptable; Global Tables for high-velocity, conflict-tolerant state (sessions, carts, event logs) where local write latency matters more than cross-key ordering.

### S3 Cross-Region Replication — and why it needs a multi-Region KMS key

**S3 CRR** asynchronously copies objects from a source bucket to a destination bucket in another Region. For the data lake, this means your second Region has the lake's data when the primary is gone. The subtlety — and the reason Lecture 1's multi-Region KMS key matters here — is **encryption**. If the source bucket uses SSE-KMS with a Region-locked CMK, the replicated object lands in the destination Region encrypted with a key that *does not exist there*, and the replica is undecryptable garbage. The fix is a **multi-Region KMS key**: a primary key in the source Region and a replica key (sharing the same key material) in the destination Region, so the ciphertext replicated cross-Region decrypts with the destination's replica key.

```typescript
// Source bucket replicates to a destination bucket in us-west-2, re-encrypting with the
// destination Region's replica of the multi-Region key.
new s3.CfnBucket(this, 'LakeBucket', {
  bucketName: lakeBucketName,
  versioningConfiguration: { status: 'Enabled' },   // CRR requires versioning
  replicationConfiguration: {
    role: replicationRole.roleArn,
    rules: [{
      status: 'Enabled',
      destination: {
        bucket: `arn:aws:s3:::${destLakeBucketName}`,
        encryptionConfiguration: { replicaKmsKeyId: replicaKeyArnInUsWest2 },
      },
      sourceSelectionCriteria: { sseKmsEncryptedObjects: { status: 'Enabled' } },
    }],
  },
});
```

Three things CRR requires that trip people up: **versioning must be on** (both buckets), the **replication role** needs `s3:GetObjectVersionForReplication` on the source and `s3:ReplicateObject`/`kms:Decrypt`/`kms:Encrypt` across both keys, and **`replicaKmsKeyId` must point at the destination Region's key**. Get the multi-Region key wrong and CRR "works" but the replica is unreadable — a failure you only discover during the failover you didn't drill.

#### Replication Time Control (RTC) — turning "eventually" into an SLA, and into an RPO

Plain CRR is *asynchronous with no guarantee*: most objects replicate in seconds, but a large object during a traffic spike can lag minutes, and AWS makes **no promise**. For DR that is a problem, because your S3 RPO is then "unknown" — exactly the adjective this lecture exists to kill. **S3 Replication Time Control (RTC)** fixes that: it replicates **99.99% of new objects within 15 minutes**, backs it with an SLA, and — the part that matters for operating it — emits **CloudWatch metrics** (`ReplicationLatency`, `BytesPendingReplication`, `OperationsPendingReplication`) plus S3 replication-failure events so you can *alarm* when replication falls behind. RTC turns an unbounded, unobservable lag into a bounded, monitored one. The cost is a per-GB RTC fee on top of normal CRR transfer, which is the honest price of putting an SLA on your S3 RPO.

```typescript
rules: [{
  status: 'Enabled',
  priority: 1,
  filter: { prefix: 'lake/' },                 // a priority + filter is required once RTC is on
  deleteMarkerReplication: { status: 'Enabled' },
  destination: {
    bucket: `arn:aws:s3:::${destLakeBucketName}`,
    encryptionConfiguration: { replicaKmsKeyId: replicaKeyArnInUsWest2 },
    replicationTime: { status: 'Enabled', time: { minutes: 15 } },   // the 15-min SLA
    metrics:         { status: 'Enabled', eventThreshold: { minutes: 15 } },  // emit the lag metric
  },
  sourceSelectionCriteria: { sseKmsEncryptedObjects: { status: 'Enabled' } },
}],
```

The honest framing of your S3 DR RPO: **without RTC it is "best-effort, unbounded"; with RTC it is "≤ 15 minutes for 99.99% of objects, with an alarm when it slips."** For a data lake feeding analytics that is usually fine — a lake is rarely on the critical synchronous path — but state the number, and if 15 minutes is too loose for some bucket, that bucket probably should not be on S3 for its hot path at all.

A second subtlety operators forget: **CRR replicates new objects forward from when you enable it; existing objects are not retroactively copied.** To backfill the objects already in the bucket you run **S3 Batch Replication** (an on-demand job that replicates existing objects under the rule). Stand up CRR on a lake that already has a terabyte of history and you have replicated *nothing* until that Batch job runs — another "works in the demo, empty in the disaster" trap.

### Multi-Region KMS keys — the mechanics that make the encrypted replica readable

Lecture 1 introduced multi-Region keys; here is the mechanism, because both S3 CRR and the encrypted Aurora/DynamoDB replicas above depend on it being right. A **multi-Region KMS key** is a *primary* key in one Region plus one or more *replica* keys in other Regions that **share the same key material and the same key ID** (the trailing `mrk-...` identifier is identical across Regions; only the Region in the ARN differs). Because the material is identical, **ciphertext produced under the primary key decrypts under any replica key, with no re-encryption and no cross-Region KMS call.** That is the whole point: an object encrypted in us-east-1 and replicated to us-west-2 is decryptable *locally* in us-west-2, even if us-east-1 (and its primary key) is completely unreachable.

```typescript
import * as kms from 'aws-cdk-lib/aws-kms';

// In the PRIMARY Region stack (us-east-1): create the primary multi-Region key.
const primaryKey = new kms.CfnKey(this, 'DataKeyPrimary', {
  multiRegion: true,                       // <-- the flag that makes it replicable
  enableKeyRotation: true,
  keyPolicy: { /* admins/users as in Lecture 1 */ },
});

// In the REPLICA Region stack (us-west-2): replicate the primary into this Region.
const replicaKey = new kms.CfnReplicaKey(this, 'DataKeyReplica', {
  primaryKeyArn: primaryKeyArnFromUsEast1,   // points back at the primary's ARN
  keyPolicy: { /* this Region's policy — replicas have INDEPENDENT policies */ },
});
```

The mechanics you must internalize, because they are the difference between a readable and a useless replica:

- **Replicas are created from the primary, but then live independently.** Once replicated, each replica has its **own key policy, own grants, own alias, own enabled/disabled state.** You can grant the us-west-2 read role on the replica key without touching the primary. Replicating does *not* keep the policies in sync — that is deliberate, so each Region can scope access locally.
- **Key material and rotation stay shared.** Rotate the primary and the new material propagates to every replica automatically (they are, cryptographically, the same key). This is why ciphertext stays mutually decryptable forever.
- **You cannot make an existing single-Region key multi-Region after the fact.** Multi-Region-ness is set at *creation* (`multiRegion: true`). If your lake's CMK was created single-Region (Lecture 1's first key often is), you must create a *new* multi-Region key and re-encrypt — a real migration, not a flag flip. This is the single most common reason a "we have CRR" lake is undecryptable in the DR Region.
- **Deleting the primary does not orphan the replicas.** Replica keys can be promoted; a scheduled primary deletion lets you designate a replica as the new primary. But a *replica* whose primary is deleted while it is disabled can become unusable — manage the lifecycle deliberately, with `RemovalPolicy.RETAIN` as in Lecture 1.

Tie it back: the `replicaKmsKeyId` in the CRR rule above must be the **us-west-2 replica key's ARN**, and the Aurora secondary's `kmsKeyId` must likewise be the replica key in its Region. Same key identity, three consumers (S3 CRR, Aurora secondary, DynamoDB replica), one rule — *encrypt the replica with the destination Region's replica of the multi-Region key, never the source Region's key.*

### Route 53 health-checked failover — the traffic switch

The data primitives put your data in the second Region. **Route 53 failover routing** is what actually *moves traffic* there. You create two records for the same name — a **primary** (pointing at the primary Region's endpoint) and a **secondary** (pointing at the DR Region's endpoint) — each with a **health check**. While the primary's health check is healthy, Route 53 answers DNS with the primary. When the health check fails, Route 53 automatically answers with the **secondary**. That is the failover: DNS flips, clients reconnect to the DR Region.

```typescript
import * as route53 from 'aws-cdk-lib/aws-route53';

const primaryHealth = new route53.CfnHealthCheck(this, 'PrimaryHealth', {
  healthCheckConfig: {
    type: 'HTTPS',
    fullyQualifiedDomainName: 'api-primary.capstone.example.com',
    resourcePath: '/health',
    requestInterval: 30,
    failureThreshold: 3,
  },
});

new route53.CfnRecordSet(this, 'ApiPrimary', {
  hostedZoneId: zone.hostedZoneId,
  name: 'api.capstone.example.com',
  type: 'A',
  setIdentifier: 'primary',
  failover: 'PRIMARY',
  healthCheckId: primaryHealth.attrHealthCheckId,
  aliasTarget: { dnsName: primaryAlbDns, hostedZoneId: primaryAlbZoneId, evaluateTargetHealth: true },
});

new route53.CfnRecordSet(this, 'ApiSecondary', {
  hostedZoneId: zone.hostedZoneId,
  name: 'api.capstone.example.com',
  type: 'A',
  setIdentifier: 'secondary',
  failover: 'SECONDARY',
  aliasTarget: { dnsName: drAlbDns, hostedZoneId: drAlbZoneId, evaluateTargetHealth: true },
});
```

The number that haunts every Route 53 failover is the **DNS TTL**. A record with a 300-second TTL means clients can cache the dead primary's address for up to five minutes after the health check flips — *that cached TTL is a floor on your RTO*. Set the failover record's TTL low (60 seconds or less) so clients re-resolve quickly. This is why the Friday drill measures RTO with a stopwatch: the health-check interval (`requestInterval × failureThreshold` = detection time) plus the TTL (propagation time) is your real recovery floor, and it is almost always longer than people guess.

#### When health-check failover is not enough: Route 53 ARC routing controls

Health-checked failover is *automatic and reactive* — it flips when a probe says the endpoint is unhealthy. That is exactly what you want for a clean Region outage, and exactly what you do **not** want in two common cases: (1) a **gray failure** where the health check still passes (the `/health` endpoint returns 200) but the Region is actually degraded — data is stale, a dependency is down, latency is terrible — and you want to evacuate *despite* a green probe; and (2) a **controlled, human-decided evacuation** where you want to *choose* to fail over (for a deployment, a drill, or a partial outage) rather than wait for a probe to trip. For those you want a **manual, highly-available switch you can throw with confidence**, and that is **Route 53 Application Recovery Controller (ARC) routing controls.**

A routing control is, conceptually, an on/off switch (`On`/`Off`) that gates a DNS record. You flip it through the **ARC cluster data plane** — a five-Region, intentionally boring API designed to keep working *even when the rest of AWS, including the Route 53 control plane, is having a bad day*. That five-Region redundancy is the whole value proposition: the one moment you need to fail over is the moment a Regional control plane might be impaired, so the failover switch itself must not live in a single Region. You query and set routing-control state against any of the five cluster endpoints.

```bash
# Read current state from the ARC cluster data plane (any of the 5 Regional endpoints):
aws route53-recovery-cluster get-routing-control-state \
  --routing-control-arn arn:aws:route53-recovery-control::111122223333:controlpanel/abc/routingcontrol/east \
  --region us-east-1 --endpoint-url https://host-xxxx.us-east-1.amazonaws.com/

# THROW THE SWITCH: turn the primary OFF and the secondary ON, atomically respecting safety rules.
aws route53-recovery-cluster update-routing-control-states \
  --update-routing-control-state-entries \
    '[{"RoutingControlArn":"arn:aws:route53-recovery-control::111122223333:controlpanel/abc/routingcontrol/east","RoutingControlState":"Off"},
      {"RoutingControlArn":"arn:aws:route53-recovery-control::111122223333:controlpanel/abc/routingcontrol/west","RoutingControlState":"On"}]' \
  --endpoint-url https://host-xxxx.us-west-2.amazonaws.com/
```

The piece that makes ARC trustworthy is **safety rules**. You define assertions the data plane *enforces* on every state change — most importantly an **assertion rule** that says "at least one Region's routing control must be `On` at all times." That makes it impossible to fat-finger yourself into a total outage by turning everything off; the API rejects the change. You can also add a **gating rule** ("you may only turn West on if West's readiness check is green"). ARC's other half, **readiness checks**, continuously audits that the standby Region is *actually capable* of taking traffic — that its capacity, quotas, and resource configuration match the primary — so when you throw the switch you are not failing over into a Region that will immediately fall over. ARC is the answer to the failure mode in 2.6 below: the DR Region that was never really ready.

The decision: **use health-checked failover for the automatic, unambiguous case; add ARC routing controls when you need a human-throwable, data-plane-resilient switch and continuous readiness assurance.** ARC is not free (the cluster carries a meaningful hourly cost) so it is a "this workload's RTO and the cost of a gray-failure mistake justify it" decision — the same honest-posture math as everything else this week.

## 2.4 — Putting a posture together: the capstone's choice

The capstone spec requires DynamoDB Global Tables, an Aurora cross-Region read replica (Global Database), S3 CRR on the lake, Route 53 health-checked failover, **and documented, proven RTO/RPO targets.** Map that to a posture:

- **Data tier** is effectively **active-active** (Global Tables are multi-writable) and **warm standby** on Aurora (the secondary runs but is read-only until promoted). RPO is sub-second on both.
- **Compute tier** is **pilot light to warm standby** depending on how much you keep running in the DR Region. Keeping the DR EKS/Lambda warm costs money; keeping it cold saves money but adds minutes to RTO.

So the capstone's honest posture statement reads something like: *"Warm standby. Data replicates continuously (DynamoDB Global Tables, Aurora Global, S3 CRR) for a sub-second RPO. Compute in the DR Region runs scaled-down and scales up on failover, plus Route 53 health-checked DNS failover, for a target RTO of 5 minutes — bounded below by the 30s×3 health-check detection plus the 60s DNS TTL. Measured RTO in the drill: 4m12s. Measured RPO: 0s for DynamoDB, ~1.1s for Aurora."* That paragraph — posture named, numbers targeted, numbers *measured* — is the deliverable. Anything vaguer is a hope.

## 2.5 — A concrete failover runbook, with the RTO/RPO math

A posture and a pile of primitives are not a plan until there is a **runbook** — an ordered, copy-pasteable sequence a tired on-call engineer can execute at 3 a.m. without thinking. This is the artifact Friday's drill produces. Here is the capstone's `us-east-1 → us-west-2` runbook, written the way a real one reads: numbered steps, the exact command, and the expected observation after each.

```text
RUNBOOK: Evacuate us-east-1 → us-west-2   (unplanned: primary Region impaired)
Owner: on-call SRE   Pre-reqs: ARC cluster reachable, DR readiness check GREEN, KMS replica keys enabled

T+0:00  DECIDE. Confirm primary is actually down (not a monitoring blip):
        - Synthetic canary for api.capstone.example.com failing from 2+ external regions, AND
        - us-east-1 ALB target health all-unhealthy OR Region status impaired.
        If gray failure (probe green, Region bad): proceed anyway via ARC (below).

T+0:30  PROMOTE AURORA (unplanned — primary unreachable). Accept the lag tail as RPO:
        aws rds remove-from-global-cluster \
          --global-cluster-identifier capstone-global \
          --db-cluster-identifier arn:aws:rds:us-west-2:111122223333:cluster:capstone-secondary
        Expect: secondary becomes a standalone writer in ~30–60s. Record last
        AuroraGlobalDBReplicationLag value BEFORE promotion → that is the Aurora RPO.

T+1:00  SCALE DR COMPUTE to full (pilot-light/warm → full capacity):
        Set the DR EKS nodegroup / ASG desired count to production size; or for Lambda,
        nothing to do (concurrency is on-demand). Expect: pods Ready in ~2–3 min.

T+1:30  FLIP TRAFFIC via ARC routing controls (resilient data plane, not the R53 control plane):
        aws route53-recovery-cluster update-routing-control-states \
          --update-routing-control-state-entries \
            '[{"RoutingControlArn":"arn:aws:route53-recovery-control::111122223333:controlpanel/abc/routingcontrol/east","RoutingControlState":"Off"},
              {"RoutingControlArn":"arn:aws:route53-recovery-control::111122223333:controlpanel/abc/routingcontrol/west","RoutingControlState":"On"}]' \
          --endpoint-url https://host-xxxx.us-west-2.amazonaws.com/
        (If using plain health-check failover instead, the flip already started automatically
         when the health check tripped at detection time; ARC just makes it deterministic.)

T+1:35  WAIT FOR DNS PROPAGATION. Clients holding a cached answer keep hitting the dead
        primary until their TTL (60s) expires. This wait is unavoidable and is in the RTO.

T+~3:00 VERIFY. Synthetic canary green from us-west-2; write a probe row to Aurora and to the
        DynamoDB table; confirm S3 reads from the DR bucket decrypt (proves the replica KMS key).
        DECLARE recovered. Record wall-clock T+0:00 → green = achieved RTO.

POST    Re-establish DR posture for the NEW primary (us-west-2): rebuild the Aurora global
        cluster with a fresh secondary once us-east-1 returns; confirm CRR direction; reset
        ARC so at least one control stays On (the safety assertion rule enforces this).
```

Now the math, because "RTO ≈ 5 minutes" must come from somewhere. Two cases:

**Automatic (health-check) failover RTO** is a sum of independent stages, and the discipline is to write each one down:

```text
RTO  =  detection           +  DNS propagation        +  DR warm-up
     =  (interval × threshold)  +  (record TTL)           +  (compute scale-up + drain)
     =  (30s × 3 = 90s)         +  (60s)                  +  (~120s)
     =  90 + 60 + 120  =  270s  =  4m30s   (target ≤ 5m → meets it, with little margin)
```

Every term is a knob. Tighten detection by lowering the interval or threshold (at the cost of more false-positive flips). Tighten propagation by lowering the TTL (60s is a sane floor; going lower raises resolver load for marginal gain). Tighten warm-up by keeping more compute running in the DR Region — which is precisely the pilot-light → warm-standby cost dial. **You cannot get RTO below the slowest term**, and for most teams that term is either the TTL they forgot to lower or the cold compute they didn't pre-provision.

**Manual (ARC) failover RTO** removes the detection term (a human decided) but *adds* human reaction time, which is honest to include: decide (variable, the big unknown) + promote DB (~60s) + flip control (~5s) + DNS TTL (60s) + verify (~90s). The drill exists to shrink the "decide" term by rehearsing the decision criteria until they are reflexive.

**The RPO math** is per-data-store and is *not* a single number — state each:

```text
DynamoDB Global Tables : RPO ≈ 0   (multi-active; writes already in us-west-2; loser writes are
                                     last-writer-wins drops, not failover loss — design for it)
Aurora Global (unplanned): RPO = the replication-lag tail at the instant of failure
                                     = last AuroraGlobalDBReplicationLag before promotion (~0.8–1.5s)
Aurora Global (planned)  : RPO = 0  (managed failover drains lag to zero first)
S3 lake (CRR + RTC)      : RPO ≤ 15 min for 99.99% of objects (the RTC SLA); alarm on the lag metric
```

The deliverable footer the whole week points at falls straight out of this runbook + math:

```text
Failover drill: us-east-1 → us-west-2  (unplanned, ARC-driven)
  RTO (service restored):     achieved 4m12s   (target ≤ 5m)   ✓
  RPO DynamoDB:               achieved 0s      (target ≤ 1s)   ✓
  RPO Aurora (unplanned):     achieved ~1.1s   (target ≤ 1s)   ✗  — lag tail; would be 0 on planned
  RPO S3 lake:                achieved <15m    (target ≤ 15m)  ✓  [RTC SLA, no objects pending]
  Last drilled: 2026-06-12    Runbook: this section
```

That footer — posture named, every store's number measured against its target, the one miss explained — *is* the plan. Notice the Aurora miss is not a failure of the runbook; it is the honest cost of an unplanned failover, and the right response is to document it ("we accept ≤ ~1.5s loss on unplanned Region loss; planned evacuations are zero-loss"), not to pretend it is zero.

## 2.6 — Why "we have a DR Region" usually fails

The most common DR failure is not a missing Region — it is an **untested** one. Teams stand up a second Region, replicate the data, and never fail over. Then the real disaster comes and they discover:

- The DR Region's IAM roles were never created, because the security baseline was only applied to the primary.
- The replicated S3 data is **undecryptable** because nobody made the KMS key multi-Region (Lecture 1 → this lecture's whole bridge).
- The Route 53 health check was pointing at a path that always returns 200 even when the app is broken, so it never flipped.
- The DNS TTL was 3600 seconds, so even after the flip, clients took an hour to notice.
- Nobody knew the *runbook* — which button to press, in which order — because the failover was never rehearsed.

Every one of these is invisible until you drill. **The drill is the deliverable, not the architecture.** A DR architecture you have never failed over to is Schrödinger's DR: simultaneously working and broken until you observe it. Friday you observe it. That is why this week ends with a stopwatch and two numbers, not a diagram.

## 2.7 — Open-source / cross-cloud comparators (what you traded away)

- **The managed multi-Region primitives** (Global Tables, Aurora Global) hide enormous distributed-systems complexity — consensus, conflict resolution, replication-lag management. The open/self-hosted equivalents are **Cassandra/ScyllaDB** multi-DC replication (the DynamoDB Global Tables analog, with the same last-writer-wins and tunable consistency you tune yourself) and **Patroni/Postgres logical replication** (the Aurora Global analog, where *you* run the replication and the failover orchestration). You give up "AWS handles failover" and gain control and cross-cloud portability — exactly the trade C22 · Crunch Mesh dissects.
- **Route 53 failover** has equivalents in any global load balancer or **health-checked DNS** provider (Cloudflare, NS1); the *pattern* — health check + DNS failover + low TTL — is universal, and the RTO floor (detection + TTL) is the same everywhere. Learn it here and it transfers.

The recurring lesson, the same as Week 11's fixed-vs-variable: **managed multi-Region services move the hardest distributed-systems problems off your plate and onto AWS's, and you pay for it in dollars and in the consistency constraints (last-writer-wins, sub-second-but-not-zero lag) you must design around.** Knowing those constraints — and proving your RTO/RPO against them — is the skill the capstone certifies.

## 2.8 — What you should be able to do now

- Define RTO and RPO precisely and draw them on the disaster timeline.
- Place the four postures (backup/restore, pilot light, warm standby, active/active) on the cost-vs-recovery curve with rough RTO/RPO ranges.
- Pick the cheapest posture that meets a stated RTO/RPO budget and attach a monthly cost to it.
- Stand up DynamoDB Global Tables and explain last-writer-wins conflict resolution down to the reconciliation timestamp, and design keys (single-Region-owned or conflict-immune) so a dropped write cannot corrupt you.
- Stand up an Aurora Global Database from the primary + secondary + `CfnGlobalCluster` wiring, and distinguish planned (RPO 0) from unplanned (RPO = lag tail) failover.
- Explain Aurora write-forwarding as the single-writer alternative to Global Tables' multi-writer, and say when to pick each.
- Configure S3 CRR with Replication Time Control for a 15-minute SLA, a multi-Region KMS key so the replica is decryptable, and Batch Replication to backfill existing objects.
- Explain multi-Region KMS key mechanics (shared material, independent policies, set-at-creation) and wire the replica key into CRR and the Aurora secondary.
- Wire Route 53 health-checked failover, identify the detection-plus-TTL RTO floor, and add ARC routing controls with safety rules for human-driven, gray-failure evacuations.
- Run a manual Region failover from a written runbook, do the per-stage RTO math and per-store RPO math, and report the numbers you *achieved* vs targeted with each miss explained.

## 2.9 — The challenge that goes with this lecture

**Challenge 1 — Route 53 failover drill.** Wire the health-checked failover records over a primary and DR endpoint, replicate the data with the primitives above, then *fail the primary* and measure the actual RTO (time for DNS to flip and the DR Region to serve) and RPO (data lost at the cut). Write the achieved-vs-target numbers and the runbook. The acceptance criteria are in `challenges/challenge-01-route53-failover-drill.md`. Bring a stopwatch and real numbers.
