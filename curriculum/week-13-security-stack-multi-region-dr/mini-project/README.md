# Mini-Project — The Security + DR Foundation (the Capstone Build Begins)

> Deliver the **capstone's Security and DR pillars** as one CDK (TypeScript) app that deploys from zero: KMS multi-Region CMKs with proper key policies, Secrets Manager with rotation, the GuardDuty/Security Hub/Macie/Inspector detective stack, a WAF web ACL, **and** a second-Region DR footprint — DynamoDB Global Tables, an Aurora Global Database, S3 CRR (decryptable via the multi-Region key), and Route 53 health-checked failover — with a **proven, measured RTO and RPO**. **This is not a throwaway lab. The syllabus states the capstone build begins this week; this layer is imported directly into the capstone monorepo in Weeks 14–15.**

This is the week's capstone-feeder, and it is the most consequential mini-project in the course so far, because everything before it produced *features* and this produces the *foundation those features sit on*. When you reach Week 14 (FinOps + edge) and Week 15 (capstone defense + chaos drill), you will `git submodule`/import this stack, not rebuild it. The acceptance bar is therefore higher than a lab: the IaC must be clean enough, and the failover proven enough, to defend in a Week-15 oral with two peer reviewers and a lead reviewer reading your code.

**Estimated time:** ~7.5 hours (Thursday spill-over, Friday, Saturday in the suggested schedule). Capstone weeks reshape the cadence around the build, so this is heavier than earlier weeks' mini-projects.

---

## How this compounds

The syllabus is explicit that Week 13 is where the capstone begins, and this mini-project is the first brick:

- It **becomes the capstone's `Security` pillar.** The capstone spec requires "GuardDuty, Security Hub, Macie on the lake bucket, Inspector on ECR & EKS. KMS-CMK encryption everywhere. Secrets Manager. WAF managed rules + a custom rate-limit rule." This is that pillar, built once, here.
- It **becomes the capstone's `DR` pillar.** The capstone spec requires "DynamoDB Global Tables. Aurora cross-region read replica. S3 CRR on the lake bucket. Route 53 health-checked failover. **Document RTO and RPO targets and prove them.**" This is that pillar — and the "prove them" clause is satisfied by the Friday drill, whose `DRILL.md` you carry forward.
- It **imports the Week-11 lake and the Week-8/9 data tiers.** The S3 CRR replicates the Week-11 data-lake bucket; the Global Tables make the Week-9 single-table multi-region; the Aurora Global Database extends the Week-8 cluster. You are not building new data — you are making the data you already have *survivable*.

So when Week 15's chaos drill says "kill one AZ's worth of EKS nodes and the Aurora writer; measure recovery" and "prove your RTO/RPO," the answer comes from this stack and this week's `DRILL.md`. Build it to keep, and build it clean.

---

## What you will build

A CDK (TypeScript) app with four stacks, one of which is **mirrored in Python** to honor the course's TS-primary / one-stack-in-Python convention (the capstone spec calls for "one stack in Python"):

```
   ┌──────────── CryptoStack (TS) ─────────────┐
   │  Multi-Region CMK (primary, us-east-1)     │
   │    + replica (us-west-2), rotation on       │
   │    key policy: admins != users              │
   │  Secrets Manager secret + rotation schedule │
   └───────────────────┬─────────────────────────┘
                        │ key ARNs consumed by every other stack
   ┌──────────── SecurityStack (Python) ───────┐   ← the one Python stack
   │  GuardDuty detector (S3 + EKS data sources)│
   │  Security Hub + FSBP standard              │
   │  Macie (scoped discovery job def)          │
   │  Inspector (ECR scanning enabled)          │
   │  EventBridge rule: finding -> SNS topic    │
   └───────────────────┬─────────────────────────┘
                        │
   ┌──────────── EdgeStack (TS) ───────────────┐
   │  WAF web ACL: AWS managed common rules     │
   │    + custom rate-based rule (block > N/5m) │
   │  (attached to the capstone CloudFront/ALB) │
   └───────────────────┬─────────────────────────┘
                        │
   ┌──────────── DrStack (TS) ─────────────────┐
   │  DynamoDB TableV2 with us-west-2 replica   │
   │    encrypted by the multi-Region CMK        │
   │  Aurora Global Database (primary+secondary) │
   │  S3 lake bucket CRR -> us-west-2 (replica   │
   │    re-encrypted with the replica CMK)       │
   │  Route 53 health check + failover records   │
   └─────────────────────────────────────────────┘
```

The Friday drill (`challenges/challenge-01`) exercises `DrStack` end to end and produces the `DRILL.md` that proves the RTO/RPO. The mini-project is the IaC that makes the drill reproducible.

---

## Required architecture

### Security half

- **KMS.** A multi-Region CMK (primary + replica) with **rotation enabled** and a key policy that **separates administrators from users** (no single principal both administers and uses the key). Every encrypted resource in the stack uses a CMK, never the default `aws/<service>` key.
- **Secrets Manager.** At least one secret (the Aurora app credential) generated at deploy time (never hard-coded in source), encrypted with the CMK, with an **automatic rotation schedule** configured.
- **Detective stack.** GuardDuty enabled with S3 and Kubernetes data sources; Security Hub enabled with the FSBP standard; Macie with a discovery job definition **scoped to a sample prefix** of the lake (not the whole lake); Inspector enabled for ECR. A finding-routing path (EventBridge rule → SNS) so findings are not just sitting in a console.
- **WAF.** A web ACL with the AWS managed common rule set **and** a custom rate-based rule, ready to attach to the capstone's CloudFront distribution or ALB.

### DR half

- **DynamoDB Global Table.** A `TableV2` with a `us-west-2` replica, encrypted with the multi-Region CMK in each Region. (Streams must be on for replication.)
- **Aurora Global Database.** The Week-8 cluster joined into a global cluster with a read-only secondary in `us-west-2`. (This is the warm-standby cost — document it.)
- **S3 CRR.** The Week-11 lake bucket replicating to a `us-west-2` destination bucket, with **`replicaKmsKeyId` pointing at the replica CMK** so the replicated objects are decryptable in the DR Region. Versioning on both buckets; a correctly scoped replication role.
- **Route 53 failover.** A health check on the primary endpoint and `PRIMARY`/`SECONDARY` failover records with a **low TTL**, ready for the drill.

### Cross-cutting

- **Tags.** Every resource tagged `team`, `service`, `environment` — the capstone's FinOps requirement starts here and Week 14 builds the cost dashboard on these tags.
- **One-command deploy/destroy.** `cdk deploy --all` from zero; `cdk destroy --all` leaves nothing billing — *critically* including the Aurora Global secondary and the DynamoDB replica, which are the expensive warm-standby line items.

---

## Rules

- **CDK (TypeScript) is the source of truth, with `SecurityStack` in Python.** You may use the CLI/boto3 to *run* the Macie discovery job and the Aurora global-cluster join, but every persistent resource is in IaC so the capstone can import it. One stack in Python satisfies the capstone's polyglot-IaC requirement; pick `SecurityStack` because its L1 GuardDuty/Security Hub constructs read cleanly in either language.
- **CMKs everywhere; no default keys for data that matters.** A reviewer should find no `aws/s3` or `aws/rds` key protecting capstone data.
- **The key policy must separate admin from usage.** A key policy where one role both administers and uses the key fails the review, the same way `Resource: "*"` fails a Week-2 IAM review.
- **The S3 CRR must be decryptable in the DR Region.** Prove it: replicate an object, then `aws s3 cp` it *from the DR bucket* and confirm it decrypts. A replica you cannot read is the most common silent DR failure.
- **The DR footprint must be torn down on `cdk destroy --all`.** Because the Aurora secondary and DynamoDB replica bill like a second production stack, your README must document the deploy-drill-destroy loop, and `cdk destroy --all` must actually remove them. Demonstrate it.
- **RTO and RPO must be proven, not asserted.** The `DRILL.md` from the Friday challenge — with measured numbers — is part of this submission.
- **Cost report required.** Real dollar figures, not estimates-from-memory, especially the warm-standby premium.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c19-week-13-security-dr-<yourhandle>`.
- [ ] `npx cdk deploy --all` from a clean account stands up the crypto, security, edge, and DR stacks with no manual console steps (other than the documented Macie-job run, the Aurora global-cluster join, and any org delegated-admin enablement).
- [ ] A multi-Region CMK exists with rotation on and a key policy that separates admin from users; the synthesized template contains no hard-coded secret values.
- [ ] A Secrets Manager secret exists, CMK-encrypted, with a rotation schedule.
- [ ] GuardDuty, Security Hub (FSBP), Macie (scoped job), and Inspector (ECR) are enabled, and a finding-routing rule exists. A committed `finding-disposition.md` triages every Critical/High.
- [ ] A WAF web ACL with managed common rules + a custom rate-based rule exists; a `curl` flood produces `403`s and a `RateLimit` CloudWatch metric (show it).
- [ ] A DynamoDB Global Table with a `us-west-2` replica, CMK-encrypted in both Regions.
- [ ] An Aurora Global Database with a `us-west-2` secondary.
- [ ] S3 CRR on the lake bucket to `us-west-2`, with the replica **decryptable** (prove a round-trip read from the DR bucket).
- [ ] Route 53 health-checked failover records with a low TTL.
- [ ] A `DRILL.md` (from Challenge 1) with **measured** RTO and RPO vs targets, the RTO breakdown, and the runbook.
- [ ] Every resource tagged `team`, `service`, `environment`.
- [ ] `npx cdk destroy --all` removes everything, including the Aurora secondary and the DynamoDB replica. Prove nothing remains: `aws rds describe-db-clusters` and `aws dynamodb describe-table` show no DR resources.
- [ ] A `COSTREPORT.md` with the figures below.
- [ ] A `README.md` with: one-paragraph description, exact from-clone setup commands, the deploy-drill-destroy loop, and the proof-of-decryptable-replica step.

---

## The cost report

`COSTREPORT.md` must contain, with real numbers pulled from the pricing pages (cite the date you pulled them):

1. **The warm-standby premium.** The monthly cost of the Aurora Global secondary instance + the replicated DynamoDB write units + the second-Region S3 storage — i.e. **what DR costs you every month whether or not disaster strikes.** This is the headline number of the whole week.
2. **Detective stack.** GuardDuty per-GB analysis estimate for your account's event volume, Macie per-GB for the scoped job, Inspector per-image/-instance. The recurring detective bill.
3. **KMS.** Per-CMK-month (primary + replica = two keys) plus the API-call estimate from your encrypt/decrypt volume.
4. **Shield reasoning (no spend).** A paragraph: at what revenue/downtime cost would Shield Advanced's $3,000/month become worth it for this workload? You do **not** buy it; you reason about it.
5. **RTO/RPO achieved.** Pulled from `DRILL.md`: the measured RTO and RPO vs the targets, with the RTO broken into detection (health-check time) + propagation (DNS TTL) + DR warm-up.
6. **Idle/destroyed bill.** What this stack costs per day at warm standby vs after `cdk destroy --all` — the number that explains why you destroy the DR footprint between drills.

---

## Suggested build order

1. **Thursday spill-over (1 h).** Scaffold the CDK app (`cdk init app --language typescript`), build `CryptoStack` (the multi-Region CMK + rotated secret, importing your Exercise-2 key shape), deploy it. This stack's key ARNs feed everything else.
2. **Friday morning (1 h).** Write `SecurityStack` **in Python** (`cdk init` a sibling Python app or use `aws-cdk-lib`'s Python bindings): GuardDuty detector, Security Hub + FSBP, Macie scoped job def, Inspector ECR, and the finding → SNS EventBridge rule. Deploy; confirm findings flow (you already triaged them in Exercise 1).
3. **Friday afternoon (1 h).** Write `EdgeStack` (the WAF web ACL with managed rules + rate-based rule). Run the Friday drill against `DrStack` and capture `DRILL.md`.
4. **Saturday morning (2.5 h).** Build `DrStack`: the DynamoDB Global Table, the Aurora global-cluster join, the S3 CRR with the replica KMS key, and the Route 53 failover records. Prove the decryptable replica round-trip.
5. **Saturday afternoon (2 h).** Write `COSTREPORT.md` and `README.md`. Run the full deploy-drill-destroy loop once, clean, and confirm nothing is left billing (especially the Aurora secondary).

---

## A worked snippet — the encrypted Global Table in CDK

So you are not staring at a blank file, here is the multi-Region, CMK-encrypted Global Table — the resource the capstone's transactional tier imports. The key idea is that each Region's replica is encrypted with *that Region's* replica of the multi-Region key, which is exactly why Exercise 2's cross-Region-decryptable key matters here.

```typescript
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as kms from 'aws-cdk-lib/aws-kms';

// The primary-Region key (created in CryptoStack) and the ARN of its us-west-2 replica.
const primaryKey = kms.Key.fromKeyArn(this, 'PrimaryKey', primaryKeyArn);

const table = new dynamodb.TableV2(this, 'AppTable', {
  tableName: 'capstone-app',
  partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
  billing: dynamodb.Billing.onDemand(),
  dynamoStream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,  // required for replication
  // Encrypt the primary with the primary CMK and each replica with its Region's replica key.
  encryption: dynamodb.TableEncryptionV2.customerManagedKey(primaryKey, {
    'us-west-2': replicaKeyArnUsWest2,
  }),
  replicas: [{ region: 'us-west-2' }],
  pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
});

// Tag for FinOps (Week 14 builds the cost dashboard on these).
cdk.Tags.of(table).add('team', 'platform');
cdk.Tags.of(table).add('service', 'capstone');
cdk.Tags.of(table).add('environment', 'prod');
```

The `encryption` map is the load-bearing part: pass the replica Region's key ARN so the `us-west-2` replica is encrypted with the replica CMK that shares key material with the primary. Omit it and DynamoDB falls back to an AWS-managed key per Region — which "works" but fails the "CMK everywhere" rule and, more importantly, means you do not control the key the DR copy depends on.

---

## A second worked snippet — the S3 CRR replication role

The replication role is the part of S3 CRR people get wrong, and getting it wrong means the replica silently never decrypts. It needs read on the source, write on the destination, and **KMS decrypt on the source key + KMS encrypt on the destination (replica) key**:

```typescript
const replicationRole = new iam.Role(this, 'CrrRole', {
  assumedBy: new iam.ServicePrincipal('s3.amazonaws.com'),
});
replicationRole.addToPolicy(new iam.PolicyStatement({
  actions: ['s3:GetReplicationConfiguration', 's3:ListBucket',
            's3:GetObjectVersionForReplication', 's3:GetObjectVersionAcl'],
  resources: [lakeBucket.bucketArn, `${lakeBucket.bucketArn}/*`],
}));
replicationRole.addToPolicy(new iam.PolicyStatement({
  actions: ['s3:ReplicateObject', 's3:ReplicateDelete', 's3:ReplicateTags'],
  resources: [`${destBucketArn}/*`],
}));
replicationRole.addToPolicy(new iam.PolicyStatement({
  actions: ['kms:Decrypt'],
  resources: [primaryKeyArn],                       // decrypt at the source
  conditions: { StringLike: { 'kms:ViaService': 's3.us-east-1.amazonaws.com' } },
}));
replicationRole.addToPolicy(new iam.PolicyStatement({
  actions: ['kms:Encrypt'],
  resources: [replicaKeyArnUsWest2],                // re-encrypt at the destination
  conditions: { StringLike: { 'kms:ViaService': 's3.us-west-2.amazonaws.com' } },
}));
```

Note both KMS statements scoped with `kms:ViaService` — the replication role may decrypt the source key *via S3* and encrypt the destination key *via S3*, nothing else. That is Lecture 1's least-privilege-on-the-path, applied to the exact place DR depends on it.

---

## Submission

Push the repo. In your engineering journal, answer: *Your `DRILL.md` reports a real RTO and RPO. If a target was missed (e.g. the RTO floor of ~90s health-check detection + 60s TTL exceeded a 60s RTO target, or Aurora's ~1.1s exceeded a ≤1s RPO target), what is the cheapest change that would close the gap — and is it worth it?* The honest answer (faster detection means a tighter health-check interval and a more sensitive failover, which trades RTO against false-positive failovers; a tighter Aurora RPO means active-active write-forwarding, which is far more expensive) is the point. Knowing the *cost* of each nine of recovery, and being able to say it about your own architecture, is the senior skill this week certifies.

---

## What this sets up

Week 14 (FinOps + edge) attaches CloudFront + a Lambda@Edge tenant-routing function in front of this stack's WAF, and builds a QuickSight cost dashboard on the `team`/`service`/`environment` tags you applied here — including the warm-standby premium you documented. Week 15 (capstone defense + chaos drill) imports this whole layer and runs the chaos drill against it: an AZ failover, a DynamoDB throttle, and your bonus drill, with this week's `DRILL.md` as the baseline. Do not delete the repo when the week ends — it is the foundation of the thing you defend.
