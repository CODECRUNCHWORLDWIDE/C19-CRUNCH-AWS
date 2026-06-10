# Week 3 — Exercises

Three focused drills that build the same stack three ways. Do them **in order** — exercise 2 and 3 both compare against the template you synthesize in exercise 1.

## Index

1. **[Exercise 1 — A TS CDK app: VPC + KMS-encrypted S3 + Lambda](exercise-01-cdk-ts-vpc-s3-lambda.md)** — scaffold a CDK app in TypeScript, build the stack, synth it, read the CloudFormation, and deploy to `dev` (or to LocalStack). (~90 min)
2. **[Exercise 2 — Python CDK parity](exercise-02-python-cdk-parity.py)** — re-implement the identical stack in Python CDK and confirm it synthesizes an equivalent CloudFormation template. (~75 min)
3. **[Exercise 3 — The OpenTofu equivalent](exercise-03-opentofu-equivalent.tf)** — write the same stack in OpenTofu and diff the result against the CDK-synthesized template, naming the structural differences. (~90 min)

## How to work the exercises

- **Type the code yourself.** Do not copy-paste the whole file. The point of the drill is building the muscle memory of `cdk init`, `cdk synth`, `cdk diff`, `tofu plan`.
- After every change, **synth before you deploy.** `cdk synth` (or `tofu plan`) is your compiler. If it errors or leaves unresolved tokens, you are not done.
- **Keep your real-AWS spend near zero.** Default to LocalStack (`cdklocal`, `tflocal`) for the inner loop. Deploy to real `dev` only to *see* real behavior, and `cdk destroy` / `tofu destroy` when you finish.
- If you get stuck for more than 10 minutes, read the hints at the bottom of each file.
- Every exercise ends with a clean synth/plan and, where you deployed, a `destroy` so you are not paying for idle infrastructure.

## The shared stack

All three exercises build the **same logical stack** so you can diff them:

- A **VPC** with two AZs, public and private-isolated subnets, and **no NAT Gateway** (NAT is the silent budget killer; we avoid it deliberately this week).
- A **KMS customer-managed key** with rotation enabled.
- An **S3 bucket** encrypted with that key, versioned, public access fully blocked, TLS enforced, and a lifecycle rule transitioning objects to Infrequent Access at 30 days and expiring them at 365 days.
- A **Lambda function** (Python 3.12) with **least-privilege read access** to the bucket (and `kms:Decrypt` on the key, because the bucket is encrypted).

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-03` to compare approaches.
