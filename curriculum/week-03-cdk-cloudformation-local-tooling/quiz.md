# Week 3 — Quiz

Fourteen questions on CDK, CloudFormation, OpenTofu, and the local-emulation loop. Take it with your lecture notes closed. Aim for 12/14 before moving to Week 4. Answer key at the bottom — don't peek.

---

**Q1.** What is the relationship between CDK and CloudFormation?

- A) CDK is a replacement for CloudFormation; `cdk deploy` talks directly to the AWS resource APIs.
- B) CDK is a program that *synthesizes* a CloudFormation template, which CloudFormation then deploys. CloudFormation is the substrate.
- C) CloudFormation is a wrapper around CDK; you cannot use CloudFormation without first running `cdk synth`.
- D) They are unrelated tools that happen to both deploy AWS resources.

---

**Q2.** You write `const bucket = new s3.Bucket(this, "Data");` and later `console.log(bucket.bucketName)`. What prints?

- A) The literal bucket name, e.g. `crunchiacstack-data6e1f4d8f-abc123`.
- B) `undefined`, because the bucket has not been created yet.
- C) A token placeholder string like `${Token[TOKEN.42]}`, because the real name does not exist until deploy time.
- D) An empty string, which CloudFormation fills in later.

---

**Q3.** Which statement about construct levels (L1/L2/L3) is correct?

- A) L1 constructs (`CfnBucket`) are 1:1 with CloudFormation resource types and expose every raw property; L2 constructs (`Bucket`) add sane defaults and helper methods; L3 are opinionated multi-resource patterns.
- B) L3 constructs are the lowest level, mapping directly to CloudFormation.
- C) L2 constructs cannot be customized; you must drop to L1 for any non-default setting.
- D) There is no functional difference; the levels are a documentation convention only.

---

**Q4.** What does `cdk bootstrap` create, and why is it needed?

- A) Nothing on AWS; it only configures your local `~/.aws/config`.
- B) A `CDKToolkit` CloudFormation stack containing a staging S3 bucket, an ECR repo, and IAM roles — the prerequisites that `cdk deploy` assumes already exist.
- C) Your application's VPC and S3 bucket, so you don't have to write them.
- D) A copy of the CDK CLI inside your account so deploys run server-side.

---

**Q5.** The "chicken-and-egg IAM problem" that bootstrapping solves is best described as:

- A) You need IAM permissions to create IAM permissions, so the first principal must be highly privileged.
- B) CDK needs a place to upload assets and a role to assume *before* it can deploy your stack — but creating that place and role is itself a deployment, so it must happen out-of-band first.
- C) CloudFormation cannot create roles, so you must create them by hand forever.
- D) Lambda functions cannot assume roles until a bucket exists.

---

**Q6.** Which is the most accurate description of a CDK **logical ID**?

- A) A random GUID regenerated on every synth.
- B) The friendly name you pass as the construct's `id` argument, used verbatim.
- C) A deterministic identifier CDK derives from the construct's path in the tree plus a hash; changing the construct's id or position can change it and cause CloudFormation to **replace** the resource.
- D) The physical AWS resource ARN.

---

**Q7.** You re-implement a TS CDK stack in Python CDK with the same constructs and props. What should `cdk synth` produce for each?

- A) Completely different templates, because the languages generate different CloudFormation.
- B) Structurally equivalent CloudFormation — the same resource types and counts — because both languages are thin skins over the same jsii-generated construct library. (Logical-ID hashes and asset hashes may differ.)
- C) Identical byte-for-byte templates, including logical IDs.
- D) Python produces YAML and TypeScript produces JSON, so they cannot be compared.

---

**Q8.** Which is true of OpenTofu/Terraform state versus CDK?

- A) Both keep a client-side state file mapping code to resource IDs.
- B) OpenTofu keeps a client-side **state file**; CDK has no state file — CloudFormation tracks the stack's resources **server-side**.
- C) CDK keeps a state file in `cdk.out/`; OpenTofu keeps its state in CloudFormation.
- D) Neither tool tracks state; both query live resources on every run.

---

**Q9.** Why does the bucket-name parity between the TS and OpenTofu versions of the same stack usually **differ**?

- A) OpenTofu cannot create S3 buckets.
- B) CDK derives a name from the stack + logical ID + hash when you don't specify one, while OpenTofu lets the AWS provider/`name_prefix` generate a different scheme — so auto-generated physical names differ even when the resources are equivalent.
- C) OpenTofu always uses the literal Terraform resource name as the bucket name.
- D) CloudFormation forbids generated bucket names.

---

**Q10.** In OpenTofu, you wrote the Lambda's IAM policy (`s3:GetObject` + `kms:Decrypt`) **by hand**. In CDK you did not. Why?

- A) CDK does not support IAM.
- B) CDK L2 `grant*` methods (`bucket.grantRead(fn)`) generate the least-privilege policy — including the KMS `Decrypt` grant — for you; OpenTofu's resource model has no equivalent, so you author the policy explicitly.
- C) OpenTofu auto-generates IAM but CDK requires manual policies.
- D) Both require manual policies; the exercise was wrong.

---

**Q11.** What does `sam local invoke` actually do?

- A) Invokes the function in your real AWS account but routes logs locally.
- B) Runs the function in a Docker container that mirrors the real Lambda runtime, against a template that locates the handler, runtime, and code.
- C) Translates your Lambda into a standalone binary.
- D) Calls the function through API Gateway in `us-east-1`.

---

**Q12.** You want your Lambda's `boto3` S3 client to hit LocalStack locally and real S3 in production, with **the same code**. The cleanest mechanism is:

- A) Hard-code `endpoint_url="http://localhost:4566"` and comment it out before deploying.
- B) Read `AWS_ENDPOINT_URL_S3` (honoured natively by modern SDKs) and pass it as `endpoint_url` only when set.
- C) Detect the environment with `if "localstack" in socket.gethostname()`.
- D) Maintain two separate handler files and swap them in CI.

---

**Q13.** CloudFormation **drift detection** compares:

- A) Your CDK code against the last synthesized template (this is what `cdk diff` does).
- B) The deployed stack's *expected* configuration (per the template) against the *actual* live resource configuration, catching out-of-band changes.
- C) Two different AWS accounts' resources.
- D) The current template against a previous Git commit.

---

**Q14.** Which statement about `cdk diff` versus `detect-stack-drift` is correct?

- A) They are the same operation with different names.
- B) `cdk diff` compares your **code** against the **last deployed template**; `detect-stack-drift` compares the **template** against **live reality**. `cdk diff` will not see a change someone made in the console.
- C) `cdk diff` sees console changes; `detect-stack-drift` only sees code changes.
- D) Neither can detect a manually deleted resource.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — CDK is a *synthesizer*. It runs your program, emits a CloudFormation template into `cdk.out/`, and hands it to CloudFormation, which is the engine that actually creates/updates/deletes resources. CloudFormation is the substrate; CDK is the ergonomic layer.
2. **C** — `bucketName` is a **token**: a placeholder for a value that does not exist until deploy time. CDK renders it into a CloudFormation `Ref`/`GetAtt` at synth. Never do string surgery on a token; use token-aware helpers (`Fn.join`, template literals CDK intercepts).
3. **A** — L1 (`Cfn*`) is the raw 1:1 mapping; L2 (`Bucket`, `Key`, `Vpc`) adds defaults and `grant*`/helper methods; L3 (e.g. `aws-ecs-patterns`) wires several resources into a pattern. You pick the lowest level that still gives you the ergonomics you want, and you can escape down to L1 via the escape hatch (`bucket.node.defaultChild as CfnBucket`).
4. **B** — Bootstrapping deploys the `CDKToolkit` stack: a versioned staging S3 bucket (for assets), an ECR repository (for image assets), and the deploy/file-publishing/image-publishing/lookup IAM roles. `cdk deploy` assumes these exist.
5. **B** — To deploy a stack, CDK first needs somewhere to put assets and a role to assume. But provisioning that place and role is itself a deployment. Bootstrapping breaks the cycle by creating those prerequisites out-of-band (and is why the bootstrap principal is so privileged — it is the most dangerous role in the account).
6. **C** — Logical IDs are deterministic, derived from the construct's tree path plus a hash. They are *stable* across synths if the tree is stable, but renaming a construct or moving it changes the logical ID, which CloudFormation reads as "delete the old resource, create a new one" — a replacement. This is a classic foot-gun.
7. **B** — Both languages bind to the same jsii-generated `aws-cdk-lib`, so equivalent code produces structurally equivalent templates: same resource types, same counts, same wiring. Auto-generated logical-ID and asset hashes can differ, which is why you diff the *type histogram*, not the raw bytes.
8. **B** — This is the single biggest mental-model difference. OpenTofu/Terraform hold a client-side **state file** (and you must protect it / put it in a backend). CDK has **no state file**; CloudFormation tracks the deployed resources server-side. Lose your CDK code and the stack is fine; lose your Terraform state and you have a recovery project.
9. **B** — When you don't pass an explicit name, CDK generates a physical name from stack + logical ID + hash, while the AWS provider in OpenTofu uses its own scheme (often `name_prefix` + random suffix). Equivalent resources, different auto-generated names. (You usually *let* names be generated to avoid name collisions on redeploy.)
10. **B** — L2 `grant*` methods are CDK's headline ergonomic win: `bucket.grantRead(fn)` writes the `s3:GetObject` policy **and** adds the `kms:Decrypt` grant for the bucket's CMK, scoped to exactly that bucket and key. OpenTofu's resource model has no such helper, so you author the `aws_iam_role_policy` by hand — which is exactly where over-broad `"Resource": "*"` policies sneak in.
11. **B** — `sam local invoke` runs the function inside a Docker container built to match the real Lambda runtime, reading a SAM/CloudFormation template to locate the handler, runtime, code path, and environment. It is the cheap inner loop for Lambda development.
12. **B** — Modern AWS SDKs (including boto3 ≥ 1.34) honour `AWS_ENDPOINT_URL_S3`. Read it and pass it as `endpoint_url` only when present. Same code runs locally (pointed at LocalStack) and in prod (env var unset → real S3). A and D are anti-patterns; C is brittle.
13. **B** — Drift detection is server-side: CloudFormation re-reads each resource's live configuration and compares it to what the template declares, surfacing out-of-band changes. Option A describes `cdk diff`.
14. **B** — `cdk diff` is code-vs-last-deployed-template; `detect-stack-drift` is template-vs-live-reality. A console change is invisible to `cdk diff` but caught by drift detection. Confusing the two is a common interview stumble.

</details>

---

If you scored under 10, re-read the lecture notes for the questions you missed — especially Q5/Q6 (bootstrap and logical IDs) and Q13/Q14 (drift vs diff), which are the load-bearing concepts for the rest of the course. If you scored 13 or 14, you're ready for the [homework](./homework.md).
