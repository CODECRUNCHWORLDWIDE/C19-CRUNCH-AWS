# Week 4 — Exercises

Three focused, building drills. Do them in order — each one assumes the stack from the one before. By the end you have a production-shape VPC with endpoints and a private host that proves zero-NAT for AWS-service traffic. That stack is the seed for the mini-project.

## Index

1. **[Exercise 1 — Build a three-AZ VPC](exercise-01-three-az-vpc.md)** — a guided CDK build of a VPC across three AZs with public, private, and isolated subnets per AZ and exactly **one** NAT Gateway. Read the synthesized CloudFormation and verify the topology with the AWS CLI. (~90 min)
2. **[Exercise 2 — Add VPC endpoints](exercise-02-vpc-endpoints.ts)** — extend the VPC with S3 + DynamoDB **gateway** endpoints and **interface** endpoints for STS, KMS, SSM (+ messages), ECR API, and ECR DKR. A runnable CDK stack you can `cdk deploy`. (~60 min)
3. **[Exercise 3 — Prove zero NAT](exercise-03-prove-zero-nat.ts)** — deploy a private EC2 instance reachable only via Session Manager, pull from ECR and read from S3, and prove with NAT Gateway CloudWatch metrics that **zero** bytes crossed the NAT for that traffic. A runnable CDK stack plus a verification script. (~75 min)

## How to work the exercises

- **Set your budget alarm first.** These create billable resources (one NAT Gateway, a few interface endpoints, one `t3.micro`). Roughly **$0.05–0.08/hour** while up. `cdk destroy` every night.
- Pin your account and region: `export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)` and `export CDK_DEFAULT_REGION=us-east-1`.
- **Type the code yourself.** Do not paste the whole file. The point is to feel where the constructs connect.
- After every `cdk deploy`, **prove it** with the AWS CLI — don't trust the console's green checkmarks. The proof commands are in each exercise.
- Every exercise ends with a teardown step. Run it. An idle NAT Gateway you forgot about is the single most common surprise on a student's bill.

## Project scaffold (do this once, before Exercise 1)

```bash
mkdir crunch-week04 && cd crunch-week04
npx aws-cdk@2 init app --language typescript
npm install
# Sanity check the toolchain.
npx cdk --version
npx cdk bootstrap   # only if this account/region isn't bootstrapped yet
```

The exercises drop their stacks into `lib/` and wire them in `bin/`. Each exercise tells you exactly where.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-04` to compare.
