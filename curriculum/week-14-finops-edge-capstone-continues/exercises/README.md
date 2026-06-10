# Week 14 — Exercises

Three exercises. The first two are the **FinOps** half — land and query the cost data, then read the optimization recommendations. The third is the **edge** half — put CloudFront with edge functions in front of an API origin. Do them in order; the mini-project and the challenge assume all three are done.

## Index

1. **[Exercise 1 — CUR → Athena → QuickSight by tag](exercise-01-cur-athena-quicksight-by-tag.md)** — create a Cost & Usage Report, land it in S3, catalogue it with Glue, query per-team and untagged spend in Athena, and build the QuickSight dashboard. Read your **untagged-spend** number. (~75 min, plus up-to-24h wait for the first CUR file)
2. **[Exercise 2 — Savings Plan, rightsizing, Graviton](exercise-02-savings-plan-rightsizing-graviton.py)** — pull Savings Plan purchase recommendations and Compute Optimizer rightsizing findings via the API, compute the commitment break-even, and quantify a Graviton price/performance move. (~75 min)
3. **[Exercise 3 — CloudFront edge with a tenant-header injector](exercise-03-cloudfront-edge-tenant-header.py)** — stand up a CloudFront distribution over an API origin with a CloudFront Function (header/cache-key rewrite) and a Lambda@Edge function (signed-cookie → `x-tenant-id`), and watch a request flow through both. (~90 min)

## Before you start

- **AWS CLI v2** configured with a profile that can use Cost Explorer (`ce`), Savings Plans, Compute Optimizer, Glue, Athena, CloudFront, WAF, and Lambda. `aws --version` should report `aws-cli/2.x`.
- **Python 3.12+** with the per-exercise `requirements.txt` (mostly just `boto3`). A clean virtualenv per exercise.
- **A Region you'll stick with** for the application resources. **But note:** the CUR report definition, Lambda@Edge, and WAF-for-CloudFront are all **`us-east-1`-only** global resources — deploy those there regardless of your app Region.
- **Create the Cost & Usage Report on Monday.** The first file can take **up to 24 hours** to land. If you start Exercise 1 on Tuesday with a CUR you created Monday, the data is there. If you create it Thursday, you have nothing to query.
- **Activate your cost allocation tags** (`team`, `service`, `environment`) in the Billing console on Monday. Activation is not retroactive.
- **A QuickSight account** for Exercise 1's dashboard (Standard edition is enough; first author has a trial window). If you'd rather not use QuickSight, the exercise notes a Grafana-on-Athena alternative.

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the commands and code yourself.** Copy-pasting teaches you nothing; typing builds the muscle memory you need in a cost review or an incident.
- Run it. Read the output. When the CUR query prints your **untagged spend**, stop and ask: *which resources is that, and why didn't they get tagged?* When you add a Lambda@Edge function, ask: *could this have been a cheaper CloudFront Function?*
- Tear down what costs money when you finish each session. The big ones this week: a Lambda@Edge function **replicates and takes time to fully delete** (you must disassociate it from the distribution first, then delete after replicas clear), a CloudFront distribution must be **disabled before delete**, and a WAF web ACL has a per-month cost while it exists. Athena scans against the CUR cost cents.
- Every exercise ends with a checkable artifact: a per-tag cost table, a recommendation read-out, or a request that flowed through both edge tiers. If you don't have it, you're not done.

## Cost note

Exercise 1 costs cents (a little S3 for the CUR, sub-GB Athena scans) plus whatever your QuickSight edition costs (the trial is free for the window). Exercise 2 is essentially free — it only *reads* recommendations via the API; it does **not** purchase a Savings Plan (purchasing is a real commitment — the homework discusses it, but you do not buy one in a lab). Exercise 3 costs a few cents of CloudFront requests/transfer plus the Lambda@Edge invocations; the only thing that *accrues* if you forget it is the WAF web ACL (added in the challenge) and an idle CloudFront distribution (negligible but not zero). **Disable and delete the distribution and disassociate the edge functions when you finish.**

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-14` to compare.
