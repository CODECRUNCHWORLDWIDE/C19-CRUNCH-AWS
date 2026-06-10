# Week 3 Homework

Six practice problems that revisit the week's topics — the IaC layering, constructs, bootstrap, drift, and the local loop. The full set should take about **5.5 hours** in total. Work in your Week 3 Git repository (the `crunch-iac-starter` you build in the mini-project, or a sibling `homework/` repo) so each problem produces at least one commit you can point to later.

Each problem includes a short **problem statement**, **acceptance criteria** so you know when you are done, a **hint** if you get stuck, and an **estimated time**.

A standing rule for the week applies to all of these: **synth before you deploy.** Every problem that produces infrastructure must show a clean `cdk synth` / `tofu plan` and, where you deployed, a `destroy` at the end.

---

## Problem 1 — Read a synthesized template like a senior

**Problem statement.** Take your Exercise 1 TypeScript stack and run `cdk synth > template.json`. Without deploying, answer the following in a file `notes/template-reading.md`, citing the exact JSON path (e.g. `Resources.DataKeyABC123.Properties.EnableKeyRotation`) for each:

1. Which resource enforces TLS-only access to the bucket, and what condition does it use?
2. Where, exactly, did the `kms:Decrypt` permission for the Lambda end up — which logical resource, and how is the key ARN referenced (a literal, a `Ref`, or an `Fn::GetAtt`)?
3. How many `AWS::EC2::Subnet` resources are in the template, and why is it that number given the VPC config?
4. Find one use each of the intrinsic functions `Ref`, `Fn::GetAtt`, and `Fn::Join` (or `Fn::Sub`) and explain in one sentence what each is doing.

**Acceptance criteria.**

- File `notes/template-reading.md` exists with all four answers, each citing a concrete JSON path.
- The TLS answer correctly identifies the `AWS::S3::BucketPolicy` and the `aws:SecureTransport` condition.
- Committed.

**Hint.** `cat template.json | python3 -m json.tool | less` to pretty-print, or open `cdk.out/CrunchIacTsStack.template.json` in your editor and use the outline. The TLS deny is in the bucket policy, not the bucket. `grantRead` writes the `kms:Decrypt` into an `AWS::IAM::Policy` attached to the Lambda's role.

**Estimated time.** 40 minutes.

---

## Problem 2 — L1 escape hatch

**Problem statement.** The L2 `Bucket` construct does not expose every CloudFormation property. Suppose you need to set the bucket's `AccelerateConfiguration` to `Enabled` (Transfer Acceleration), which the L2 does not surface as a clean prop in the version you are on. Use the **L1 escape hatch** to set it: access the underlying `CfnBucket` via `bucket.node.defaultChild` and call `addPropertyOverride`. Synthesize and confirm the property appears in the template.

Then write two sentences explaining, in your own words, the difference between an L1 construct (`CfnBucket`), an L2 construct (`Bucket`), and the escape hatch that lets you reach from one to the other.

**Acceptance criteria.**

- The synthesized `AWS::S3::Bucket` contains `AccelerateConfiguration: { AccelerationStatus: 'Enabled' }`.
- You used `addPropertyOverride` (or `addOverride`) on the L1 child, not a fork of the construct.
- A `notes/escape-hatch.md` with the two-sentence explanation.
- `cdk synth` is clean; committed.

**Hint.**

```typescript
const cfnBucket = bucket.node.defaultChild as import('aws-cdk-lib/aws-s3').CfnBucket;
cfnBucket.addPropertyOverride('AccelerateConfiguration.AccelerationStatus', 'Enabled');
```

Remember to **remove this** before you submit the mini-project — Transfer Acceleration costs money and the starter is meant to be near-free. This is a learning drill, not a permanent change.

**Estimated time.** 45 minutes.

---

## Problem 3 — Explain the bootstrap roles

**Problem statement.** In `notes/bootstrap-explained.md`, answer in prose (no code) the chicken-and-egg IAM question from Lecture 2:

1. Why can `cdk deploy` not simply use your human SSO credentials to create resources directly? What problem does the dedicated `cfn-exec` role solve?
2. Name the four IAM roles the bootstrap stack creates and state, in one sentence each, what each one is for (`deploy`, `file-publishing`, `image-publishing`, `lookup`).
3. The `cfn-exec` role defaults to `AdministratorAccess`. Why is that the single most dangerous principal in a bootstrapped account, and what is the production mitigation (the `--cloudformation-execution-policies` and permissions-boundary flags)?
4. If you delete the `CDKToolkit` stack by hand, what breaks on your next `cdk deploy`, and how do you recover?

**Acceptance criteria.**

- File exists with all four answers in prose.
- The answer to (3) correctly identifies that scoping `cfn-exec` and applying a permissions boundary is the mitigation, and ties back to Week 2's permission-boundary lecture.
- Committed.

**Hint.** Re-read Lecture 2 §2–§4. The key insight: deploys are run by a *role you trust to assume*, which in turn lets CloudFormation act via a *separate execution role* — so a compromised laptop session cannot do more than "start a deploy," and the actual resource creation is gated by the `cfn-exec` policy you control.

**Estimated time.** 45 minutes.

---

## Problem 4 — Induce and catch drift, scripted

**Problem statement.** Deploy your Exercise 1 stack (to real `dev` — drift detection is one of the real-AWS-only behaviors; LocalStack's drift support is incomplete). Then:

1. Mutate the bucket **out of band** in the console or via raw CLI — for example, add a tag `drifted=true` to the bucket, or disable versioning.
2. Write a script `scripts/check-drift.sh` that calls `aws cloudformation detect-stack-drift`, polls `describe-stack-drift-detection-status` until `DETECTION_COMPLETE`, then prints the drifted resources from `describe-stack-resource-drifts` and exits non-zero if `StackDriftStatus != IN_SYNC`.
3. Run it; confirm it catches your mutation and exits non-zero.
4. `cdk deploy` again (which re-asserts the template), re-run the script, confirm it now reports `IN_SYNC`.
5. `cdk destroy` to stop paying.

**Acceptance criteria.**

- `scripts/check-drift.sh` exists, polls correctly, and exits non-zero on drift / zero when in sync.
- A short `notes/drift.md` recording: what you mutated, the script's output showing the drift, and the output after re-deploying.
- One sentence distinguishing `cdk diff` (code vs last-deployed template) from `detect-stack-drift` (template vs reality).
- You ran `cdk destroy` afterward. Committed.

**Hint.**

```bash
ID=$(aws cloudformation detect-stack-drift --stack-name CrunchIacTsStack --profile crunch-dev --query StackDriftDetectionId --output text)
until [ "$(aws cloudformation describe-stack-drift-detection-status --stack-drift-detection-id "$ID" --profile crunch-dev --query DetectionStatus --output text)" = "DETECTION_COMPLETE" ]; do sleep 2; done
aws cloudformation describe-stack-resource-drifts --stack-name CrunchIacTsStack --profile crunch-dev \
  --query "StackResourceDrifts[?StackResourceDriftStatus!='IN_SYNC']"
```

**Estimated time.** 1 hour.

---

## Problem 5 — OpenTofu state, hands-on

**Problem statement.** Using your Exercise 3 OpenTofu stack against LocalStack (via `tflocal` or provider `endpoints`), do the following and record observations in `notes/tofu-state.md`:

1. `tofu apply` the stack. Open `terraform.tfstate` and find the S3 bucket resource. What real-world identifier does the state map your `aws_s3_bucket.data` to?
2. Manually delete the bucket out of band (`aws --endpoint-url=... s3 rb`). Run `tofu plan`. What does OpenTofu say it will do, and *why* does it know — given that you never told it the bucket was gone?
3. Run `tofu state list` and `tofu state show aws_kms_key.data`. In two sentences, contrast OpenTofu's state-file model with CDK's stateless/CloudFormation-owns-the-truth model.
4. `tofu destroy` to clean up.

**Acceptance criteria.**

- File `notes/tofu-state.md` with all four answers.
- The answer to (2) correctly identifies that `tofu plan` *refreshes* from the provider and detects the out-of-band deletion — the Terraform-family equivalent of drift, surfaced on every plan rather than on an explicit detect call.
- Committed; `tofu destroy` run.

**Hint.** The state file is JSON. Search it for `"type": "aws_s3_bucket"`. The `instances[0].attributes.id` (or `bucket`) is the mapping to reality. Re-read Lecture 1 §1 on "who owns the state."

**Estimated time.** 50 minutes.

---

## Problem 6 — Tool-choice memo

**Problem statement.** Write a 350–450 word decision memo at `notes/tool-choice-memo.md` answering a concrete scenario:

> Your team runs entirely on AWS today, ships serverless and container workloads, and has four engineers comfortable in TypeScript. A new partnership may require deploying a copy of the core data plane to GCP within 18 months — but that is not certain. You must pick the IaC tool for a greenfield platform repo *this quarter*.

Address, with reasons grounded in this week's lectures:

1. Which tool you would standardize on now (CDK, OpenTofu, raw CloudFormation, or a split), and why.
2. How the "possible GCP in 18 months" uncertainty does — or does not — change your answer. (Re-read Lecture 1's argument about why CDK won the AWS war and lost the OSS one.)
3. What you would do *differently* if the GCP requirement were certain and dated this quarter.
4. One concrete risk of your chosen tool and how you would mitigate it (state-file custody for OpenTofu; bootstrap-role blast radius and the AWS-only lock-in for CDK).

**Acceptance criteria.**

- File exists, 350–450 words, each numbered point addressed.
- The memo takes a clear position rather than hedging, and the position is defensible against the lecture material.
- Committed.

**Hint.** There is no single "right" answer, but there are indefensible ones. "CDK because it's newer" is indefensible. "CDK now because the team is TS-native, all-AWS, and the GCP requirement is speculative — with a documented exit cost — and we revisit if the partnership is signed" is the shape of a senior answer. This is for your engineering journal as much as for a grade; you will defend a version of it in Friday's review.

**Estimated time.** 35 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 40 min |
| 2 | 45 min |
| 3 | 45 min |
| 4 | 1 h 0 min |
| 5 | 50 min |
| 6 | 35 min |
| **Total** | **~4 h 35 min** |

(The remaining hour in the week's homework budget is the reading and the synth/deploy/destroy cycles these problems trigger.)

When you have finished all six, push your repo and make sure the [mini-project](./mini-project/README.md) starter is in good enough shape that Week 4 can branch from it without cleanup.
