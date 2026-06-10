# Lecture 2 — Storage Cost Engineering: Lifecycle Tiers, Replication Topology, and Picking EBS vs EFS vs FSx

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can put a defensible dollar number on a storage design before you build it; design a replication topology (SRR/CRR) with the right durability, latency, and cost trade-offs; and choose between EBS, EFS, and the FSx family from a workload shape — including knowing when MinIO, Ceph, or JuiceFS beat the managed service.

If Lecture 1 was "S3 is a database," Lecture 2 is the FinOps and block/file half:

> **Storage is the line item that grows while you sleep. Compute scales to zero; storage does not. The engineer who designs the lifecycle and replication topology *first*, and picks the block/file primitive from the workload shape instead of habit, saves more money over a system's life than any other single decision in this course.**

---

## 1. Cost engineering is a design activity, not a clean-up activity

Most teams "do FinOps" after the bill arrives: someone notices S3 is $4,000/month, opens Cost Explorer, and starts deleting things. That is clean-up, and it is the expensive way. Cost engineering happens **at design time**, on a whiteboard, before a byte is written. You answer four questions:

1. **How big does this get, and how fast?** (Storage growth rate — GB/day.)
2. **What is the access pattern over an object's lifetime?** (Hot for N days, then cold forever? Read once and deleted? Re-read on audit?)
3. **What is the durability/availability requirement?** (Can I lose an AZ? A region? Nothing, ever?)
4. **What is the read:write ratio and request shape?** (A billion 4 KB objects is a *request* problem; a thousand 5 GB objects is a *storage* problem.)

Those four answers determine the storage class, the lifecycle, the encryption strategy, the replication topology, and whether you even want S3 at all. Let's make this concrete with a worked estimate, because the mini-project requires you to produce one.

---

## 2. A worked cost estimate (the kind the mini-project wants)

Suppose a logging-and-analytics workload: **50 GB/day** of new objects, average object size **256 KB** (so ~200k objects/day), access pattern "hot for 7 days, warm for 30, archived for compliance for 7 years, read on audit maybe twice a year." Region `us-east-1`, prices approximate and current-ish for 2026 (always re-check before committing to a doc):

**Naïve design — everything in S3 Standard forever, 7 years:**

- Steady-state stored at 7 years ≈ 50 GB/day × 365 × 7 ≈ **127.75 TB**.
- Standard at ~$0.023/GB-mo → 127,750 GB × $0.023 ≈ **$2,938/month** and climbing.

**Engineered design — the lifecycle staircase:**

- **Standard, days 0–30** (the hot + warm window): ~1.5 TB rolling × $0.023 ≈ **$35/mo**.
- **Glacier IR, days 30–365** (still occasionally readable, millisecond): ~18 TB × ~$0.004/GB-mo ≈ **$72/mo**.
- **Deep Archive, day 365+** (the 7-year compliance tail): ~108 TB × ~$0.00099/GB-mo ≈ **$107/mo**.
- Request + transition cost: ~200k transitions/day at Glacier transition rates ≈ a few dollars/mo.

Total engineered ≈ **~$215/month** versus **~$2,938/month** naïve, and the gap *widens* every year as the Deep Archive tail grows on the cheapest tier instead of the most expensive. That is a ~14x saving from one lifecycle policy. **This is the single highest-leverage paragraph in the storage week.** Memorize the method, not the numbers: project the volume over the retention horizon, multiply each lifecycle segment by its tier price, and compare to the naïve "Standard forever."

The two failure modes of this estimate:

- **You forgot retrieval cost.** If the auditors actually read 108 TB out of Deep Archive twice a year, retrieval + the temporary Standard copy is a real (and lumpy) cost. Model the read, not just the store.
- **You forgot the request bill.** Two hundred thousand `PUT`s/day plus transitions plus reads is a request line. For tiny-object workloads it can dwarf storage. If objects are small and numerous, the move is often to **aggregate** (batch many records into one larger object — exactly what Kinesis Firehose does for the data lake in Week 11) rather than to tier.

---

## 3. Replication topology: SRR, CRR, and what you are actually buying

Replication asynchronously copies *new* objects from a source bucket to a destination bucket. Two flavors:

- **SRR (Same-Region Replication)** — same region, different bucket. Used for: log aggregation across accounts, separating prod data into a read-only analytics account, meeting "two copies in two buckets" data-governance rules. Cheap (no inter-region transfer).
- **CRR (Cross-Region Replication)** — different region. Used for: disaster recovery (region loss), latency (serve reads from a region near users), and regulatory data-residency (a copy that must live in `eu-central-1`). You pay **inter-region data transfer** plus the destination storage.

What replication does and does not give you:

- It replicates **new** objects after you enable it (existing objects need **S3 Batch Replication** to backfill).
- It is **asynchronous** — by default, most objects replicate within minutes, but there is no SLA unless you turn on **Replication Time Control (RTC)**, which guarantees 99.99% of objects replicate within **15 minutes** and emits CloudWatch metrics. RTC costs extra per GB. Turn it on only when your RPO (recovery point objective) actually requires a bounded replication lag.
- It can **re-encrypt on the replica** with a *different* KMS key in the destination region — which you must do, because a `us-east-1` CMK cannot decrypt in `eu-west-1`. Each region gets its own CMK (or a multi-region KMS key, Week 13).
- It does **not** replicate deletes by default in a way that destroys data: delete markers can optionally replicate, but the underlying versions are preserved. This is deliberate — replication is for durability, not for mirroring `rm`.

The CRR rule needs an IAM role S3 assumes to read the source and write the destination, plus the destination key permission. In CDK:

```typescript
import { Bucket, BucketEncryption, BlockPublicAccess, CfnBucket } from 'aws-cdk-lib/aws-s3';
import { Role, ServicePrincipal, PolicyStatement, Effect } from 'aws-cdk-lib/aws-iam';

// (sourceBucket, sourceKey, destBucketArn, destKeyArn defined elsewhere)
const replicationRole = new Role(this, 'ReplRole', {
  assumedBy: new ServicePrincipal('s3.amazonaws.com'),
});
replicationRole.addToPolicy(new PolicyStatement({
  effect: Effect.ALLOW,
  actions: ['s3:GetReplicationConfiguration', 's3:ListBucket'],
  resources: [sourceBucket.bucketArn],
}));
replicationRole.addToPolicy(new PolicyStatement({
  effect: Effect.ALLOW,
  actions: ['s3:GetObjectVersionForReplication', 's3:GetObjectVersionAcl', 'kms:Decrypt'],
  resources: [`${sourceBucket.bucketArn}/*`, sourceKey.keyArn],
}));
replicationRole.addToPolicy(new PolicyStatement({
  effect: Effect.ALLOW,
  actions: ['s3:ReplicateObject', 's3:ReplicateDelete', 'kms:GenerateDataKey'],
  resources: [`${destBucketArn}/*`, destKeyArn],
}));

// CRR is still an L1 escape hatch on the CfnBucket in 2026.
const cfnBucket = sourceBucket.node.defaultChild as CfnBucket;
cfnBucket.replicationConfiguration = {
  role: replicationRole.roleArn,
  rules: [{
    id: 'crr-to-dr-region',
    status: 'Enabled',
    priority: 0,
    deleteMarkerReplication: { status: 'Enabled' },
    filter: {},
    destination: {
      bucket: destBucketArn,
      storageClass: 'STANDARD_IA',                 // store the replica cheaper than source
      encryptionConfiguration: { replicaKmsKeyId: destKeyArn },
    },
    sourceSelectionCriteria: { sseKmsEncryptedObjects: { status: 'Enabled' } },
  }],
};
```

**Topology judgment:** a replica is a *recovery* asset, so it is fine for it to live in a cheaper class (`STANDARD_IA` above). Do not pay Standard prices twice for a copy you only read during a regional failover. And do not enable RTC unless your RPO is tight enough to need a 15-minute guarantee — most DR postures (pilot light, warm standby — Week 13) tolerate a few minutes of normal replication lag.

---

## 4. EBS: block storage, and how to pick a volume type

EBS is a *network-attached block device* — it looks like a local disk to one EC2 instance (or, with `io2` Multi-Attach, a few). It is the right primitive for **a filesystem or a database that one instance owns**. Four families matter:

| Type | Media | IOPS | Throughput | Durability | Use it for |
|---|---|---|---|---|---|
| **`gp3`** | SSD | 3,000 baseline, up to 16,000 (provisioned independently) | 125 MB/s base, up to 1,000 MB/s | 99.8–99.9% | **The default.** Boot volumes, most databases, general workloads. |
| **`io2` Block Express** | SSD | up to 256,000 | up to 4,000 MB/s | **99.999%** | Latency-sensitive, IOPS-hungry databases; sub-ms; the durability tier. |
| **`st1`** | HDD | (throughput, not IOPS) | up to 500 MB/s | 99.8–99.9% | Big sequential: log processing, data warehouse scans, streaming. |
| **`sc1`** | HDD | low | up to 250 MB/s | 99.8–99.9% | Cold, infrequently-scanned bulk data. The cheapest block tier. |

The single most important EBS fact for 2026: **`gp3` decouples size, IOPS, and throughput.** On the old `gp2`, IOPS were a function of volume size (3 IOPS/GB) — so to get more IOPS you over-provisioned capacity you did not need. On `gp3` you buy a 100 GB volume and *separately* dial IOPS up to 16,000 and throughput up to 1,000 MB/s. **Migrate every `gp2` volume to `gp3`; it is cheaper and more flexible with zero downtime.** That migration is one of the most reliable FinOps wins on AWS.

When to leave `gp3` for `io2` Block Express: when you need **more than 16,000 IOPS**, **sub-millisecond, consistent latency**, or the **99.999% durability** tier — i.e., a serious transactional database (the kind you would run on RDS/Aurora in Week 8, but here on raw EC2 for the benchmark). `io2` costs meaningfully more per provisioned IOPS, which is exactly why the Friday challenge makes you *prove* the workload needs it before you pay for it.

KMS-encrypt every volume. You can set account-wide default EBS encryption once:

```bash
# Turn on default encryption for all new EBS volumes in this region, with a CMK.
aws ec2 enable-ebs-encryption-by-default
aws ec2 modify-ebs-default-kms-key-id --kms-key-id alias/my-ebs-cmk
```

Snapshots are incremental block-level backups to S3 (managed, not in your buckets), and are themselves encrypted from an encrypted volume. **Fast Snapshot Restore (FSR)** pre-warms a snapshot so a restored volume has full performance immediately instead of lazy-loading blocks on first touch — useful for golden images and fast DR, but it is billed per snapshot per AZ, so enable it only where restore latency matters.

---

## 5. EFS: shared file storage across many instances

EBS attaches to (essentially) one instance. **EFS** is a managed **NFSv4.1** file system that **mounts on many instances, across AZs, simultaneously**, with POSIX semantics. It grows and shrinks automatically; you pay for what you store. This is the primitive for **shared state**: a web fleet that needs a common content directory, a CI farm sharing a cache, an ML team sharing a dataset, a CMS with user uploads behind multiple app servers.

Throughput modes (pick the right one — this is where EFS bills surprise people):

- **Elastic** (default, recommended for most): throughput scales with demand, pay per GB transferred. Best for spiky or unpredictable workloads.
- **Provisioned**: you buy a fixed MB/s regardless of stored size. For steady high-throughput workloads where Elastic's per-request cost would be higher.
- **Bursting** (legacy): throughput scales with stored size via a credit system; fine for small/quiet file systems but it throttles when credits run out — a classic 3am surprise.

EFS has its own **lifecycle management**: move files not accessed in N days to **Infrequent Access (IA)** and then to **Archive**, cutting storage cost ~85–95% for cold files, with a per-GB retrieval charge on access. It is the EFS analog of the S3 lifecycle staircase, and you should turn it on for any file system with a long tail of cold files.

EFS uses **mount targets** (one per AZ, an ENI in your VPC) and optionally **access points** (an enforced POSIX user/group and root directory per application — the clean way to give two apps isolated subtrees of one file system). Security is a Security Group on the mount target plus IAM/POSIX permissions.

Mounting the *same* EFS into both **ECS Fargate** and **EC2** at once (Exercise 3) is the canonical "shared storage" demonstration. On Fargate you declare an `efsVolumeConfiguration` on the task definition; on EC2 you mount with the EFS mount helper:

```bash
# On EC2 (Amazon Linux 2023): install the helper and mount via the access point.
sudo dnf install -y amazon-efs-utils
sudo mkdir -p /mnt/shared
sudo mount -t efs -o tls,accesspoint=fsap-0abc123 fs-0123456789abcdef0:/ /mnt/shared
echo "hello from EC2 $(date)" | sudo tee /mnt/shared/from-ec2.txt
```

```jsonc
// On Fargate: the task definition volume + mountPoint (rendered by CDK).
{
  "volumes": [{
    "name": "shared",
    "efsVolumeConfiguration": {
      "fileSystemId": "fs-0123456789abcdef0",
      "transitEncryption": "ENABLED",
      "authorizationConfig": { "accessPointId": "fsap-0abc123", "iam": "ENABLED" }
    }
  }],
  "containerDefinitions": [{
    "name": "app",
    "mountPoints": [{ "sourceVolume": "shared", "containerPath": "/mnt/shared", "readOnly": false }]
  }]
}
```

Write `from-ec2.txt` on the instance, read it from the Fargate container, write `from-fargate.txt` back, read it on EC2 — that round-trip is the proof of shared read/write, and it is exactly what Exercise 3 asks you to demonstrate.

---

## 6. FSx: the specialized file systems, one line each

When EFS's NFS-and-Linux model is wrong, the **FSx** family gives you a managed file system tuned to a specific world. You will rarely build these from scratch in this course, but you must be able to name the right one in a design review:

- **FSx for Lustre** — the HPC/ML scratch filesystem. Hundreds of GB/s, sub-millisecond, and it can be **linked to an S3 bucket** so your training data lake appears as a POSIX filesystem and results flush back to S3. This is the answer for **GPU training and HPC** that needs to chew through a lake fast. (Ties directly into Week 11's SageMaker work.)
- **FSx for Windows File Server** — fully managed **SMB** with **Active Directory** integration, DFS, shadow copies. The answer when Windows apps need a real Windows file share. Do not try to fake this with EFS.
- **FSx for NetApp ONTAP** — multiprotocol (NFS *and* SMB on the same data), with ONTAP's snapshots, dedup/compression, and automatic tiering to a cheaper capacity pool. The answer for **enterprise migrations** that depend on ONTAP features, and for mixed Linux/Windows access to one dataset.
- **FSx for OpenZFS** — managed ZFS: snapshots, clones, NFS, low-latency. The answer when you want **ZFS semantics** (instant clones for dev/test, fine-grained snapshots) as a service.

The decision tree, compressed: **Need block for one DB → EBS. Need shared POSIX/Linux across instances → EFS. Need fast scratch over a lake for HPC/ML → FSx Lustre. Need Windows/SMB+AD → FSx Windows. Need ONTAP or multiprotocol → FSx ONTAP. Need ZFS-as-a-service → FSx OpenZFS. Need object → S3.**

---

## 7. The full storage decision table

Put this on a slide and defend it in a design review:

| Workload shape | Primitive | Why |
|---|---|---|
| App reads/writes objects by key; web assets; backups; data lake | **S3** | Object, infinite scale, lifecycle, cheapest at rest |
| One EC2 instance owns a filesystem or a database | **EBS `gp3`** | Block, low latency, tunable IOPS/throughput |
| Latency-critical, IOPS-hungry single-instance DB | **EBS `io2` Block Express** | Sub-ms, up to 256k IOPS, 99.999% durable |
| Sequential big scans / log streaming on one instance | **EBS `st1` / `sc1`** | Throughput-optimized HDD, cheap per GB |
| Many Linux instances share files concurrently | **EFS** | Multi-AZ NFS, mounts everywhere at once |
| HPC/ML scratch over an S3 lake | **FSx for Lustre** | Hundreds of GB/s, S3-linked |
| Windows apps need an SMB share with AD | **FSx for Windows** | Managed SMB + Active Directory |
| Enterprise/ONTAP features, mixed NFS+SMB | **FSx for NetApp ONTAP** | Multiprotocol, snapshots, tiering |

---

## 8. The open-source comparators: when self-hosting actually wins

C19 is vendor-aware, not vendor-loyal. Every AWS primitive has an open-source shadow. For storage:

- **MinIO** — a single-binary, S3-API-compatible object store. You ran the SDK against it in Week 3's local stack. *When it wins:* on-prem or edge where there is no AWS region; air-gapped environments; high-throughput internal object storage where S3's per-request and egress fees on a hot internal workload exceed the cost of running your own SSDs. *When it loses:* you become responsible for durability, replication, capacity, and the 3am page. S3's eleven nines are not free to reproduce.
- **Ceph** — a unified distributed store offering object (RGW, S3-compatible), block (RBD), and file (CephFS) from one cluster. *When it wins:* a large private cloud / OpenStack environment that needs all three storage modes from one system, at a scale where the operational team is justified. *When it loses:* small teams — Ceph is powerful and operationally heavy; running it well is a full-time discipline.
- **JuiceFS** — a POSIX (and HDFS, and S3) filesystem that stores **data in any object store** (S3, MinIO, GCS) and **metadata in a fast database** (Redis, TiKV, a SQL DB). *When it wins:* you want EFS-like POSIX semantics with **S3-like economics and scale** — e.g., an ML training job that wants a POSIX mount but the dataset lives in S3 and is huge; JuiceFS gives near-local read performance with object-store durability and cost. *When it loses:* you do not want to operate the metadata engine, or your workload is genuinely object-shaped (then just use S3).

The framing for a design review: **managed services trade money for eliminated operational risk.** Self-hosting MinIO/Ceph/JuiceFS makes sense when (a) you are at a scale where AWS storage fees dwarf the cost of an ops team, (b) you have a hard constraint AWS cannot meet (on-prem, air-gap, residency), or (c) you specifically need a capability the managed service lacks. For everyone else, S3/EFS/FSx and the time you save are the cheaper choice. Know the trade-off; do not be dogmatic in either direction.

---

## 9. Intelligent-Tiering vs a hand-written lifecycle: the honest comparison

There are two ways to move objects down the cost staircase: write a **lifecycle rule** (a deterministic schedule — "30 days then IA") or turn on **Intelligent-Tiering** (S3 watches access and moves each object based on its *actual* last-access time). They are not interchangeable, and the choice is a cost decision, not a religious one.

**Intelligent-Tiering** has, in 2026, these tiers, moved automatically with no retrieval fee for the frequent/infrequent/archive-instant tiers:

- **Frequent Access** — objects touched recently. Priced like Standard.
- **Infrequent Access** — not touched for 30 days. Priced like Standard-IA (~40% cheaper).
- **Archive Instant Access** — not touched for 90 days. Priced like Glacier IR (~68% cheaper than Standard), still millisecond reads.
- **Optional Archive / Deep Archive tiers** (you opt in) — not touched for 90–180+ days; these *do* impose a restore latency, so only enable them when objects can tolerate it.

The catch is the **monitoring-and-automation fee**: roughly **$0.0025 per 1,000 objects per month**. That fee is per *object*, not per GB. So the decision pivots on object size:

- **Large objects, unpredictable access** → Intelligent-Tiering wins. A workload of 100,000 objects averaging 50 MB each is 5 TB. The monitoring fee is `100,000 / 1,000 × $0.0025 = $0.25/mo` — trivial against the storage savings, and you never have to predict the access pattern.
- **Tiny objects, huge count** → Intelligent-Tiering is a trap. A billion 8 KB objects (8 TB) costs `1,000,000,000 / 1,000 × $0.0025 = $2,500/month` in monitoring fees *alone*, before storage. For that shape, either aggregate the objects (Firehose-style batching) or use a deterministic lifecycle rule, which has no per-object monitoring charge.
- **Known, predictable access pattern** → a hand-written lifecycle rule is cheaper and more transparent. If you *know* logs are cold after 30 days, the rule costs nothing to run and you can read it in code review. Do not pay a monitoring fee to discover a fact you already know.

The senior heuristic: **Intelligent-Tiering buys you out of having to predict access patterns, at a per-object price.** Use it when the access pattern is genuinely unknown or varies object-by-object *and* objects are large enough that the monitoring fee is noise. Use a deterministic lifecycle rule when you know the pattern. Never put a billion tiny objects in Intelligent-Tiering.

One more sharp edge that bites teams every quarter: the **minimum object size** and **minimum storage duration** charges on the cold tiers. Standard-IA, One-Zone-IA, and the Glacier classes bill any object as if it were at least **128 KB**, and they bill a **minimum storage duration** (30 days for IA, 90 for Glacier Flexible/IR, 180 for Deep Archive) even if you delete the object on day 1. A lifecycle rule that transitions a swarm of 10 KB objects to IA does not save money — it *loses* it, because each object now bills at 128 KB in a class with an early-deletion penalty. **Lifecycle the big cold objects; leave (or aggregate) the small ones.** This is the single most common lifecycle-policy bug in production, and the homework makes you reason about it explicitly.

---

## 10. Data transfer and request cost: the dimensions people forget

Storage-at-rest is the dimension everyone models and the one that is usually *not* the surprise on the bill. The surprises live in transfer and requests. Carry these rules:

- **Ingress to S3 is free.** Uploading costs nothing in transfer (you pay the `PUT` request).
- **Egress to the internet is the expensive direction** — roughly `$0.09/GB` for the first tier out of most regions in 2026. Serving large objects directly from S3 to end users is how surprise five-figure bills happen. Put **CloudFront** (Week 4) in front of anything user-facing; CloudFront egress is cheaper and cached, and S3→CloudFront origin transfer is free.
- **S3 to EC2/Lambda/Fargate in the *same region* over a Gateway VPC endpoint is free.** This is why Week 4 drilled VPC endpoints. The same traffic over a NAT Gateway costs NAT data-processing fees *plus* egress. Reading a 1 TB dataset from S3 into a same-region training job costs `$0` over a Gateway endpoint and real money over NAT. Re-read that sentence; it is the most expensive accidental line item in this course.
- **Cross-region transfer (what CRR generates)** is `~$0.02/GB` between most regions. Replicating 1 TB to a DR region is a one-time `~$20` plus the ongoing delta — fine for a real DR posture, ruinous if you accidentally CRR a hot, high-churn bucket. This is why the README tells you to replicate a *few small test objects*, not gigabytes.
- **Requests cost real money at the tiny-object scale.** `PUT`/`COPY`/`POST`/`LIST` are ~`$0.005/1,000`; `GET` is ~`$0.0004/1,000`. A billion `GET`s/month is `$400` in requests before a byte of storage or transfer. Object Lambda adds its own per-request and per-GB-processed charge on top of the underlying `GET`.

A worked transfer estimate for the mini-project's CRR, so you can put it in your cost report. Suppose the source bucket ingests **10 GB/day** of new objects that all match the replication filter, replicated to a DR region:

- Cross-region transfer: `10 GB/day × 30 × $0.02 = $6/month`.
- Destination storage (replica in `STANDARD_IA`): `~300 GB rolling × $0.0125 = $3.75/month`.
- Replication `PUT`s on the destination: negligible unless objects are tiny.
- **RTC, if enabled**, adds a per-GB replication charge on top — only pay it if your RPO needs the 15-minute SLA.

Total CRR overhead ≈ **~$10/month** for this volume. That is the number you write next to "is region-loss protection worth it?" in the design review. For most production data, yes; for a scratch bucket, obviously not. The point is that you can *say the number* before someone asks.

---

## 11. Reading the bill: Storage Lens and Cost Explorer

You cannot engineer what you cannot measure. Two tools close the loop:

- **S3 Storage Lens** — account- (or org-) wide dashboard of storage by bucket, class, prefix, with cost-optimization recommendations ("X% of your IA storage is small objects under the 128 KB minimum — those belong in Standard or should be aggregated"). The free tier covers the basics; advanced metrics add prefix-level detail for a small fee. **Turn it on; it is how you produce the `Storage class breakdown` line from the README.**
- **Cost Explorer** — filter by the `service = Amazon S3` and group by `usage type` to see *which dimension* (storage vs requests vs transfer vs KMS) is actually costing you. This is how you confirm your design estimate matched reality — the closing exercise of the week.

The discipline: **estimate at design time (Section 2), deploy, load representative data, then reconcile estimate vs actual in Storage Lens + Cost Explorer.** If they differ by more than 2x, you misunderstood the cost model, and the homework makes you write down which dimension you got wrong. That reconciliation loop is the entire point of "cost is a feature."

---

## 12. Recap

You should now be able to:

- Produce a defensible monthly cost estimate for a storage design by projecting volume over the retention horizon and pricing each lifecycle segment.
- Design an SRR/CRR topology with replica re-encryption and a cheaper replica class, and decide when RTC is worth it.
- Pick `gp3` vs `io2` vs `st1`/`sc1` from a workload shape, and know why every `gp2` volume should become `gp3`.
- Choose EBS vs EFS vs the FSx family from the decision table, and mount one EFS into Fargate and EC2 at once.
- Name when MinIO, Ceph, and JuiceFS beat the managed AWS service — and when they are a trap.
- Close the loop with Storage Lens and Cost Explorer.

Next: prove it. Continue to the [exercises](../exercises/README.md), then the [gp3-vs-io2 challenge](../challenges/challenge-01-gp3-vs-io2-benchmark.md), and finally the [mini-project](../mini-project/README.md) that becomes your data-lake foundation.

---

## References

- *S3 pricing*: <https://aws.amazon.com/s3/pricing/>
- *S3 replication*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html>
- *Replication Time Control*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-time-control.html>
- *EBS volume types*: <https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html>
- *EFS performance & throughput modes*: <https://docs.aws.amazon.com/efs/latest/ug/performance.html>
- *EFS lifecycle management*: <https://docs.aws.amazon.com/efs/latest/ug/lifecycle-management-efs.html>
- *FSx for Lustre*: <https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html>
- *S3 Storage Lens*: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens.html>
- *MinIO*: <https://github.com/minio/minio> · *Ceph*: <https://docs.ceph.com/> · *JuiceFS*: <https://github.com/juicedata/juicefs>
