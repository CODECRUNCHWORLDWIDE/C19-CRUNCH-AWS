# Week 11 — Exercises

Three exercises that build on each other. The first two stand up the data lake; the third stands up the inference path. Do them in order — Exercise 2 queries the table Exercise 1 created, and the mini-project assumes all three are done.

## Index

1. **[Exercise 1 — Firehose → Glue → Athena](exercise-01-firehose-glue-athena.md)** — land NDJSON event data into S3 via Kinesis Data Firehose, crawl it with Glue, and run your first Athena queries. Read the bytes-scanned footer. (~75 min)
2. **[Exercise 2 — Partition, Parquet, and measure](exercise-02-partition-parquet-measure.py)** — convert the raw JSON to partitioned Parquet with Athena CTAS, add partition projection, re-query, and measure the cost-and-latency improvement programmatically. (~75 min)
3. **[Exercise 3 — SageMaker Spot training + real-time endpoint](exercise-03-sagemaker-spot-endpoint.py)** — train a tiny scikit-learn classifier on a managed-Spot training job, deploy it to a real-time endpoint, and invoke it. (~90 min)

## Before you start

- **AWS CLI v2** configured with a profile that can use S3, Firehose, Glue, Athena, and SageMaker. `aws --version` should report `aws-cli/2.x`.
- **Python 3.12+** with the per-exercise `requirements.txt`. A clean virtualenv per exercise keeps `sagemaker`'s heavy deps out of the others.
- **A Region you'll stick with all week.** `us-east-1` is assumed in the examples; if you use another, change it everywhere consistently.
- **Bedrock model access for Anthropic Claude enabled** — needed for the Friday challenge, not these exercises, but enable it Monday so it is ready.

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the commands and code yourself.** Copy-pasting AWS CLI calls teaches you nothing; typing them builds the muscle memory you need in an incident.
- Run it. Read the output. When Athena prints `Data scanned: X MB`, stop and ask why it is that number.
- Tear down what costs money when you finish each session: `aws sagemaker delete-endpoint`, empty and delete lab buckets, disable any crawler schedule. Leaving a real-time endpoint running over the weekend is a $40 surprise.
- Every exercise ends with a checkable artifact: a query result, a measurement table, or a successful prediction. If you don't have it, you're not done.

## Cost note

Exercises 1 and 2 cost cents (S3 storage, a few Firehose GB, sub-gigabyte Athena scans, one short Glue crawler). Exercise 3 costs more: a Spot training job (a few cents) plus a real-time endpoint that bills ~$0.115/hour while it exists. **Delete the endpoint the moment you finish Exercise 3.** The exercise's last step is the `delete-endpoint` call — do not skip it.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-11` to compare.
