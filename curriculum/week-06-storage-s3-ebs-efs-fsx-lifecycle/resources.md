# Week 6 — Resources

Every AWS doc here is free and current as of 2026. The open-source projects are public on GitHub. No paywalled material is linked. AWS pricing pages change; always re-check the number before you put it in a design doc — the URLs below are stable, the dollars are not.

## Required reading (work it into your week)

- **Amazon S3 User Guide — overview** — the canonical reference, kept current per feature:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html>
- **S3 storage classes** — the table you will memorize the shape of:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html>
- **Managing your storage lifecycle** — transitions, expirations, the rules engine:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html>
- **Protecting data with server-side encryption** — SSE-S3, SSE-KMS, DSSE-KMS, Bucket Keys:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/serv-side-encryption.html>
- **Replicating objects (SRR/CRR)** — replication rules, replica encryption, RTC:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html>
- **Transforming objects with S3 Object Lambda**:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/transforming-objects.html>
- **Amazon EBS volume types** — `gp3`, `io2` Block Express, `st1`, `sc1`:
  <https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html>
- **Amazon EFS — how it works** — NFS, mount targets, throughput modes, tiers:
  <https://docs.aws.amazon.com/efs/latest/ug/how-it-works.html>

## S3 depth

- **S3 request rate and performance guidelines** — prefix scaling, 5,500 GET / 3,500 PUT per prefix:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html>
- **S3 consistency model** — strong read-after-write since December 2020:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel>
- **Conditional requests (`If-None-Match` on PUT)** — the 2024 write-if-absent primitive:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-requests.html>
- **Object Lock (WORM)** — governance vs compliance mode, legal holds:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html>
- **Blocking public access** — the four account/bucket toggles:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html>
- **Disabling ACLs (Object Ownership = Bucket owner enforced)** — the 2026 default:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html>
- **Presigned URLs** — time-boxed credential-free access:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html>
- **S3 Select / querying in place** — note that `SelectObjectContent` is deprecated for new use in favor of Athena/S3 Tables, but you must understand it:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/selecting-content-from-objects.html>
- **S3 Intelligent-Tiering**:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/intelligent-tiering.html>
- **S3 Storage Lens** — account-wide storage analytics and cost recommendations:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens.html>
- **S3 Tables (Iceberg-native buckets)** — a 2024/2025 addition you will use in Week 11:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables.html>

## Pricing (re-check the dollars before quoting them)

- **S3 pricing**: <https://aws.amazon.com/s3/pricing/>
- **EBS pricing**: <https://aws.amazon.com/ebs/pricing/>
- **EFS pricing**: <https://aws.amazon.com/efs/pricing/>
- **FSx pricing** (per file-system family): <https://aws.amazon.com/fsx/pricing/>
- **AWS Pricing Calculator** — build the estimate before you build the bucket:
  <https://calculator.aws/>

## EBS / EFS / FSx depth

- **EBS — `io2` Block Express**: <https://docs.aws.amazon.com/ebs/latest/userguide/ebs-io-characteristics.html>
- **EBS snapshots** and Fast Snapshot Restore:
  <https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html>
- **EFS throughput modes** (Elastic, Provisioned, Bursting):
  <https://docs.aws.amazon.com/efs/latest/ug/performance.html>
- **EFS lifecycle management** (IA and Archive tiers):
  <https://docs.aws.amazon.com/efs/latest/ug/lifecycle-management-efs.html>
- **Mounting EFS on ECS Fargate** (the `efsVolumeConfiguration` you need):
  <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/efs-volumes.html>
- **FSx for Lustre** (HPC/ML, S3-linked): <https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html>
- **FSx for NetApp ONTAP** (multiprotocol, tiering): <https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html>
- **FSx for Windows File Server** (SMB + AD): <https://docs.aws.amazon.com/fsx/latest/WindowsGuide/what-is.html>

## IaC references

- **AWS CDK v2 API — `aws-cdk-lib/aws-s3`** (`Bucket`, `LifecycleRule`, `StorageClass`):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3-readme.html>
- **AWS CDK v2 API — `aws-cdk-lib/aws-kms`** (`Key`, key policies):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_kms-readme.html>
- **AWS CDK v2 API — `aws-cdk-lib/aws-efs`**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs-readme.html>
- **CloudFormation `AWS::S3::Bucket` reference**:
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-s3-bucket.html>
- **OpenTofu / Terraform `aws_s3_bucket` and friends** (the resource model split into many small resources):
  <https://search.opentofu.org/provider/hashicorp/aws/latest/docs/resources/s3_bucket>
- **`aws s3` and `aws s3api` CLI references**:
  <https://docs.aws.amazon.com/cli/latest/reference/s3api/>

## Talks (free, no signup)

- **re:Invent — "Deep dive on Amazon S3" (STG3xx)** — the annual S3 internals talk; search the AWS Events YouTube channel for the most recent year:
  <https://www.youtube.com/@AWSEventsChannel>
- **re:Invent — "Optimizing storage costs on AWS"** — the FinOps-for-storage talk:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Building and operating a global object store" — the original S3 history** (Werner Vogels keynotes; search the channel):
  <https://www.youtube.com/@AWSEventsChannel>
- **AWS re:Post — S3 tag** — real operator questions and answers:
  <https://repost.aws/tags/questions>

## Open-source comparators (read these to stay vendor-aware, not vendor-loyal)

- **MinIO** — high-performance S3-compatible object store, single binary, self-hosted:
  <https://github.com/minio/minio>
- **Ceph** — unified distributed object (RGW, S3-compatible), block (RBD), and file (CephFS) storage:
  <https://github.com/ceph/ceph> · docs: <https://docs.ceph.com/>
- **JuiceFS** — a POSIX, HDFS, and S3-compatible distributed filesystem backed by any object store, with metadata in Redis/TiKV/SQL:
  <https://github.com/juicedata/juicefs>
- **SeaweedFS** — fast distributed object/file store, a lighter alternative to Ceph:
  <https://github.com/seaweedfs/seaweedfs>
- **`s5cmd`** — a very fast parallel S3 client (works against S3 and MinIO); great for the benchmark warm-up:
  <https://github.com/peak/s5cmd>
- **`fio`** — the flexible I/O tester you will use for the `gp3` vs `io2` challenge:
  <https://github.com/axboe/fio>
- **`pgbench`** — the Postgres benchmark for the synthetic workload:
  <https://www.postgresql.org/docs/current/pgbench.html>

## Tools you'll use this week

- **`aws` CLI v2** — `aws s3`, `aws s3api`, `aws s3control` (Object Lambda), `aws ec2` (EBS), `aws efs`. Verify with `aws --version`.
- **AWS CDK v2** — `npm i -g aws-cdk`; `cdk --version` should report 2.x.
- **OpenTofu** — `tofu version` should report 1.8+.
- **`fio`** — `brew install fio` / `apt install fio`. The I/O benchmark.
- **`pgbench`** — ships with the PostgreSQL client (`postgresql-client` / `libpq`).
- **`jq`** — for slicing CLI JSON output.
- **Docker** — for running MinIO locally in the stretch goals.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **SSE-KMS** | Server-side encryption where S3 calls KMS to wrap/unwrap the data key. A CMK is a key *you* own. |
| **Bucket Key** | A bucket-level data key that lets S3 avoid one KMS call per object, cutting KMS request cost ~99%. |
| **Glacier IR** | Glacier Instant Retrieval — archive price, millisecond retrieval, 90-day minimum. |
| **Deep Archive** | The cheapest S3 tier; 12-hour retrieval, 180-day minimum. |
| **Intelligent-Tiering** | A class where AWS moves objects between access tiers automatically for a small per-object monitoring fee. |
| **Object Lock** | WORM (write-once-read-many) retention on object versions. Governance mode is bypassable by a privileged role; compliance mode is not, by anyone, ever. |
| **CRR / SRR** | Cross-Region / Same-Region Replication. Asynchronous copy of new objects to another bucket. |
| **RTC** | Replication Time Control — an SLA (99.99% within 15 min) and metrics for replication. Costs extra. |
| **Object Lambda** | A Lambda that sits on an access point and transforms the object body on `GET`. |
| **Presigned URL** | A time-boxed URL that carries a signature so an unauthenticated client can `GET`/`PUT` one object. |
| **BPA** | Block Public Access — four toggles that override any public ACL or bucket policy. |
| **`gp3`** | General-purpose SSD; IOPS, throughput, and size are billed and tuned independently. The default. |
| **`io2` Block Express** | Provisioned-IOPS SSD; up to 256k IOPS, sub-millisecond, 99.999% durability. For databases. |
| **`st1` / `sc1`** | Throughput-optimized / Cold HDD. Cheap, sequential, for logs and big-data streaming. |
| **EFS** | Elastic File System — managed NFSv4.1, multi-AZ, mounts on many instances at once. |
| **FSx** | A family of managed file systems: Lustre, Windows File Server, NetApp ONTAP, OpenZFS. |

---

*If a link 404s, please open an issue so we can replace it.*
