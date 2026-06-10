# Challenge 1 — Benchmark `gp3` vs `io2` on a Synthetic Postgres Workload

**Time estimate:** ~3 hours (mostly waiting on benchmarks; ~45 min of hands-on).

## Problem statement

You are about to put a Postgres database on EC2-backed EBS (in Week 8 it becomes RDS, but here you control the raw volume so you can measure). Someone proposes `io2` Block Express "because databases need provisioned IOPS." Someone else says "`gp3` is the default for a reason, prove you need `io2`." Your job is to settle it with data.

Provision **two** EBS volumes on one EC2 instance: a `gp3` and an `io2`. Run an identical I/O workload against each — first raw block I/O with `fio`, then a real Postgres OLTP workload with `pgbench`. Capture **IOPS, throughput (MB/s), p50 latency, and p99 latency** for each. Then write a decision doc that says *which volume wins for which workload shape, and at what cost.*

This is open-ended on purpose. You decide the instance type, the volume sizes, the provisioned IOPS levels, and the `fio`/`pgbench` parameters — and you defend those choices in the writeup. There is no single right answer; there is a right *method*.

## Setup constraints

- One EC2 instance (`c7i.2xlarge` or `m7i.2xlarge` is a sane choice — enough EBS bandwidth to not bottleneck on the instance). Confirm the instance's EBS bandwidth ceiling so the *instance* is not your bottleneck instead of the volume.
- Two data volumes attached to that one instance:
  - **`gp3`**: 100 GiB, start at the 3,000 baseline IOPS / 125 MB/s, then a second run at provisioned 8,000 IOPS / 500 MB/s.
  - **`io2`**: 100 GiB, provisioned at (say) 32,000 IOPS. (Block Express is automatic at this size on a Nitro instance.)
- Both volumes KMS-encrypted (default EBS encryption on).
- Use SSM Session Manager, not SSH — no public IP, no key pairs.
- **Tear it all down the same day.** A 32,000-IOPS `io2` volume is not free to leave running.

## What to measure

For each volume and each configuration, capture from `fio`:

- **Random read IOPS** (`randread`, 4k blocks, queue depth 32).
- **Random write IOPS** (`randwrite`, 4k, QD32).
- **Mixed 70/30 read/write IOPS and p50/p99 latency** (the OLTP-shaped run).
- **Sequential throughput** (`read`/`write`, 1M blocks) in MB/s.

Then run `pgbench` (TPC-B-like) against a Postgres instance whose data directory lives on each volume, and capture:

- **TPS (transactions per second)** at a fixed client/thread count.
- **Mean and p99 latency** per transaction.

## Suggested method

### 1. Provision (CDK or CLI; CLI shown for speed)

```bash
# Default-encrypt EBS in this region.
aws ec2 enable-ebs-encryption-by-default

# Launch the instance (fill in your subnet, SG, and the SSM instance profile).
IID=$(aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --instance-type c7i.2xlarge \
  --iam-instance-profile Name=SSMInstanceProfile \
  --subnet-id subnet-xxxxxxxx \
  --security-group-ids sg-xxxxxxxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=team,Value=platform},{Key=service,Value=ebs-bench},{Key=environment,Value=dev}]' \
  --query 'Instances[0].InstanceId' --output text)
echo "$IID"

AZ=$(aws ec2 describe-instances --instance-ids "$IID" \
  --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' --output text)

# gp3: 100 GiB, 8000 IOPS, 500 MB/s.
GP3=$(aws ec2 create-volume --availability-zone "$AZ" --size 100 \
  --volume-type gp3 --iops 8000 --throughput 500 --encrypted \
  --query VolumeId --output text)

# io2: 100 GiB, 32000 IOPS (Block Express on a Nitro instance at this ratio).
IO2=$(aws ec2 create-volume --availability-zone "$AZ" --size 100 \
  --volume-type io2 --iops 32000 --encrypted \
  --query VolumeId --output text)

aws ec2 wait volume-available --volume-ids "$GP3" "$IO2"
aws ec2 attach-volume --volume-id "$GP3" --instance-id "$IID" --device /dev/sdf
aws ec2 attach-volume --volume-id "$IO2" --instance-id "$IID" --device /dev/sdg
```

### 2. Prepare filesystems (inside an SSM session)

```bash
aws ssm start-session --target "$IID"
# Inside the session:
sudo dnf install -y fio postgresql15 postgresql15-server
# Identify the NVMe device names (EBS shows up as /dev/nvme1n1, /dev/nvme2n1, ...).
lsblk
sudo mkfs.xfs /dev/nvme1n1   # gp3
sudo mkfs.xfs /dev/nvme2n1   # io2
sudo mkdir -p /mnt/gp3 /mnt/io2
sudo mount /dev/nvme1n1 /mnt/gp3
sudo mount /dev/nvme2n1 /mnt/io2
```

### 3. The `fio` runs

Use a single reusable job. Run it once per mount, swapping `--directory`.

```bash
# Random read, 4k, QD32, 60s, direct I/O (bypass page cache for honest numbers).
sudo fio --name=randread --directory=/mnt/gp3 --rw=randread --bs=4k \
  --iodepth=32 --numjobs=4 --size=4G --runtime=60 --time_based \
  --direct=1 --group_reporting

# Mixed 70/30 (OLTP-shaped) with latency percentiles.
sudo fio --name=mix7030 --directory=/mnt/gp3 --rw=randrw --rwmixread=70 \
  --bs=8k --iodepth=32 --numjobs=4 --size=4G --runtime=60 --time_based \
  --direct=1 --group_reporting --percentile_list=50:95:99

# Sequential throughput.
sudo fio --name=seqread --directory=/mnt/gp3 --rw=read --bs=1M \
  --iodepth=8 --numjobs=2 --size=8G --runtime=60 --time_based \
  --direct=1 --group_reporting
```

Repeat every command with `--directory=/mnt/io2`. Record `iops`, `bw`, and `clat` p50/p99 from each run. (`fio` prints `clat percentiles` when you pass `--percentile_list`.)

### 4. The `pgbench` runs

Put a Postgres data dir on each volume and benchmark a TPC-B-like workload.

```bash
# Initialize a cluster whose data lives on gp3.
sudo -u postgres initdb -D /mnt/gp3/pgdata
sudo -u postgres pg_ctl -D /mnt/gp3/pgdata -l /tmp/gp3.log start
sudo -u postgres createdb bench
sudo -u postgres pgbench -i -s 50 bench          # scale 50 ~ 750MB dataset
# Run: 8 clients, 4 threads, 120 seconds, report latency.
sudo -u postgres pgbench -c 8 -j 4 -T 120 -P 10 -r bench
```

Stop the cluster, repeat the `initdb` / `pg_ctl` / `pgbench` sequence with `-D /mnt/io2/pgdata` on the `io2` mount, and record **TPS**, **latency average**, and the **p99** from the `-r` per-statement report.

### 5. The cost math

Pull the per-volume monthly cost from the current EBS pricing page and compute, for *your* configurations:

- `gp3` 100 GiB @ 8,000 IOPS, 500 MB/s = (100 GiB × $/GiB) + ((8000 − 3000) × $/provisioned-IOPS) + ((500 − 125) × $/provisioned-MBps).
- `io2` 100 GiB @ 32,000 IOPS = (100 GiB × $/GiB) + tiered provisioned-IOPS cost (io2 IOPS price has tiers — the first 32k is one rate, above that is cheaper).

Express the result as **dollars per month** *and* as **dollars per 1,000 sustained IOPS delivered** (cost ÷ measured IOPS). That second number is the one that wins arguments.

## Acceptance criteria

- [ ] Both volumes provisioned, KMS-encrypted, attached to one instance, benchmarked, and **torn down the same day**.
- [ ] A results table with, for each volume/config: random-read IOPS, mixed-70/30 IOPS, p50 and p99 latency, and sequential throughput (MB/s) — from `fio`.
- [ ] A `pgbench` table with TPS, mean latency, and p99 latency for each volume.
- [ ] A cost table: $/month for each config, and $/1,000 sustained IOPS.
- [ ] A **decision doc** (`gp3-vs-io2-decision.md`, ~400–600 words) that answers:
  - For a small OLTP database (a few thousand IOPS, p99 latency target ~10 ms), which wins, and why?
  - For a latency-critical database (sub-millisecond p99 requirement, tens of thousands of IOPS), which wins, and why?
  - For a write-heavy log/append workload dominated by sequential throughput, which wins?
  - At what IOPS level does `io2` become *cost*-competitive with `gp3`, given your measured numbers?
  - The one-sentence recommendation you would put in a design review.
- [ ] The raw `fio` JSON output (`--output-format=json`) and the `pgbench` logs committed alongside the writeup, so the numbers are reproducible.

## Stretch

- Add a `gp3` run at the **maximum** 16,000 IOPS / 1,000 MB/s and see how close it gets to `io2` at a fraction of the price. This is the crux of the cost argument.
- Test **`io2` Multi-Attach**: attach the `io2` volume to a second instance and observe that the block device is shared (you need a cluster-aware filesystem — note what breaks if you naively `mount` xfs on both).
- Re-run the mixed workload with the page cache **enabled** (`--direct=0`) and explain why the IOPS numbers jump and why that is misleading for sizing a database.
- Snapshot the `io2` volume, restore it with **Fast Snapshot Restore** on and off, and measure first-touch latency difference.

## Why this matters

Provisioned-IOPS volumes are one of the easiest places to overspend on AWS — `io2` at 64,000 IOPS costs real money every hour whether or not the workload uses it. The skill of *measuring the workload shape and matching the cheapest volume that meets the SLO* is exactly what FinOps week (Week 14) formalizes, and it is what separates "we bought the expensive one to be safe" from "we right-sized it and saved 60%." The decision doc you write here is a template you will reuse for RDS storage in Week 8 and for the capstone cost report in Week 15.

## Submission

Commit `gp3-vs-io2-decision.md`, the `fio` JSON, and the `pgbench` logs under `challenges/challenge-01/` in your Week 6 repo. Confirm the EC2 instance and both volumes are gone (`aws ec2 describe-volumes` shows them deleted). Post the decision doc's one-sentence recommendation in your cohort tracker.
