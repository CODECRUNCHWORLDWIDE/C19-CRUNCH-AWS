# Week 8 — Exercises

Three exercises that build on each other. By the end you have a production-shaped Aurora PostgreSQL cluster, a passwordless connection path through RDS Proxy, and a failover-timing harness you wrote yourself. Do them **in order** — Exercise 2 connects to the cluster from Exercise 1, and Exercise 3 fails over the same cluster.

Every exercise this week ends with a **teardown step**. Aurora bills while it idles. If your `cdk destroy` leaves an orphaned cluster or a retained snapshot, you are not done.

## Index

1. **[Exercise 1 — Stand up an Aurora cluster via CDK](exercise-01-aurora-cluster-cdk.md)** — a guided exercise: write a TypeScript CDK stack that provisions an Aurora PostgreSQL cluster (writer + 2 readers across 3 AZs), KMS-encrypted, TLS-enforced, with a custom cluster parameter group and Performance Insights. Deploy it, inspect the endpoints, tear it down. (~120 min)
2. **[Exercise 2 — RDS Proxy + IAM auth from an IRSA pod, then pgbench](exercise-02-rds-proxy-iam-pgbench.ts)** — a runnable CDK (TypeScript) stack that adds an RDS Proxy with IAM authentication in front of the Exercise-1 cluster, wires an IRSA role for an EKS service account, and includes the Kubernetes manifests and the `pgbench` commands to connect passwordlessly and benchmark the writer and reader endpoints. (~120 min)
3. **[Exercise 3 — Force a failover and measure recovery time](exercise-03-failover-timer.py)** — a runnable Python harness that opens a write probe and a read probe against the cluster, triggers `failover-db-cluster`, and measures **write recovery time** and **read recovery time** separately, printing a timeline you paste into your mini-project failover report. (~60 min)

## How to work the exercises

- **Type the CDK yourself.** Do not clone a finished repo. The muscle memory of `new rds.DatabaseCluster(...)` with the right props is the point.
- **Deploy to your `dev` account**, the one you `cdk bootstrap`-ed in Week 3, inside the VPC with isolated subnets and VPC endpoints from Week 4.
- **Watch the bill.** A writer + 2 readers on `db.r7g.large` is ~$0.78/hour ≈ $19/day. Set your Week-1 Budgets alert and `cdk destroy` every evening unless you are mid-failover-test.
- If you get stuck for more than 15 minutes, read the inline hints / `<details>` blocks. Then read the relevant `resources.md` doc.
- Each exercise ends green only when (a) the artifact works **and** (b) `cdk destroy` (or the CLI teardown) removes every billable resource cleanly.

## Prerequisites checklist

Before you start Exercise 1, confirm:

```bash
node --version      # >= 20
cdk --version       # >= 2.150.0
aws --version       # >= 2.17
psql --version      # >= 16
pgbench --version   # >= 16
kubectl version --client   # any recent
```

And that your `dev` VPC exists with isolated subnets and a security group you can attach the database to. If Week 4's VPC was torn down, the Exercise-1 stack includes a minimal VPC fallback so you are not blocked.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-08` to compare.
