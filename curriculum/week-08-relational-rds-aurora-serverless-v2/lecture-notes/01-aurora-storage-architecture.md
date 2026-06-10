# Lecture 1 — Aurora Is a Postgres Shell Over a Distributed Storage Engine

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you provision a cluster and inspect its endpoints while you read).

This is the lecture that earns you the right to make claims about Aurora. Everything else this week — the proxy, the IAM auth, the failover drill, the ACU cost math — sits on top of one fact that most engineers who "use Aurora" have never internalized: **Aurora is not managed PostgreSQL. It is a PostgreSQL query engine that has had its storage layer ripped out and replaced with a purpose-built, log-structured, multi-tenant distributed storage service.** Once you see the system that way, the behavior stops being surprising. Failover in 10–30 seconds instead of 60–120 stops being magic. Fifteen read replicas that share one copy of the data stop being expensive. A volume that "just grows" to 128 TiB without a `resize` stops being a feature you have to plan. And the subtle ways your migrations behave differently from RDS stop being bugs and start being consequences. By the end of this lecture you can draw the storage fleet on a whiteboard, state the quorum math from memory, and explain why each of those behaviors falls out of the architecture rather than being bolted on.

## 1.1 — Start with the thing Aurora replaces

To understand what Aurora *is*, start with what community PostgreSQL *does*, because Aurora keeps the top half and throws away the bottom half.

A community PostgreSQL instance is a process tree talking to a local filesystem. When you `COMMIT`, here is the sequence, simplified but honest:

1. The backend process modifies pages in **shared buffers** (an in-memory page cache, default 25% of RAM).
2. It writes **WAL records** — the write-ahead log, a physical/logical description of the change — to the WAL buffer, then flushes the WAL to disk via `fsync`. The transaction is durable once the WAL is on stable storage. This is the commit point.
3. Later, asynchronously, a **checkpoint** flushes the dirty 8 KiB data pages from shared buffers back to the heap files on disk. The data files lag the WAL; that is fine, because on crash recovery PostgreSQL replays the WAL forward from the last checkpoint to reconstruct the pages.

Replication in community Postgres ships that same WAL stream to a standby, which **replays** it against its own copy of the data files. The standby has a full, independent copy of every page. That is why a read replica costs you a full second copy of storage, and why promoting a standby after a primary failure means waiting for the standby to finish replaying any WAL it had not yet applied — the replication lag is your data-loss window (RPO) and the replay-catch-up plus DNS change is your recovery window (RTO).

Hold that picture. **Aurora keeps steps 1 and 2's *intent* but deletes the local disk, the checkpoint-to-heap-files dance, and the replay-based replica entirely.**

## 1.2 — The one sentence that defines Aurora: "the log is the database"

Aurora's compute node runs a forked PostgreSQL engine. It still has shared buffers. It still generates redo log records (Aurora's term for the WAL records) on every change. But it **does not write data pages to a local disk, and it does not ship the log to replicas for replay.** Instead:

> The Aurora writer ships **only the redo log records** across the network to a fleet of **six storage nodes**, spread across **three Availability Zones** (two nodes per AZ). The storage nodes are responsible for taking those log records and materializing the actual 8 KiB data pages — on demand, lazily, in the background.

Read that twice. The compute node's job shrinks to: run SQL, manage the buffer cache, generate redo. The expensive, write-amplifying parts — writing full pages, checkpointing, full-page writes to defend against torn pages, double-writing — are gone from the compute node. The classic SIGMOD-2017 number is that this cuts the network write traffic by roughly **7.7×** versus a mirrored-Postgres-on-EBS setup that has to write the page, the WAL, the page again on the mirror, and so on. Aurora writes the log, and only the log.

The storage node, on receiving log records for a page, appends them to a per-page log chain. When someone asks to *read* that page (the compute node had a buffer-cache miss, or a reader instance needs it), the storage node coalesces the outstanding log records into the materialized page and returns it. Materialization is the storage fleet's problem, not the compute node's, and it happens in parallel across the fleet.

## 1.3 — The quorum math you must know cold

Six copies across three AZs. Aurora uses a **quorum** protocol, not primary/replica mirroring, at the storage layer. The numbers you memorize:

- **Write quorum: 4 of 6.** A write (a batch of log records) is durable — and the compute node is told the commit succeeded — once **four** of the six storage nodes acknowledge it. Not all six. Four.
- **Read quorum: 3 of 6.** When the storage layer needs a consistent read of a page from quorum (e.g., during recovery), it reads from **three** nodes and uses versioning to pick the latest.
- `Vw + Vr > V` and `Vw > V/2`: with V = 6, Vw = 4, Vr = 3. `4 + 3 = 7 > 6` (read sees latest write) and `4 > 3` (no split-brain writes). The math is deliberately chosen.

Why those numbers? Because of what they let Aurora *survive* without losing availability:

- **Losing an entire AZ (2 of 6 nodes) and still writing.** Down two nodes, you have four left. Four is the write quorum. You can still commit. This is the headline: Aurora tolerates an AZ failure for **writes** with no data loss and no write outage at the storage layer.
- **Losing an entire AZ *plus* one more node (3 of 6) and still reading.** Down three, you have three left, which is the read quorum. So Aurora tolerates **AZ + 1** for reads. You can serve reads (and repair) even after an AZ failure plus a single additional node failure.

That "AZ + 1" property is the whole reason the storage is six-way and three-AZ rather than three-way one-AZ. A correlated AZ-wide failure is the realistic disaster; the +1 covers the unlucky simultaneous disk failure during the AZ outage. Repair is fast because the volume is sliced into **10 GiB segments** ("protection groups"), each with its own six-copy quorum. When a node dies, Aurora only has to re-replicate the 10 GiB segments that lived on it, copying from the surviving quorum members in parallel — not the whole 64-or-128-TiB volume. Mean-time-to-repair for a segment is seconds to low minutes, which keeps the probability of a *second* failure inside the repair window vanishingly small. That is the durability argument: it is not "six copies is more than three," it is "six copies sliced into 10 GiB segments repairs so fast that the window for a quorum-breaking double failure essentially closes."

## 1.4 — Why failover is fast: readers share the writer's storage

Here is the payoff for read replicas, and it is the single biggest practical difference from RDS.

In RDS (community Postgres), a read replica has **its own copy** of the data. The primary ships WAL; the replica replays it into its own files. Promotion = finish replaying + flip DNS, and the replica's buffer cache is its own.

In Aurora, **the writer and all readers point at the same shared storage volume.** A reader does not replay a log to maintain its own copy — there is only one copy (well, six segments, but one logical volume). The writer ships its redo log records to the storage fleet *and* streams them to the reader instances so the readers can invalidate/update the pages sitting in *their* buffer caches. The reader's data is never stale relative to durable storage because it does not *have* its own durable storage — it reads from the shared volume.

Consequences:

- **A reader can be promoted to writer in seconds**, because it does not need to catch up on un-replayed WAL against a private copy — the durable state already lives in shared storage. Promotion is mostly: pick the highest-priority healthy reader, point the cluster (writer) endpoint's DNS at it, and let it open the volume for writes. Aurora typically completes failover in **10–30 seconds**, dominated by detection + DNS propagation + the new writer warming up, not by data movement.
- **Adding a reader is cheap on storage** — you pay for the *instance* (compute) but **not** a second copy of the data, because there is no second copy. (You do pay for the I/O the reader drives, and for storage once, cluster-wide.) RDS read replicas each cost a full storage copy. This is why Aurora scales reads to **15** replicas comfortably and RDS does not.
- **Replica lag is measured in *milliseconds*** (the time for the reader to apply log records to its buffer cache, typically single-digit to low-tens of ms), not the seconds-to-minutes of WAL-shipping replication, because there is no file replay — just cache coherence over the same volume.

Contrast this with **RDS Multi-AZ (single-standby)**: a synchronous physical standby in another AZ. Durable (synchronous), but failover is a **DNS change after the standby finishes any pending recovery**, typically **60–120 seconds**. And the standby is *not* readable — it is a pure failover target. The newer **RDS Multi-AZ DB cluster** (one writer + two readable standbys, semi-synchronous) gets failover down to ~35 seconds and gives you readable standbys, but it is still log-replay replication with full storage copies per instance. Aurora's shared storage is a genuinely different mechanism, and the failover-time and replica-cost numbers are the observable fingerprints of that difference.

Put the comparison in a table you can reproduce on a whiteboard in the design exam:

| Property | Community PG / RDS single-AZ | RDS Multi-AZ (1 standby) | RDS Multi-AZ DB cluster | Aurora |
|---|---|---|---|---|
| Storage model | Local/EBS, per instance | EBS, primary + sync standby copy | EBS, 3 copies (1 per instance) | Shared 6-copy/3-AZ quorum volume |
| Read replicas | Async WAL-ship, own copy | Standby not readable | 2 readable standbys | Up to 15, shared storage |
| Replica lag | seconds | n/a (sync) | low (semi-sync) | **milliseconds** |
| Failover time | manual / minutes | **60–120 s** | **~35 s** | **10–30 s** |
| Volume growth | manual `resize` | manual | manual | **automatic to 128 TiB** |
| Cost shape | 1× storage | 2× storage | 3× storage | 1× storage + per-instance compute |

## 1.5 — Why the volume "just grows"

You never provision Aurora storage. There is no "allocate 100 GiB" knob like RDS's `allocatedStorage`. The volume starts at 10 GiB and grows in 10 GiB segment increments automatically as you write, up to **128 TiB** (raised from the old 64 TiB cap). You are billed for what you store, per GiB-month, and (on Standard) for the I/O you drive.

This falls directly out of the segment model: the volume *is* a set of 10 GiB protection groups, each independently six-way replicated. Growing the volume means allocating another protection group somewhere in the fleet and adding it to the volume's segment map. There is no monolithic file to extend, no downtime, no DBA paging you at 2 a.m. because the disk hit 95%. The flip side: **storage does not shrink.** Delete a terabyte of data and the high-water mark stays (until the very recent dynamic-resize behavior reclaims it lazily on some engine versions). Treat reclamation as best-effort, not guaranteed, and design `DELETE`-heavy workloads accordingly — `pg_repack`/`VACUUM FULL` rewrite into new pages but do not reliably shrink the Aurora volume the way they shrink a local data directory.

## 1.6 — What "the log is the database" does to your migrations

This is the part the syllabus promises and the part that bites real teams. The storage architecture changes the *cost profile* of DDL, even though the SQL is identical to community Postgres.

**Fast metadata-only operations.** Aurora PostgreSQL inherits PostgreSQL's catalog-level DDL semantics. `ALTER TABLE ... ADD COLUMN ... DEFAULT <constant>` is metadata-only in modern Postgres (the default is stored in the catalog, not written to every row) — and it is metadata-only on Aurora too, fast and non-blocking. Good. Adding a `CHECK` constraint as `NOT VALID` then `VALIDATE CONSTRAINT` separately keeps the long-running validation off the `ACCESS EXCLUSIVE` lock — same on Aurora. The general rule holds: *the same migration that is safe on community Postgres is safe on Aurora.*

**Where it diverges: anything that rewrites the table touches the storage fleet, not a local disk.** A migration that rewrites every page — `ALTER TABLE ... ALTER COLUMN ... TYPE` with a non-trivial cast, `CLUSTER`, `VACUUM FULL`, or adding a column with a volatile default on an old engine version — generates redo for every changed page and pushes it through the 4-of-6 quorum write path over the network. On a local NVMe disk, rewriting a 200 GiB table is bottlenecked by local IOPS. On Aurora it is bottlenecked by the *quorum write latency and storage I/O cost* — which is generally fine throughput-wise, but on **Aurora Standard you are billed per I/O**, so a giant table rewrite has a *dollar* cost that does not exist on community Postgres. A `VACUUM FULL` of a bloated multi-terabyte table can show up as a visible line on your Aurora bill. (This is one of the inputs to the I/O-Optimized-vs-Standard decision in Lecture 2.)

**`CREATE INDEX CONCURRENTLY` works and you should use it.** It is non-blocking on Aurora exactly as on community Postgres. But it does two heap scans and a sort, all of which drive storage I/O across the fleet — again, billed on Standard. Build indexes during low-traffic windows not just for lock contention reasons but for I/O-cost reasons.

**The migration discipline that follows:** treat every migration as if it must be (a) lock-safe — short `ACCESS EXCLUSIVE` holds only, `NOT VALID` + `VALIDATE`, `CONCURRENTLY` for indexes — *and* (b) I/O-aware — estimate the pages rewritten, and if it is a full-table rewrite of a large table, schedule it, and consider I/O-Optimized for the cluster if rewrites are frequent. Bring Flyway/Liquibase/Alembic from C16; the AWS-specific addition is the I/O line item.

## 1.7 — The endpoints, and why there are three kinds

A provisioned Aurora cluster gives you a small set of DNS endpoints. You must know what each one does, because connecting to the wrong one is the most common Aurora mistake:

- **Cluster endpoint (a.k.a. writer endpoint):** `mycluster.cluster-abc123.us-east-1.rds.amazonaws.com`. Always resolves to the **current writer**. On failover, Aurora re-points this CNAME at the promoted instance. Your application's write connection string uses this and *never changes* across failovers. This is the single most important endpoint.
- **Reader endpoint:** `mycluster.cluster-ro-abc123.us-east-1.rds.amazonaws.com`. Round-robins **connections** (not individual queries) across the healthy reader instances. Open ten connections and they spread across your readers; a single long-lived connection sticks to one reader. This is why a connection pool with a small, long-lived set of connections can pile onto one reader and starve the others — a real production gotcha. RDS Proxy and client-side pooling change this behavior, which is part of why Tuesday's lecture exists.
- **Instance endpoints:** one per instance, e.g. `mycluster-instance-1.abc123...`. You generally do **not** hard-code these — they break the abstraction and pin you to a specific instance that may get replaced. Use them only for targeted diagnostics (e.g., "is *this specific reader* lagging?").
- **Custom endpoints (optional):** you can define your own endpoint that load-balances across a *chosen subset* of instances — e.g., route analytical queries to two big `r7g.4xlarge` readers and OLTP reads to the rest. Useful for the capstone's "analytical Aurora store."

In the design exam, when someone asks "how does your app survive a writer failover," the correct answer starts with "the application's write DSN points at the **cluster endpoint**, which is a CNAME Aurora re-points at the promoted reader, so the app reconnects to the same hostname and sees the new writer." If you say "we update the connection string," you have failed the question.

## 1.8 — Provision one and look at it

Enough theory. Spin up a minimal cluster with the CLI and inspect the architecture you just learned (the CDK version is Exercise 1; here we use the CLI for speed and so you see the raw resource shape). This assumes a VPC with isolated subnets and a DB subnet group already exist from Week 4.

```bash
# Create a DB cluster parameter group so we can enforce TLS later
aws rds create-db-cluster-parameter-group \
  --db-cluster-parameter-group-name aurora-pg16-week8 \
  --db-parameter-group-family aurora-postgresql16 \
  --description "Week 8 demo cluster parameter group"

aws rds modify-db-cluster-parameter-group \
  --db-cluster-parameter-group-name aurora-pg16-week8 \
  --parameters "ParameterName=rds.force_ssl,ParameterValue=1,ApplyMethod=pending-reboot"

# Create the cluster (Aurora PostgreSQL 16.x), KMS-encrypted, backups 7 days
aws rds create-db-cluster \
  --db-cluster-identifier week8-aurora \
  --engine aurora-postgresql \
  --engine-version 16.6 \
  --master-username crunchadmin \
  --manage-master-user-password \
  --db-subnet-group-name week8-db-subnets \
  --vpc-security-group-ids sg-0abc123 \
  --db-cluster-parameter-group-name aurora-pg16-week8 \
  --storage-encrypted \
  --backup-retention-period 7

# Add a writer instance
aws rds create-db-instance \
  --db-instance-identifier week8-aurora-writer \
  --db-cluster-identifier week8-aurora \
  --engine aurora-postgresql \
  --db-instance-class db.r7g.large \
  --enable-performance-insights

# Add two readers
for i in 1 2; do
  aws rds create-db-instance \
    --db-instance-identifier week8-aurora-reader-$i \
    --db-cluster-identifier week8-aurora \
    --engine aurora-postgresql \
    --db-instance-class db.r7g.large \
    --enable-performance-insights
done
```

Now inspect what you built — note how the three endpoint kinds appear:

```bash
aws rds describe-db-clusters \
  --db-cluster-identifier week8-aurora \
  --query 'DBClusters[0].{Writer:Endpoint, Reader:ReaderEndpoint, Members:DBClusterMembers[].{Id:DBInstanceIdentifier,IsWriter:IsClusterWriter}}'
```

Expected output (your identifiers will differ):

```json
{
    "Writer": "week8-aurora.cluster-abc123xyz.us-east-1.rds.amazonaws.com",
    "Reader": "week8-aurora.cluster-ro-abc123xyz.us-east-1.rds.amazonaws.com",
    "Members": [
        { "Id": "week8-aurora-writer",   "IsWriter": true  },
        { "Id": "week8-aurora-reader-1", "IsWriter": false },
        { "Id": "week8-aurora-reader-2", "IsWriter": false }
    ]
}
```

There is the architecture from §1.7 in JSON: one writer, two readers, one cluster (writer) CNAME, one `cluster-ro` reader CNAME. The storage fleet underneath — the six-way, three-AZ, 10 GiB-segment quorum volume — has no API surface. You never see it, you never tune it, and that is the point: AWS operates it, you rent the abstraction.

Confirm TLS is being enforced once the reboot applies:

```bash
# This should FAIL with sslmode=disable once rds.force_ssl=1 is active:
PGSSLMODE=disable psql "host=week8-aurora.cluster-abc123xyz.us-east-1.rds.amazonaws.com \
  dbname=postgres user=crunchadmin" -c 'select 1;'
# FATAL:  no pg_hba.conf entry for host ..., SSL off

# With TLS it connects:
PGSSLMODE=require psql "host=week8-aurora.cluster-abc123xyz.us-east-1.rds.amazonaws.com \
  dbname=postgres user=crunchadmin" -c 'select 1;'
#  ?column?
# ----------
#         1
```

**Tear it down when you are done reading** (you will rebuild it properly via CDK in Exercise 1):

```bash
for id in week8-aurora-writer week8-aurora-reader-1 week8-aurora-reader-2; do
  aws rds delete-db-instance --db-instance-identifier $id --skip-final-snapshot
done
aws rds delete-db-cluster --db-cluster-identifier week8-aurora --skip-final-snapshot
```

## 1.9 — The open-source shadow: what you give up and what you avoid

The senior move is never "Aurora because AWS." It is "Aurora because we need fast failover and read scale-out without operating HA ourselves, we accept the storage premium and the lock-in, and here is the number." So you must know what the open-source alternatives actually cost you to run.

**Community PostgreSQL on EKS with Patroni (or CloudNativePG).** Patroni runs a sidecar next to each Postgres instance, stores cluster state in a DCS (etcd/Consul/Kubernetes leader-lease), and handles automatic failover: it watches the leader's health, holds a leader lock with a TTL, and on leader loss runs an election, promotes the most-caught-up replica, and uses `pg_rewind` to reattach the old leader as a follower without a full re-clone. CloudNativePG is the Kubernetes operator that wraps this pattern so you write a `Cluster` CRD instead of hand-rolling Patroni config.

What you get: full control, full portability, no per-I/O billing, the actual community engine (every extension works, no fork-lag). What you pay: **you operate it.** You own the DCS quorum, the failover testing, the storage (each replica is a full copy on EBS — back to 1× storage per replica, the thing Aurora's shared storage eliminated), the backup tooling (`pgBackRest`/`barman` to S3), the connection pooler (PgBouncer), the monitoring, and the 2 a.m. page when the leader lease flaps under network partition. Failover with Patroni is competitive on time (single-digit seconds with tuned TTLs) but it is *log-replay* failover — the new leader must be caught up, so your RPO is your replication lag, same as RDS, not Aurora's shared-storage-zero.

**Citus** is the orthogonal axis. Aurora scales **reads** (15 replicas) but has exactly **one writer** — you cannot shard writes across nodes. Citus is a Postgres extension that distributes a table across worker nodes by a shard key, giving you horizontal **write** scale-out and parallel query across shards. If your bottleneck is write throughput beyond a single beefy instance, Aurora does not solve it and Citus (or Aurora Limitless, AWS's newer sharding answer) does. Know the distinction cold: **Aurora = read scale-out + fast failover, single writer. Citus = write/horizontal scale-out, you operate it.**

The honest trade-off table for the design exam:

| Need | Aurora | Patroni/CloudNativePG on EKS | Citus |
|---|---|---|---|
| Fast failover (<30s) without ops burden | ✅ best | ⚠️ achievable, you operate it | ⚠️ inherits underlying PG HA |
| Read scale-out | ✅ 15 shared-storage readers | ⚠️ replicas, 1× storage each | ✅ + parallel query |
| Write scale-out (sharding) | ❌ single writer | ❌ single writer | ✅ this is the point |
| No per-I/O billing | ⚠️ I/O-Optimized fixes it (Lec 2) | ✅ | ✅ |
| Portability / no lock-in | ❌ | ✅ | ✅ |
| Operational burden | ✅ lowest | ❌ highest | ❌ high |

## 1.10 — Parameter groups: where you actually tune this thing

You do not tune the storage fleet — AWS operates it. What you *do* tune is the PostgreSQL engine on the compute nodes, and you do it through **parameter groups**. There are two kinds, and confusing them is a classic mistake:

- **DB cluster parameter group** — applies to the *whole cluster*: every instance, writer and readers. Engine-wide settings live here: `rds.force_ssl`, `shared_preload_libraries`, `rds.logical_replication`, character-set defaults. You set `shared_preload_libraries = pg_stat_statements` here because it must be identical on every node.
- **DB instance parameter group** — applies to *one instance*. Per-instance tuning lives here: `max_connections` (which Aurora actually derives from instance memory by default, via a formula), `work_mem`, `effective_cache_size`. A big analytical reader can carry a different instance parameter group than the OLTP readers.

Parameters are either **static** or **dynamic**:

- **Dynamic** parameters apply on change (or on the next connection), no restart. `log_min_duration_statement`, `work_mem`.
- **Static** parameters require a **reboot** of the instance to take effect. `shared_preload_libraries`, `rds.force_ssl` (it is `pending-reboot`). This is why Exercise 1 sets `force_ssl` in the parameter group at *creation* — so the first boot already has it.

The practical workflow: change a static parameter, then `aws rds reboot-db-instance` each instance during a maintenance window (reboot the readers first, then fail over and reboot the old writer, so you never take a write outage you did not schedule). Aurora exposes the same machinery to you whether you use the console, the CLI, CDK's `ParameterGroup` construct, or OpenTofu's `aws_rds_cluster_parameter_group` — the static-vs-dynamic and reboot semantics are identical across all of them.

A note on **option groups**: these are an **RDS** concept (for engine add-ons like Oracle TDE, SQL Server features, MySQL MEMCACHED). Aurora PostgreSQL does **not** use option groups — extensions are managed via `shared_preload_libraries` in the cluster parameter group and `CREATE EXTENSION` in SQL. If an interviewer asks "what option group do you use for Aurora Postgres," the correct answer is "none — option groups are RDS-engine-specific; Aurora Postgres uses parameter groups and `CREATE EXTENSION`."

## 1.11 — Performance Insights: how an on-call engineer reads Aurora

You enabled Performance Insights (PI) on every instance in Exercise 1. PI is the dashboard you open when someone says "the database is slow," and reading it correctly is a skill, not a glance.

The central metric is **DB load**, expressed as **average active sessions (AAS)** — the average number of sessions actively running (on CPU or waiting) at any instant. The reference line on the chart is `max vCPU` (the instance's vCPU count). The reading:

- **AAS below `max vCPU`:** the instance is not CPU-bound; you have headroom.
- **AAS above `max vCPU`:** sessions are queuing — either for CPU or for some wait event. This is your "the database is the bottleneck" signal.

PI slices the load by **wait event**, which tells you *what* the sessions are waiting on:

- `CPU` — genuine compute; you may need a bigger instance or a cheaper query plan.
- `IO:DataFileRead` / `IO:XactSync` — storage waits; on Aurora this is the quorum-write/read path. Heavy here may argue for I/O-Optimized (Lecture 2).
- `Lock:*` / `Lock:transactionid` — lock contention; a migration holding `ACCESS EXCLUSIVE`, or hot-row update contention.
- `LWLock:BufferMapping` / `Client:ClientRead` — buffer-cache or client-side stalls.

And it ranks **Top SQL** by load contribution, so you can go straight from "AAS is 12 on an 8-vCPU box and the top wait is `Lock`" to "this one `UPDATE` is the culprit." PI's free tier keeps **7 days** of this; long-term retention (up to 2 years, 24-month) is paid. For the capstone you keep the free 7 days and rely on `pg_stat_statements` (the open-source comparator, which PI partly reads from) for longer-horizon query analysis. The homework has you compare what PI shows against what `pg_stat_statements` shows for the same window — they overlap but PI adds the wait-event dimension that `pg_stat_statements` alone does not give you.

## 1.12 — Backups, PITR, and the recovery-time hierarchy

The storage architecture quietly makes backups cheap and continuous. Because the log *is* the database, Aurora **continuously streams its redo log to S3** in the background — there is no nightly "backup job" that loads the instance. This gives you two recovery primitives with very different RTOs, and you must rank them:

1. **Failover (RTO ~10–30s, RPO 0).** Not a "backup" — a promotion. For a *node/AZ* failure. The fastest recovery, no data loss, covered by Exercise 3.
2. **Point-in-time recovery (PITR) (RTO minutes–tens-of-minutes, RPO ~seconds).** Restore the cluster to **any second** within the backup retention window (1–35 days). This creates a *new* cluster from the continuous backup; it does not repair the existing one. For "someone ran `DELETE FROM users` without a `WHERE`." You restore to the second before the mistake.
3. **Manual snapshot restore (RTO tens-of-minutes, RPO = snapshot age).** A point-in-time copy you took deliberately, kept until you delete it (snapshots survive cluster deletion — this is the thing that quietly costs money if you forget them). Restoring also creates a new cluster.
4. **Cross-region snapshot copy (RTO = copy time + restore time, RPO = snapshot age).** Copy a snapshot to another region, **re-encrypting** to a destination-region KMS key (you cannot use a key from the source region in the destination). This is the cheapest DR tier — "backup/restore" in the Week-13 DR taxonomy.
5. **Aurora Global Database (RTO ~minutes managed, RPO ~sub-second).** Covered in §1.13. For a whole-*region* failure with a tight RPO.

The senior framing: **failover is for nodes, PITR/snapshots are for mistakes and corruption, Global Database is for regions.** Do not reach for a snapshot restore when you need a failover, or for a failover when someone dropped a table. The RTO/RPO numbers tell you which tool fits which incident, and the design exam will hand you an incident and ask which you reach for.

## 1.12a — A worked migration: the safe way and the dangerous way

To make §1.6 concrete, here is the same logical change — "add a `NOT NULL` column with a computed default to a 300 GiB `orders` table" — done the dangerous way and the safe way, with the Aurora-specific I/O note for each.

**The dangerous way (do not do this on a hot table):**

```sql
-- This takes an ACCESS EXCLUSIVE lock for the WHOLE rewrite and, on older
-- engines, rewrites every row -> redo for every page -> quorum writes for
-- 300 GiB of pages -> billed I/O on Aurora Standard, and a multi-minute
-- write outage while the lock is held.
ALTER TABLE orders ADD COLUMN region_code text NOT NULL DEFAULT compute_region(id);
```

The `compute_region(id)` default is *volatile* (it depends on the row), so PostgreSQL cannot store it as a constant in the catalog — it must materialize the value into every existing row. That is a full-table rewrite under `ACCESS EXCLUSIVE`. On a local disk it is slow; on Aurora Standard it is slow *and* it shows up on the bill as storage I/O.

**The safe way (lock-aware and I/O-aware):**

```sql
-- 1. Add the column nullable with no default — metadata-only, instant, no rewrite.
ALTER TABLE orders ADD COLUMN region_code text;

-- 2. Backfill in batches so no single transaction rewrites the whole table
--    and locks stay short. Each batch is a small, committed unit of redo.
DO $$
DECLARE
  rows_updated integer;
BEGIN
  LOOP
    UPDATE orders
       SET region_code = compute_region(id)
     WHERE region_code IS NULL
       AND id IN (SELECT id FROM orders WHERE region_code IS NULL LIMIT 5000);
    GET DIAGNOSTICS rows_updated = ROW_COUNT;
    EXIT WHEN rows_updated = 0;
    COMMIT;                       -- spread the redo / quorum writes over time
    PERFORM pg_sleep(0.05);       -- let other traffic through; smooth the I/O
  END LOOP;
END $$;

-- 3. Add the NOT NULL constraint as NOT VALID, then validate separately so the
--    expensive scan does not hold ACCESS EXCLUSIVE.
ALTER TABLE orders ADD CONSTRAINT orders_region_nn CHECK (region_code IS NOT NULL) NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT orders_region_nn;   -- SHARE UPDATE EXCLUSIVE, non-blocking for reads/writes
```

Both versions reach the same end state. The safe version never holds a long exclusive lock, spreads the redo (and therefore the Aurora quorum-write I/O) over time instead of in one billed burst, and lets production traffic through. The discipline is identical to community Postgres; the *added* reason to do it on Aurora is the per-I/O billing of the rewrite. If you run migrations like this frequently, that is an argument for **I/O-Optimized** (Lecture 2), which removes the per-I/O charge entirely and makes the rewrite cost predictable.

## 1.12b — RDS for PostgreSQL: when you would still pick it over Aurora

Aurora is not always the answer, and the design exam rewards knowing the cases where plain RDS PostgreSQL is the better call:

- **You need an extension or engine version Aurora's fork lags on.** Aurora PostgreSQL tracks community releases with a lag, and a few extensions are unsupported or version-gated. RDS runs the *community* engine, so it adopts new minor versions and extensions faster. If you depend on a bleeding-edge extension, RDS (or self-managed) may be your only option.
- **Your workload is small and steady, and cost is dominated by the storage premium.** Aurora's compute is competitive, but its storage and I/O model carries a premium over RDS `gp3` storage for small databases that do not need the shared-storage failover/read-scale features. A 20 GiB internal tool with one user does not need six-way quorum storage; RDS single-AZ or Multi-AZ is cheaper.
- **You want the simplest possible mental model.** RDS Multi-AZ (one standby) is "primary + synchronous standby, DNS failover" — a model every DBA already knows. Aurora's shared-storage model is more capable but less familiar.

The honest summary: **Aurora wins when you need fast failover, read scale-out, or large/growing volumes; RDS wins when you need the freshest community engine, a small steady footprint, or the simplest model.** Both are "managed Postgres"; only Aurora replaces the storage layer.

## 1.13 — Aurora Global Database: the storage trick, applied across regions

Aurora Global Database extends the §1.2 idea across regions. Instead of logical replication (which would replay SQL in the secondary region and lag under load), Aurora replicates at the **storage layer**: a dedicated replication infrastructure ships redo log records from the primary region's storage fleet to the secondary region's storage fleet, typically with **sub-second lag** and without consuming the primary's compute (the replication is done by the storage/replication-agent layer, not by a reader instance straining to keep up).

The secondary region holds a read-only Aurora cluster you can serve reads from (region-local low-latency reads), and gives you two failover modes:

- **Managed planned failover.** For a controlled region switch (a drill, a maintenance event). Aurora coordinates the promotion so RPO is **0**; RTO is a few minutes.
- **Unplanned detach-and-promote.** For a real primary-region outage. You promote the secondary to a standalone primary. RPO is the tiny replication lag at the moment of failure (sub-second to low seconds); RTO is larger and involves repointing your application's writes to the new region.

This is the capstone's cross-region store, verbatim: "Aurora Postgres (multi-AZ + cross-region read replica) for analytical queries." The multi-AZ part is the cluster from Exercise 1; the cross-region read replica is a Global Database secondary. You add it as a stretch goal in the mini-project so the capstone's DR posture is already rehearsed. Know the distinction from cross-region *snapshot copy* (§1.12.4): a Global Database secondary is **continuously, sub-second current**; a copied snapshot is **as stale as the snapshot**. One is warm-standby DR; the other is backup/restore DR. They cost very different amounts and buy very different RPOs.

## 1.14 — What to take into the rest of the week

- Aurora compute ships **only redo log records** to a **6-copy, 3-AZ, 10 GiB-segment** storage fleet. The log is the database.
- **Write quorum 4/6, read quorum 3/6.** Survives **AZ loss** for writes, **AZ + 1** for reads.
- Readers **share the writer's storage**, so failover is **10–30 s** (vs RDS Multi-AZ 60–120 s), replica lag is **milliseconds**, and a reader costs **compute but not a second storage copy**.
- The **cluster (writer) endpoint** is a CNAME Aurora re-points on failover — your app's write DSN never changes. The **reader endpoint** round-robins *connections*, not queries.
- The volume **auto-grows to 128 TiB** and does not reliably shrink.
- Migrations are **lock-safe the same as community Postgres**, but full-table rewrites drive **quorum-write storage I/O that is billed per-I/O on Standard** — estimate the pages and the dollars.
- The open-source shadow: **Patroni/CloudNativePG** for self-operated HA (log-replay failover, 1× storage per replica, you own it), **Citus** for write sharding (the one thing Aurora's single writer cannot do).

Tomorrow's lecture takes the cost shape you just learned — single writer, shared storage, per-I/O-or-I/O-Optimized billing — and turns it into the ACU spreadsheet that decides whether Aurora Serverless v2 saves you money or quietly burns it.

## 1.15 — Five misconceptions to unlearn before the design exam

These come up in real reviews. Get them straight now:

1. **"Aurora replicas are async, so I might read stale data like an RDS replica."** No — Aurora readers serve from the *same* shared volume, and lag is single-digit-to-tens of milliseconds (buffer-cache coherence), not the seconds of WAL-shipping. There is still a tiny lag, so a read-after-write against the reader endpoint can miss a just-committed row, but it is milliseconds, not seconds. For strict read-your-writes, read from the writer endpoint.

2. **"Aurora has no data-loss window on failover because it's synchronous to a standby."** The right *answer* (RPO 0 in-region) but the wrong *reason*. There is no standby — there is one shared volume that the promoted reader simply opens. The durability comes from the 4/6 quorum write at commit time, not from a synchronous standby.

3. **"Adding readers scales my writes."** No. Aurora has exactly **one writer**. Readers scale *reads* only. Write scale-out needs Citus, Aurora Limitless, or application-level sharding — none of which a vanilla Aurora cluster gives you.

4. **"I should size my instance for storage."** Aurora storage is decoupled from compute and auto-grows to 128 TiB. You size the *instance* for CPU/RAM (the working set and query concurrency), never for disk capacity. A 10 TiB database can run on a `db.r7g.large` if its hot set fits in 16 GiB of RAM.

5. **"A bigger backup retention is free."** Continuous backup within the retention window is included, but **manual snapshots persist after cluster deletion and are billed until you delete them.** The classic surprise bill is a forgotten 2 TiB snapshot from six months ago. The mini-project rubric checks for orphaned snapshots for exactly this reason.

If you can refute all five at a whiteboard with the architecture as your evidence, you understand Aurora well enough for the exam and the capstone.
