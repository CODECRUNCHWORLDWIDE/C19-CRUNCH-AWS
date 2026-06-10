# Challenge 1 — Twelve Broken Policies: Find the Bug, Prove the Fix

**Time estimate:** ~120 minutes.

## Problem statement

Lecture 1 walked you through twelve policy bugs with the answers in front of you. This challenge gives you **twelve fresh policies** — different shapes, same five bug families — with **no answer key**. Your job is to do the senior-engineer thing for each one:

1. **Read it out loud** (effect / what / where / when), in writing, in one or two sentences.
2. **Name the bug** and classify it into one of the five families from Lecture 1, section 1.5:
   - over-broad `Resource`
   - missing condition
   - wrong condition / wrong attribute
   - `Not*` trap / empty-set mistake
   - ARN-granularity / privilege-escalation primitive
3. **Write the fix** as a corrected JSON policy.
4. **Prove the bug and the fix** with `aws iam simulate-custom-policy` — show that the broken policy allows (or denies) something it shouldn't, and that your fixed policy flips that decision.

A bug found by accident, without the evaluation-logic explanation, scores zero. The explanation is the skill being graded.

Account `111122223333` is "your" account throughout. The Organization ID is `o-abc123def4`.

---

## The twelve policies

### P1 — Pipeline artifact reader

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GetArtifacts",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": "arn:aws:s3:::ci-artifacts/*"
    }
  ]
}
```

### P2 — DynamoDB table access for a microservice

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OrdersTable",
      "Effect": "Allow",
      "Action": "dynamodb:*",
      "Resource": "arn:aws:dynamodb:us-east-1:111122223333:table/orders"
    }
  ]
}
```

### P3 — Cross-account read role trust

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustAuditAccount",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::444455556666:root" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### P4 — SNS topic policy for cross-service publishing

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3Publish",
      "Effect": "Allow",
      "Principal": { "Service": "s3.amazonaws.com" },
      "Action": "SNS:Publish",
      "Resource": "arn:aws:sns:us-east-1:111122223333:upload-events"
    }
  ]
}
```

### P5 — Developer "read-only" policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOnly",
      "Effect": "Allow",
      "NotAction": ["s3:DeleteObject", "s3:DeleteBucket", "dynamodb:DeleteTable"],
      "Resource": "*"
    }
  ]
}
```

### P6 — Secrets access scoped by MFA

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadProdSecretsWithMfa",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:us-east-1:111122223333:secret:prod/*",
      "Condition": {
        "Bool": { "aws:MultiFactorAuthPresent": "true" }
      }
    }
  ]
}
```

### P7 — Backup bucket protection

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBackups",
      "Effect": "Allow",
      "Action": "s3:*",
      "Resource": ["arn:aws:s3:::backups", "arn:aws:s3:::backups/*"]
    },
    {
      "Sid": "ProtectFromDeletion",
      "Effect": "Deny",
      "Action": "s3:DeleteObject",
      "Resource": "arn:aws:s3:::backups"
    }
  ]
}
```

### P8 — KMS key policy for an encrypted queue

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AppUsesKey",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::111122223333:role/queue-consumer" },
      "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:PutKeyPolicy", "kms:ScheduleKeyDeletion"],
      "Resource": "*"
    }
  ]
}
```

### P9 — Region lockdown SCP

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyOutsideEuWest1",
      "Effect": "Deny",
      "Action": "*",
      "Resource": "*",
      "Condition": {
        "StringNotEquals": { "aws:RequestedRegion": "eu-west-1" }
      }
    }
  ]
}
```

### P10 — EC2 instance management for an autoscaler role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ManageInstances",
      "Effect": "Allow",
      "Action": ["ec2:RunInstances", "iam:PassRole"],
      "Resource": "*"
    }
  ]
}
```

### P11 — ABAC self-service project access

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OwnProjectBuckets",
      "Effect": "Allow",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::proj-${aws:PrincipalTag/project}-*",
      "Condition": {
        "StringEquals": { "aws:PrincipalAccount": "111122223333" }
      }
    }
  ]
}
```

### P12 — Lambda invoke permission (resource policy on the function)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowApiGwInvoke",
      "Effect": "Allow",
      "Principal": { "Service": "apigateway.amazonaws.com" },
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:us-east-1:111122223333:function:checkout"
    }
  ]
}
```

---

## Acceptance criteria

- [ ] A file `findings.md` in your Week 2 repo under `challenges/challenge-01/` with **twelve sections**, one per policy.
- [ ] Each section contains: the read-out-loud, the named bug, the family classification, the corrected JSON, and the simulator command + decision that proves both the bug and the fix.
- [ ] At least **eight** of the twelve identifications are correct (a few are subtle; partial credit on the rest if the family is right even when the exact fix is imperfect).
- [ ] **Watch out:** not every policy is broken in the obvious way, and at least one of the twelve is *correct as written* — calling a correct policy "broken" is itself a wrong answer. Decide carefully which one and defend it.
- [ ] Every simulator proof is a real, runnable `aws iam simulate-custom-policy` (or `simulate-principal-policy`) command with the `--context-entries` it needs, and you paste the actual `EvalDecision` you got.
- [ ] Committed.

## How to prove with the simulator

The pattern for proving a bug (broken policy lets something through):

```bash
aws iam simulate-custom-policy \
  --policy-input-list file://p1-broken.json \
  --action-names s3:GetObject \
  --resource-arns 'arn:aws:s3:::ci-artifacts/build-42/app.zip' \
  --query 'EvaluationResults[0].{Action:EvalActionName,Decision:EvalDecision,Matched:MatchedStatements[0].SourcePolicyId}' \
  --output json
```

The pattern for proving a fix (fixed policy flips the decision):

```bash
aws iam simulate-custom-policy \
  --policy-input-list file://p9-fixed.json \
  --action-names iam:CreateRole \
  --resource-arns '*' \
  --context-entries ContextKeyName=aws:RequestedRegion,ContextKeyType=string,ContextKeyValues=us-east-1 \
  --query 'EvaluationResults[0].EvalDecision' --output text
```

For trust policies (P3, P4, P12) and resource policies, the simulator does not evaluate the `Principal` element directly — instead, reason about the trust in writing and prove the *identity-side* half (or the missing condition) where the simulator can help. For the confused-deputy cases, your written explanation carries the proof; state which `aws:SourceArn`/`aws:SourceAccount`/`sts:ExternalId` you would add and why the engine needs it.

## Hints

<details>
<summary>Which family is each, roughly (peek only after a real attempt)</summary>

- Over-broad `Resource`: look at P2 and P10.
- Missing condition: look at P3, P4, P12.
- Wrong condition / wrong attribute: look at P11.
- `Not*` trap / empty-set: look at P5.
- ARN-granularity / escalation primitive: look at P7, P8, P10.
- Region carve-out: P9 (the global-service trap from Lecture 1, Policy 9).
- One of these is actually fine as written. P1 and P6 are the two strongest candidates for "correct"; decide which and say why the other is subtly wrong.

</details>

<details>
<summary>The subtle one in P2</summary>

`dynamodb:*` on a single table ARN looks scoped — but DynamoDB Streams and indexes have *child* ARNs (`.../table/orders/index/*`, `.../table/orders/stream/*`). `dynamodb:*` on just the table ARN may *fail* to grant stream/index access the service needs, **and** some control-plane actions (`dynamodb:DeleteTable`) you almost certainly didn't intend to grant a runtime service are included in `dynamodb:*`. Two things wrong: over-broad action set (control plane in a data-plane role) and ARN scope that misses children. Split data-plane actions out and add the child ARNs.

</details>

<details>
<summary>Why P7's deny doesn't protect the bucket</summary>

Same as Lecture 1, Policy 11: the `Deny` on `s3:DeleteObject` targets `arn:aws:s3:::backups` (the *bucket* ARN), but `DeleteObject` acts on *objects* (`backups/*`). The deny never matches, so the `s3:*` allow still permits deleting every object. Fix: deny on `arn:aws:s3:::backups/*`, and if you also want to protect the bucket itself, deny `s3:DeleteBucket` on `arn:aws:s3:::backups`.

</details>

## Why this matters

This is the exact exercise a senior engineer runs in code review, except they do it in their head in thirty seconds per policy. The capstone's Identity requirements include a policy-review gate: no PR that touches IAM merges without a reviewer who can do this. The mini-project and Week 7's CI/CD work both wire `simulate-principal-policy` and Access Analyzer custom-policy-checks into the pipeline so the machine does the first pass — but the machine only catches what you taught it to look for, and you only know what to teach it once you can find these by hand.
