# Week 10 — Exercises

Three exercises, in order. Do them in order — each builds on the artifact the previous one left running. They assemble the order-processing pipeline that the mini-project hardens and that the capstone reuses as its event spine.

All three target your AWS `dev` account via an `aws sso login` profile. The CDK app is TypeScript; the two runnable drills are Python (`boto3` + `aws-lambda-powertools`). Everything fits in or near the free tier **if you tear down the stack each night** — the `cdk destroy` step is in every exercise for a reason.

| # | File | What you build | Mode |
|---|------|----------------|------|
| 1 | [exercise-01-build-the-order-pipeline.md](./exercise-01-build-the-order-pipeline.md) | API Gateway → Lambda → EventBridge custom bus → SQS (retry-able work) + Step Functions Express (orchestration) + Firehose-to-S3 (analytics). Guided, step-by-step, CDK TypeScript with full starter and solution. | Guided build |
| 2 | [exercise-02-dlqs-and-poison-pill.py](./exercise-02-dlqs-and-poison-pill.py) | Add DLQs everywhere, fire a deliberately malformed order, and assert it lands in the **correct** DLQ — `order-validator-dlq` — with its payload intact, while good orders keep flowing. Runnable boto3 drill. | Runnable |
| 3 | [exercise-03-archive-replay-idempotent.py](./exercise-03-archive-replay-idempotent.py) | Create an EventBridge archive, publish a batch of orders, replay them, and prove the idempotency table rejects every duplicate so no order is charged twice. Runnable boto3 + DynamoDB drill. | Runnable |

## Before you start

```bash
# 1. Confirm your toolchain
node --version          # v20.x
python3 --version       # 3.12.x
cdk --version           # 2.160.0 or later
aws --version           # aws-cli/2.x
tofu version            # 1.8+ (only for the stretch goal)

# 2. Authenticate
aws sso login --profile crunch-dev
export AWS_PROFILE=crunch-dev
export AWS_REGION=eu-west-1

# 3. Confirm you can see your account
aws sts get-caller-identity
```

## Running the Python drills

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install boto3 aws-lambda-powertools

# Exercise 2 (after the stack from exercise 1 is deployed):
python3 exercise-02-dlqs-and-poison-pill.py

# Exercise 3:
python3 exercise-03-archive-replay-idempotent.py
```

Both drills read the stack's resource names from CloudFormation outputs, so deploy exercise 1's stack first. Both are **non-destructive** to your data and **idempotent themselves** — you can re-run them.

## A word on cost

The only line items that bill while idle are anything Kinesis-provisioned and anything MSK. Exercise 1 uses **Firehose** (pay-per-GB, free when idle) and an **on-demand** posture everywhere else, so leaving the exercise-1 stack up overnight costs cents. The MSK comparison lives in the challenge, which has its own loud teardown step. Still: `cdk destroy` when you finish for the day. It is one command and it is a good habit.
