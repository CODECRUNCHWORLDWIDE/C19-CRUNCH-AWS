# Week 6 — Storage: S3, EBS, EFS, FSx, and the Lifecycle Game

Welcome to the storage week. By Friday you will have a production-shape S3 bucket that is KMS-encrypted with a customer-managed key, versioned, object-locked where it matters, lifecycled through four storage classes, replicated to a second region, and fronted by an Object Lambda that transforms objects on `GET` — all defined in CDK, with the equivalent CloudFormation and OpenTofu sitting next to it so you can read the substrate. You will also have mounted one EFS file system into an ECS Fargate task and an EC2 instance at the same time, and you will have benchmarked `gp3` against `io2` on a synthetic Postgres workload and written up which one wins at what cost.

This is the week the course stops treating S3 as "a place to dump files." S3 is a database. It has consistency semantics, a cost model with five-plus dimensions, a lifecycle engine, a replication topology, a query surface (`S3 Select`, and through Athena in Week 11), and a transform layer (Object Lambda). The teams that lose money on AWS storage are the ones who never learned that. You are not going to be one of them.

Everything you build this week is **load-bearing for later weeks**. The lifecycled, CRR-replicated, KMS-encrypted bucket you ship in the mini-project becomes the **data-lake bucket** in Week 11 (S3 + Athena + Glue) and the **CRR-protected lake bucket** in Week 13 (multi-region DR). The shared-EFS pattern reappears anywhere the capstone needs shared state across compute. Build it like you mean it.

We assume you finished Weeks 1–5: you have a multi-account org, IAM done right, a CDK app that bootstraps and deploys, a production VPC with endpoints, and the compute spectrum (EC2 → Fargate → EKS) under your fingers. We will reuse all of it. The VPC endpoints from Week 4 matter a lot this week — S3 traffic that goes over a Gateway endpoint instead of a NAT Gateway is the difference between a $0 data-transfer line and a real one.

## Learning objectives

By the end of this week, you will be able to:

- **Choose** the right S3 storage class for a given access pattern, and explain the retrieval-latency / retrieval-cost / storage-cost trade-off across Standard, IA, One-Zone-IA, Glacier Instant Retrieval, Glacier Flexible Retrieval, and Deep Archive.
- **Author** a lifecycle policy that transitions objects through tiers on a schedule (Standard → IA at 30d → Glacier IR at 90d → Deep Archive at 365d) and expires noncurrent versions, in CDK, CloudFormation, and OpenTofu.
- **Encrypt** a bucket with a customer-managed KMS key (SSE-KMS with a CMK), enable bucket keys to cut KMS request cost, and write the key policy that lets the right principals and *only* the right principals decrypt.
- **Enable** versioning, Object Lock (governance and compliance modes), and retention, and reason about when WORM storage is a legal requirement versus a foot-gun.
- **Configure** Block Public Access at the account and bucket level and explain why "make it public" is almost never the right answer in 2026.
- **Build** Same-Region Replication (SRR) and Cross-Region Replication (CRR) with replica-side KMS re-encryption, and reason about Replication Time Control (RTC) and its SLA.
- **Deploy** an S3 Object Lambda Access Point with a Lambda that transforms objects on `GET` (here: watermarking JPEGs), and explain where Object Lambda beats a pre-transform pipeline and where it does not.
- **Generate** presigned URLs for time-boxed, credential-free `GET`/`PUT`, and query objects in place with `S3 Select`.
- **Pick** an EBS volume type (`gp3`, `io2` Block Express, `st1`, `sc1`) from a workload shape, size IOPS and throughput independently on `gp3`, and encrypt volumes and snapshots with KMS.
- **Decide** between EBS, EFS, and the FSx family (Lustre, Windows File Server, NetApp ONTAP, OpenZFS) for a given workload, and mount EFS into Fargate and EC2 simultaneously.
- **Estimate** the monthly cost of a storage design before you deploy it, and name the open-source comparators (MinIO, Ceph, JuiceFS) and when self-hosting actually beats S3.

## Prerequisites

This week assumes you have completed Weeks 1–5 of C19, or have equivalent fluency. Specifically:

- A working CDK app (TypeScript) that you can `cdk deploy` into a `dev` account, from Week 3.
- A production VPC with S3 and DynamoDB **Gateway endpoints** and Interface endpoints for STS/KMS/ECR, from Week 4. We mount EFS into private subnets this week; you need that VPC.
- An ECS Fargate service and a way to run a one-off EC2 instance, from Week 5.
- `aws` CLI v2 configured with an SSO profile, `cdk` v2 (`aws-cdk-lib` 2.x), Node 20+, Python 3.12+, and `tofu` (OpenTofu) 1.8+ installed.
- IAM that can create buckets, KMS keys, Lambda functions, EFS file systems, and EBS volumes in `dev`. Your Week 2 permission boundary allows all of this except production S3.

If you cannot `cdk deploy` a stack into `dev` right now, fix that before Tuesday. We will not stop to re-teach bootstrap.

## Topics covered

- **S3 as a database.** Strong read-after-write consistency (since Dec 2020), the flat keyspace, request rate scaling per prefix, ETags, conditional writes (`If-None-Match`, since 2024), and why "list then get" is an anti-pattern.
- **Storage classes.** Standard, Standard-IA, One-Zone-IA, Glacier Instant Retrieval, Glacier Flexible Retrieval, Glacier Deep Archive, and Intelligent-Tiering — the five cost dimensions and the minimum-duration and minimum-object-size charges that bite you.
- **Lifecycle rules.** Transitions, expirations, noncurrent-version handling, `AbortIncompleteMultipartUpload`, filters by prefix and tag.
- **Intelligent-Tiering.** When to let AWS move objects for you instead of writing a lifecycle rule, and the monitoring-and-automation per-object fee.
- **Encryption.** SSE-S3 vs SSE-KMS (AWS-managed key vs CMK) vs SSE-C vs DSSE-KMS, S3 Bucket Keys, and the KMS request-cost math that makes Bucket Keys non-optional at scale.
- **Object Lock & retention.** Governance vs compliance mode, retention periods, legal holds, WORM.
- **Versioning & replication.** Versioning mechanics, delete markers, SRR vs CRR, replica encryption, RTC, replication metrics.
- **Object Lambda & S3 Select.** Transforming on read; querying CSV/JSON/Parquet in place.
- **Presigned URLs & multipart upload.** Time-boxed credential-free access; multipart for large objects and resumable uploads.
- **Block Public Access.** Account-level and bucket-level settings, the four toggles, and ACLs being disabled by default in 2026.
- **EBS.** `gp3` (the default — decoupled IOPS/throughput/size), `io2` Block Express (sub-millisecond, 256k IOPS, durability 99.999%), `st1`/`sc1` (throughput-optimized HDD for streaming), snapshots, fast snapshot restore, and KMS-encrypted volumes.
- **EFS.** NFSv4.1, multi-AZ, Elastic vs Provisioned throughput, IA and Archive tiers with lifecycle management, access points, mount targets, and mounting from Fargate and EC2.
- **FSx family.** Lustre (HPC/ML scratch + S3-linked), Windows File Server (SMB + Active Directory), NetApp ONTAP (multiprotocol, snapshots, tiering), OpenZFS — the one-line decision for each.
- **Open-source comparators.** MinIO (S3-compatible object store), Ceph (unified object/block/file), JuiceFS (POSIX filesystem backed by object storage) — when self-hosting wins and when it is a trap.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                                        | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|--------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | S3 mental model, storage classes, lifecycle, encryption      |    3h    |    1.5h   |     0h     |    0.5h   |   0.5h   |     0h       |    0.5h    |     6h      |
| Tuesday   | Build the lifecycled, KMS-encrypted, versioned bucket        |    1h    |    2.5h   |     0h     |    0.5h   |   1h     |     0.5h     |    0.5h    |     6h      |
| Wednesday | CRR + Object Lambda; replication topology & cost engineering |    2h    |    2.5h   |     0h     |    0.5h   |   0.5h   |     0h       |    0h      |     5.5h    |
| Thursday  | EBS vs EFS vs FSx; mount EFS into Fargate + EC2               |    1h    |    2h     |     0h     |    0.5h   |   1h     |     1h       |    0.5h    |     6h      |
| Friday    | gp3 vs io2 benchmark challenge; cost write-up                |    0h    |    0h     |     3h     |    0.5h   |   0.5h   |     1.5h     |    0.5h    |     6h      |
| Saturday  | Mini-project deep work                                       |    0h    |    0h     |     0h     |    0h     |   0.5h   |     3.5h     |    0h      |     4h      |
| Sunday    | Quiz, cost report, review                                    |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                              | **7h**   | **8.5h**  | **3h**     | **4h**    | **4h**   | **9h**       | **2.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Current 2026 AWS docs, re:Invent talks, and open-source comparator links |
| [lecture-notes/01-s3-is-a-database.md](./lecture-notes/01-s3-is-a-database.md) | S3 as a database: consistency, keyspace, storage classes, lifecycle, encryption, versioning, Object Lock, Object Lambda, S3 Select, presigned URLs, Block Public Access |
| [lecture-notes/02-storage-cost-engineering.md](./lecture-notes/02-storage-cost-engineering.md) | Lifecycle tiers, replication topology, EBS vs EFS vs FSx selection, and the open-source comparators |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-lifecycled-kms-bucket.md](./exercises/exercise-01-lifecycled-kms-bucket.md) | Build a KMS-CMK, versioned, four-tier-lifecycled bucket in CDK |
| [exercises/exercise-02-crr-and-object-lambda.ts](./exercises/exercise-02-crr-and-object-lambda.ts) | Add CRR to a second region plus a watermarking Object Lambda |
| [exercises/exercise-03-shared-efs.py](./exercises/exercise-03-shared-efs.py) | Mount one EFS file system into Fargate and EC2 and prove shared read/write |
| [challenges/README.md](./challenges/README.md) | Index of the weekly challenge |
| [challenges/challenge-01-gp3-vs-io2-benchmark.md](./challenges/challenge-01-gp3-vs-io2-benchmark.md) | Benchmark `gp3` vs `io2` on a synthetic Postgres workload and write the decision doc |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the storage-layer mini-project (becomes the data-lake foundation) |
| [quiz.md](./quiz.md) | 14 questions with an answer key |
| [homework.md](./homework.md) | Concrete homework with deliverables and a rubric |

## The "cost report" promise

C19 ends every week with a working artifact **and a cost report**. This week the cost report is not optional decoration — it is the point. Before you `cdk deploy` anything, you will write down the estimated monthly cost of the design. After you deploy and load test data, you will pull the actual numbers from the S3 Storage Lens dashboard and Cost Explorer and compare. If your estimate and your actual differ by more than 2x, you misunderstood the cost model, and the homework asks you to explain why.

A recurring marker this week:

```
Storage class breakdown · Standard 4.2 GiB · IA 11.0 GiB · Glacier IR 38.4 GiB · Deep Archive 220.1 GiB · est. $1.83/mo
```

If you cannot produce that line for your own bucket, you have not finished the week.

## Tear-down discipline

Most of this week fits inside or near the free tier — S3 storage at these volumes is pennies, EFS bursting is cheap, and a `gp3` volume for the benchmark is a few cents an hour. The two things that cost real money if you leave them running:

- **The benchmark EC2 instance** for the `gp3` vs `io2` challenge. Use a `c7i` or `m7i`, run the benchmark, and `cdk destroy` (or terminate) the same day. An `io2` volume provisioned at 64,000 IOPS is not free to leave sitting there.
- **CRR egress.** Cross-region replication moves bytes between regions and you pay inter-region transfer. Replicate a few small test objects, not gigabytes.

Set your Week 1 Budgets alert ($5 / $25 / $80) and trust it. Run `cdk destroy --all` on Sunday for everything except the mini-project bucket, which you keep — it is the data-lake foundation.

## Stretch goals

If you finish early and want to push further:

- Stand up **MinIO** locally with Docker and point the AWS SDK at it (`--endpoint-url http://localhost:9000`). Run the same lifecycle and replication exercises against MinIO and note what is and is not supported.
- Add **S3 Storage Lens** advanced metrics to your account and read the cost-optimization recommendations.
- Enable **S3 Inventory** on the mini-project bucket and query the inventory report with Athena (a preview of Week 11).
- Replace the Object Lambda's image library and add a second transform (EXIF stripping) behind a query-string flag.
- Read the **JuiceFS** architecture doc and write a one-paragraph note on when a POSIX-over-object-storage filesystem beats EFS for an ML training workload.

## Up next

Continue to **Week 7 — CI/CD on AWS: CodeBuild, CodePipeline, CodeDeploy, ECR** once your mini-project bucket is deployed and you have pushed the CDK to your GitHub. You will be pushing container images into ECR with lifecycle policies — the same lifecycle thinking, a different service.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
