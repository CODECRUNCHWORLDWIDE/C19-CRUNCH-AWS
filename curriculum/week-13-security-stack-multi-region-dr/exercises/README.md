# Week 13 — Exercises

Three exercises that build the week's two halves. The first stands up the security baseline (detective stack); the second and third build the encryption and data primitives that the DR drill depends on. Do them in order — Exercise 2's multi-Region KMS key is used by Exercise 3's encrypted Global Table and by the mini-project's S3 CRR, and the Friday challenge assumes all three are done.

## Index

1. **[Exercise 1 — Security baseline](exercise-01-security-baseline.md)** — enable GuardDuty, Security Hub, Macie, and Inspector; generate a finding; and triage every Critical/High to a documented disposition. Read your first real findings. (~90 min)
2. **[Exercise 2 — Multi-region KMS + Secrets rotation](exercise-02-kms-multiregion-secrets.py)** — create a multi-Region CMK (primary + replica) and a Secrets Manager secret with automatic rotation, and prove both with boto3. This key is the bridge to encrypted cross-Region replication. (~75 min)
3. **[Exercise 3 — DynamoDB Global Tables + Aurora Global](exercise-03-global-tables-aurora-global.py)** — make a DynamoDB table a Global Table and join an Aurora cluster into a Global Database, then measure the cross-Region replication lag (your RPO floor). (~90 min)

## Before you start

- **AWS CLI v2** configured with a profile that can use GuardDuty, Security Hub, Macie, Inspector, KMS, Secrets Manager, DynamoDB, and RDS. `aws --version` should report `aws-cli/2.x`.
- **Python 3.12+** with the per-exercise `requirements.txt`. A clean virtualenv per exercise keeps deps isolated.
- **Two Regions you'll stick with all week.** `us-east-1` (primary) and `us-west-2` (DR) are assumed in the examples; if you use others, change them everywhere consistently.
- **GuardDuty/Security Hub/Inspector enabled early.** They need telemetry history to produce findings. Turn them on Monday or Tuesday morning so they have something to show by Friday.

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the commands and code yourself.** Copy-pasting AWS CLI calls teaches you nothing; typing them builds the muscle memory you need in an incident — and a Region failover *is* an incident.
- Run it. Read the output. When GuardDuty prints a finding or `dig` shows the DNS flip, stop and ask *why* it is what it is.
- Tear down what costs money when you finish each session. The big ones this week: a running Aurora Global secondary, a Macie job over too much data, and an Inspector scan of a large registry. Empty and delete lab buckets, and do not leave a multi-Region warm standby running over the weekend — it bills like a second production stack.
- Every exercise ends with a checkable artifact: a finding-disposition table, a successful cross-Region decrypt, or a measured replication-lag number. If you don't have it, you're not done.

## Cost note

- **Exercise 1** is mostly free to *enable* (GuardDuty/Security Hub have a 30-day trial; the controls cost little). The lines that bite are **Macie** (per GB inspected — scope it to a small sample prefix, never the whole lake) and **Inspector** (per image/instance scanned — point it at a handful of images). Do not point Macie at a real multi-TB lake in the lab.
- **Exercise 2** costs cents: $1/month per CMK (prorated), a couple of secret-months, and a few KMS API calls.
- **Exercise 3** costs the most: an Aurora Global Database runs a **second-Region instance 24/7** while it exists (the warm-standby cost — dollars, not cents), plus replicated DynamoDB write units. **Delete the Aurora global cluster and the DynamoDB replicas the moment you finish measuring lag.** The exercise's last steps do it for you — do not skip them.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-13` to compare.
