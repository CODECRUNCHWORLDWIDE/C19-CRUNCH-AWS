# Week 4 Homework

Six problems that revisit the week's topics and push them slightly further than the exercises did. The full set should take about **6 hours**. Work in your Week 4 Git repository (`c19-week-04-<yourhandle>`) so each problem produces at least one commit you can point to later. Several problems create billable resources — **`cdk destroy` (or `tofu destroy`) every night**, and keep an eye on the NAT Gateway line of Cost Explorer.

Each problem includes:

- A short **problem statement**.
- **Deliverables** — the concrete artifacts you commit.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

A grading **rubric** is at the bottom.

---

## Problem 1 — CIDR plan for a six-VPC estate

**Problem statement.** You are the network owner for an organization with three environments (`dev`, `stage`, `prod`) across two regions (`us-east-1`, `eu-west-1`) — six VPCs total. Design a non-overlapping CIDR plan such that any two VPCs could later be joined by a Transit Gateway without re-addressing. For each VPC, carve the `/16` into three subnet tiers (public, private, isolated) across three AZs as `/20` subnets, and write out the resulting subnet CIDRs for **one** of the six VPCs in full.

**Deliverables.** A file `notes/cidr-plan.md` containing:

1. A table mapping each of the six VPCs to its `/16`.
2. The nine `/20` subnet CIDRs for the `dev us-east-1` VPC (3 AZs × 3 tiers).
3. One sentence explaining why none of the six `/16` ranges overlap.

**Acceptance criteria.**

- All six VPC CIDRs are inside RFC 1918 space and do not overlap each other.
- The nine subnet CIDRs are all `/20`, all inside the `dev us-east-1` `/16`, and do not overlap each other.
- Committed.

**Hint.** A `/16` holds sixteen `/20`s. `10.0.0.0/16` → subnets at `10.0.0.0/20`, `10.0.16.0/20`, `10.0.32.0/20`, … (each `/20` is 4,096 addresses, so the third octet advances by 16). Reserve a contiguous block of `/16`s per region: `10.0–10.2` for us-east-1, `10.10–10.12` for eu-west-1, leaving room between.

**Estimated time.** 30 minutes.

---

## Problem 2 — Read the route tables and classify the tiers

**Problem statement.** Deploy the Exercise 1 + Exercise 2 stacks (VPC with one NAT and the full endpoint set). Then, using **only the AWS CLI**, dump every route table in the VPC and, for each, state which tier it serves (public / private / isolated) and the evidence (which target the `0.0.0.0/0` route points at, or that there is none; whether an S3 prefix-list route is present).

**Deliverables.** A file `notes/route-tables.md` with one section per route table containing the raw `aws ec2 describe-route-tables` JSON snippet for that table and your one-line classification with evidence.

**Acceptance criteria.**

- Every route table in the VPC is accounted for.
- The public tier's table shows `0.0.0.0/0 → igw-…`.
- The private tier's table shows `0.0.0.0/0 → nat-…`.
- The isolated tier's table shows **no** `0.0.0.0/0` route, plus the S3 prefix-list route (`pl-… → vpce-…`) from the gateway endpoint.
- Committed.

**Hint.**

```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'RouteTables[].{Id:RouteTableId,Routes:Routes[].{Dest:DestinationCidrBlock,Pfx:DestinationPrefixListId,GW:GatewayId,NAT:NatGatewayId,VPCE:VpcEndpointId}}'
```

Find `$VPC_ID` with `aws ec2 describe-vpcs --filters Name=tag:Name,Values='*Vpc*'`.

**Estimated time.** 45 minutes.

---

## Problem 3 — The deliberately-broken endpoint set (zero-NAT, the hard way)

**Problem statement.** Reproduce the most instructive failure of the week. Starting from the Exercise 3 stack, **remove the S3 gateway endpoint**, redeploy, `aws ssm start-session` into the private instance, and `docker pull` an image from ECR. Capture the NAT Gateway `BytesOutToDestination` metric showing non-zero bytes during the pull. Then add the S3 gateway endpoint back, redeploy, repeat the pull, and capture the metric showing **zero**. Write up the before/after.

**Deliverables.** A file `notes/zero-nat-proof.md` containing:

1. The two `get-metric-statistics` command outputs (broken → bytes; fixed → zero).
2. A two-sentence explanation of *why* the bytes appeared and where they went when the endpoint returned.

**Acceptance criteria.**

- The "broken" run shows a non-zero `Sum` for `BytesOutToDestination` correlated with the pull.
- The "fixed" run shows `0` (or only background-chatter bytes) for the same operation.
- Your explanation correctly names ECR's dependency on S3 for image layers.
- The NAT Gateway and instance are **torn down** afterward (note the teardown command in the file).
- Committed.

**Hint.** Run the pull, then immediately query a 15-minute window: `--start-time "$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ)"`. Use a non-trivial image (a few hundred MB) so the difference is unmistakable. On Linux, `date -u -d '-15 min'` replaces the macOS `-v-15M`.

**Estimated time.** 1 hour.

---

## Problem 4 — Security Group reference, not CIDR

**Problem statement.** Write a small CDK stack (TS or Python) that creates two Security Groups — `web` and `db` — and wires them so that the `db` group allows inbound Postgres (TCP 5432) **only from the `web` security group**, referenced by group ID, *not* by CIDR. Add an inbound HTTPS (443) rule on `web` from `0.0.0.0/0`. Synthesize and confirm the generated `AWS::EC2::SecurityGroupIngress` for the db rule uses `SourceSecurityGroupId`, not `CidrIp`.

**Deliverables.** The CDK stack under `homework/p4-sg-reference/` and a file `homework/p4-sg-reference/SYNTH.md` pasting the two relevant ingress resources from `cdk synth`.

**Acceptance criteria.**

- `cdk synth` succeeds.
- The db ingress rule references the web SG by `SourceSecurityGroupId` (no CIDR for that rule).
- The web ingress rule for 443 uses `CidrIp: 0.0.0.0/0`.
- One sentence in `SYNTH.md` explaining why SG-to-SG references are preferable to CIDR for intra-VPC tiers.
- Committed.

**Hint.** In CDK: `dbSg.addIngressRule(webSg, ec2.Port.tcp(5432), 'web tier to postgres')`. Passing a Security Group (not a `Peer.ipv4(...)`) is what produces the `SourceSecurityGroupId` form. SG references survive IP changes and autoscaling; CIDR rules go stale.

**Estimated time.** 45 minutes.

---

## Problem 5 — Weighted DNS and a failover health check (on paper + CDK)

**Problem statement.** In a CDK stack (TS or Python) targeting a hosted zone you control (or a dummy zone created in the stack), define **two** alias records for `api.<zone>`: a primary with a **failover** routing policy and a Route 53 **health check** against the primary's endpoint, and a secondary failover record pointing at a static maintenance page (an S3 website or a second CloudFront distribution). Separately, in `notes/weighted-vs-failover.md`, contrast when you would reach for weighted vs failover routing.

**Deliverables.** The CDK stack under `homework/p5-dns-failover/` and the note `notes/weighted-vs-failover.md` (150–250 words).

**Acceptance criteria.**

- `cdk synth` produces a primary `AWS::Route53::RecordSet` with `Failover: PRIMARY` plus an `AWS::Route53::HealthCheck`, and a secondary with `Failover: SECONDARY`.
- The note correctly states that weighted is for traffic splitting (blue/green, canary) and failover is for active/passive DR, and that a failover record without a health check never fails over.
- Committed.

**Hint.** CDK's `ARecord` accepts `failover` via the lower-level `CfnRecordSet`, or use `route53.ARecord` with `setIdentifier` and a `region`/`failover` extension. The cleanest path for this is `new route53.CfnRecordSet(...)` with `failover: 'PRIMARY'` and `healthCheckId`. You do **not** need to actually own a domain to `cdk synth`; you only need a real zone to `cdk deploy`.

**Estimated time.** 1 hour 15 minutes.

---

## Problem 6 — Cost model + reflection

**Problem statement.** Build a one-page cost model for the network you ran this week, then reflect. The model compares three egress postures for a three-AZ VPC running 24/7 for a 30-day month, assuming 300 GB/month of AWS-service traffic (S3 + ECR) and 50 GB/month of genuine third-party-internet egress:

- **Posture A:** three NAT Gateways (one per AZ), no endpoints.
- **Posture B:** one NAT Gateway, plus S3/DynamoDB gateway endpoints and the interface-endpoint set in three AZs.
- **Posture C:** zero NAT Gateways (assume the 50 GB third-party traffic moves to IPv6 via an egress-only IGW), plus the same endpoints.

Use the list prices from Lecture 1 (NAT ~$0.045/hr + ~$0.045/GB; interface endpoint ~$0.01/hr/AZ + ~$0.01/GB; gateway endpoint and IGW free; assume 8 interface endpoints).

**Deliverables.** A file `notes/cost-model.md` with a table of the three postures' monthly totals (broken into hourly + data-processing components) and a 200–300 word reflection.

**Acceptance criteria.**

- Three posture totals computed with the per-hour and per-GB components shown separately.
- Posture B is meaningfully cheaper than Posture A; the note explains *why* (it moves 300 GB of AWS-service traffic off the metered NAT path onto free/cheap endpoints and drops two NAT Gateways).
- The reflection answers: which posture would you run in dev, which in prod, and the one thing this week changed about how you think about a VPC default.
- Committed.

**Hint.** NAT hourly for posture A: `3 × 730 × $0.045`. Interface-endpoint hourly for B/C: `8 endpoints × 3 AZs × 730 × $0.01`. Data on NAT is charged per GB *processed*; data on gateway endpoints is free. Don't forget the per-GB charge is separate from the per-hour charge — that's the whole trap.

**Estimated time.** 45 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 30 min |
| 2 | 45 min |
| 3 | 1 h 0 min |
| 4 | 45 min |
| 5 | 1 h 15 min |
| 6 | 45 min |
| **Total** | **~5 h 0 min** |

(The remaining hour of the week's homework budget is teardown discipline and re-reading the lecture sections you stumbled on.)

---

## Grading rubric

Total **100 points**. A pass is 70.

| Criterion | Points | What earns full marks |
|-----------|-------:|-----------------------|
| **CIDR discipline** (P1) | 15 | Six non-overlapping `/16`s; nine correct `/20` subnet CIDRs; overlap reasoning sound. |
| **Route-table literacy** (P2) | 15 | Every table classified with correct evidence; isolated tier shown to have no default route plus the S3 prefix-list route. |
| **Zero-NAT proof** (P3) | 20 | Before/after metrics captured correctly; explanation names the ECR→S3 layer dependency; resources torn down. |
| **SG-to-SG referencing** (P4) | 15 | db ingress uses `SourceSecurityGroupId`; web uses `CidrIp`; rationale correct. |
| **DNS policies** (P5) | 15 | Primary/secondary failover records + health check synthesized; weighted-vs-failover distinction correct. |
| **Cost model + reflection** (P6) | 15 | Three postures computed with split components; B shown cheaper with correct reasoning; reflection honest and specific. |
| **Hygiene (all)** | 5 | Every billable resource torn down; clean commits; no secrets or account IDs leaked in notes. |

**Automatic deductions.**

- −10 if any NAT Gateway, interface endpoint, or EC2 instance is left running after submission (check Cost Explorer the next morning — a climbing `NatGateway-Hours` line is the tell).
- −10 if any real account ID, access key, or private hosted-zone internal name is committed in plaintext.
- −5 if `cdk synth` fails on any CDK problem.

When you've finished all six, push your repo and open the [mini-project](./mini-project/README.md) — it fuses the VPC and the edge into the network foundation every later week reuses.
