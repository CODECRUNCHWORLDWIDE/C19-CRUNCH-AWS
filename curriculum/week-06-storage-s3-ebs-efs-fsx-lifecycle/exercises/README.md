# Week 6 — Exercises

Three build exercises that compound. Exercise 1 produces the bucket; Exercise 2 adds replication and an Object Lambda on top of it; Exercise 3 stands up the shared-EFS demonstration. Do them in order — Exercise 2 imports the stack from Exercise 1, and the mini-project assembles all three.

## Index

1. **[Exercise 1 — A lifecycled, KMS-CMK, versioned bucket](exercise-01-lifecycled-kms-bucket.md)** — build the production bucket in CDK with SSE-KMS (CMK + Bucket Keys), versioning, Block Public Access, and the Standard → IA(30d) → Glacier IR(90d) → Deep Archive(365d) staircase. Verify with the CLI. (~1.5 h)
2. **[Exercise 2 — Cross-Region Replication + watermarking Object Lambda](exercise-02-crr-and-object-lambda.ts)** — runnable CDK (TypeScript) that adds CRR to a second region with replica re-encryption, and an S3 Object Lambda Access Point whose Lambda stamps a watermark on JPEGs at `GET` time. (~2.5 h)
3. **[Exercise 3 — Shared EFS across Fargate and EC2](exercise-03-shared-efs.py)** — runnable CDK (Python) that creates one EFS file system with an access point, mounts it into an ECS Fargate task and an EC2 instance, and proves shared read/write with a round-trip file. (~2 h)

## How to work the exercises

- **Read the prompt, then type the code.** Do not paste blindly — you are building muscle memory for the CDK constructs you will reuse all course.
- **`cdk diff` before every `cdk deploy`.** Read the change set. Storage resources (KMS keys, replication roles, BPA) are exactly where a silent mistake leaks data or money.
- **Tag everything** with `team`, `service`, `environment`. Week 14 FinOps will thank you, and it is a graded habit.
- **Tear down what costs money.** S3 at these volumes is pennies; leave the buckets. The EC2 instance in Exercise 3 and any `io2` volume must come down the same day — `cdk destroy` the compute, keep the storage.
- Every exercise ends with a **verification command** whose output you paste into your engineering journal. If you cannot produce the verification output, you are not done.

## A note on regions

Exercise 2 needs two regions (we use `us-east-1` as primary and `us-west-2` as the DR/replica region). Make sure both are bootstrapped: `cdk bootstrap aws://<account>/us-east-1 aws://<account>/us-west-2`. If you only bootstrapped one in Week 3, do the other now.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-06` to compare approaches.
