# Lecture 1 — Why CDK Lost the Open-Source War but Won the AWS One — and When to Use OpenTofu Instead

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can place CloudFormation, CDK, SAM, Terraform, OpenTofu, and Pulumi on a single map; explain what `cdk synth` actually produces; and defend, in a design review, a choice between CDK and OpenTofu for a given system.

If you only remember one sentence from this lecture, remember this:

> **CDK is a CloudFormation template generator.** It is a TypeScript (or Python, or Java, or Go) program that, when you run it, prints a JSON CloudFormation template. Everything else — constructs, the L1/L2/L3 hierarchy, the slick deploy experience — is built on that one fact. Once you internalize that CDK *synthesizes* and CloudFormation *deploys*, the entire tool stops being magic.

---

## 1. The map: six tools, two substrates

Every infrastructure-as-code tool in the AWS universe sits on top of one of two substrates: **CloudFormation** (AWS's native deployment engine) or **a state file + provider API calls** (the Terraform model). Knowing which substrate a tool uses tells you almost everything about how it behaves under failure.

| Tool | Language | Substrate | Who controls it | Notes |
|------|----------|-----------|-----------------|-------|
| **CloudFormation** | YAML / JSON | CloudFormation | AWS | The bedrock. Declarative templates. Stateless client. |
| **SAM** | YAML (CFN superset) | CloudFormation | AWS | Serverless-focused macro over CloudFormation. Adds `sam local`. |
| **CDK** | TS / Py / Java / Go / .NET | CloudFormation | AWS | Imperative program that *synthesizes* CloudFormation. |
| **Terraform** | HCL | State file + provider calls | HashiCorp (BSL license since 2023) | Multi-cloud. Owns its own state. |
| **OpenTofu** | HCL | State file + provider calls | Linux Foundation (MPL-2.0) | The open-source fork of Terraform 1.5.x. Drop-in for most uses. |
| **Pulumi** | TS / Py / Go / .NET / Java | State file + provider calls | Pulumi Corp | "Terraform with a real language." Multi-cloud, imperative. |

There are two families here, and the split matters more than the language:

1. **The CloudFormation family** (CloudFormation, SAM, CDK). The client is *stateless*. There is no state file on your laptop. The source of truth for "what is deployed" lives in the CloudFormation service inside your AWS account. You hand AWS a template; AWS figures out the diff (a *change set*), executes it, and remembers the result. If your laptop catches fire mid-deploy, the deploy continues in AWS.

2. **The Terraform family** (Terraform, OpenTofu, Pulumi). The client is *stateful*. There is a state file — a JSON document mapping your declared resources to real cloud resource IDs — and it lives wherever you put it (locally, in S3, in a Terraform Cloud / Scalr / Spacelift backend). The tool computes the diff *on your machine* by comparing your code, the state file, and (with a `refresh`) reality. If you lose the state file, the tool no longer knows what it manages.

This single distinction — *who owns the state* — is the thing that decides how each tool fails, how it handles drift, and how dangerous a concurrent run is. Hold onto it.

---

## 2. What `cdk synth` actually produces

Stop treating CDK as a black box. Let us look at what it emits. A minimal CDK stack:

```typescript
import { App, Stack, StackProps } from 'aws-cdk-lib';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

class HelloStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);
    new Bucket(this, 'Data', { versioned: true });
  }
}

const app = new App();
new HelloStack(app, 'HelloStack');
app.synth();
```

When you run `cdk synth`, CDK executes that TypeScript program, walks the **construct tree** (`App` → `Stack` → `Bucket`), asks each construct to contribute CloudFormation, and writes a template to `cdk.out/HelloStack.template.json`. The relevant slice of that output:

```json
{
  "Resources": {
    "Data6E1F4D8F": {
      "Type": "AWS::S3::Bucket",
      "Properties": {
        "VersioningConfiguration": { "Status": "Enabled" }
      },
      "UpdateReplacePolicy": "Retain",
      "DeletionPolicy": "Retain"
    }
  }
}
```

Three things to notice, because they teach you how CDK thinks:

1. **The logical ID is `Data6E1F4D8F`, not `Data`.** CDK appends an 8-character hash derived from the construct's *path* in the tree. This is how CDK guarantees uniqueness and stability: rename the construct and the hash changes, which CloudFormation reads as "delete the old bucket, create a new one." This is the single most common way beginners accidentally delete a production resource. We return to it in Lecture 2.

2. **`DeletionPolicy: Retain` appeared even though you never typed it.** The L2 `Bucket` construct applies sane defaults. A bucket is stateful, so CDK refuses to let CloudFormation silently delete your data on stack teardown. This is the L2 value proposition: defaults a senior engineer would have chosen.

3. **The template is plain CloudFormation.** Nothing in `cdk.out` is CDK-specific at deploy time. `cdk deploy` uploads that JSON to the CloudFormation service and creates a change set. You could take `cdk.out/HelloStack.template.json` and deploy it by hand with `aws cloudformation deploy` and get the identical result.

> **Try it now.** In any empty folder: `npx cdk@2 init app --language=typescript`, paste the stack above into `lib/<name>-stack.ts`, run `npx cdk synth`, and open `cdk.out/*.template.json`. Read the whole thing. It is short. Do this before you go further — the entire mental model of this course depends on you having *seen* the synthesized template once with your own eyes.

---

## 3. The open-source war CDK lost

CDK launched in 2019 with real momentum. The pitch was irresistible to anyone who had hand-written 800 lines of CloudFormation YAML: *write infrastructure in a real programming language, with loops, conditionals, functions, types, and an IDE that autocompletes.* For AWS-only shops it was, and is, a genuinely better developer experience than raw CloudFormation.

So why did it not take over the world the way Terraform did? Three reasons, and they are worth understanding because they tell you exactly where CDK's boundaries are.

### 3.1 CDK only speaks CloudFormation

CDK synthesizes CloudFormation, and CloudFormation only deploys to AWS. There is **no CloudFormation for GCP, Azure, Cloudflare, Datadog, or your Postgres database.** CDK has a side project — **CDK for Terraform (CDKTF)** — that synthesizes Terraform HCL/JSON instead of CloudFormation, and that *can* target other providers. But CDKTF is a separate, less-mature tool, and the mainstream `aws-cdk-lib` is AWS-only by construction. If your company runs on three clouds plus a dozen SaaS APIs, CDK manages one corner of your estate. Terraform/OpenTofu manages all of it through one provider model.

This is the war CDK lost: **the multi-cloud, multi-provider war.** Terraform won it because its provider model is cloud-agnostic by design. There are 3,000+ Terraform providers — AWS, GCP, Azure, GitHub, Datadog, PagerDuty, Cloudflare, Snowflake, Kubernetes, Helm, your DNS registrar. CDK has exactly one substrate.

### 3.2 CloudFormation's coverage and speed lag

Because CDK rides CloudFormation, CDK can only manage what CloudFormation can manage, and only as fast as CloudFormation updates after a new AWS feature ships. AWS has gotten dramatically better at this — most services launch with same-day CloudFormation support now — but there remains a tail of features that land in the API and the console weeks or months before CloudFormation catches up. The Terraform AWS provider, maintained by a large community plus HashiCorp, frequently ships support for new AWS features *faster than CloudFormation does*, because it calls the AWS API directly rather than waiting for a CloudFormation resource provider.

There is an escape hatch in CDK for exactly this gap — `AwsCustomResource` and CloudFormation custom resources — but they are Lambda-backed hacks, and you feel the difference. With OpenTofu, you just set the new attribute and `apply`.

### 3.3 CloudFormation's failure mode is unforgiving

When a CloudFormation deploy fails partway, the stack rolls back — and during `UPDATE_ROLLBACK_FAILED` or a stuck `DELETE_IN_PROGRESS`, you can end up in a state that is genuinely painful to recover from. CloudFormation's rollback is automatic and atomic in intent, which is a feature, but when it gets stuck (an S3 bucket that will not delete because it is non-empty, a security group with a lingering ENI, a Lambda whose log group already exists) you are reading stack events and manually skipping resources. Terraform's "I'll tell you exactly what I'm going to do, then do it, and if it fails I leave the state where it died and you fix it forward" model is, for many engineers, less frightening because it is more transparent.

---

## 4. The AWS war CDK won

Now the other side, because this lecture's title is two-sided on purpose. Inside an AWS-only shop, CDK has effectively *won* against hand-written CloudFormation and, for many teams, against Terraform too. Here is why.

### 4.1 The construct ecosystem is a force multiplier

The L2 and L3 constructs encode AWS's own best practices. When you write `new Bucket(this, 'Data', { encryption: BucketEncryption.KMS, enforceSSL: true, blockPublicAccess: BlockPublicAccess.BLOCK_ALL })`, CDK emits a bucket policy denying non-TLS access, wires the KMS key permissions, and sets all four public-access-block flags. To get the equivalent in raw CloudFormation you write ~120 lines of YAML and you have to *know* to write them. The `aws-ecs-patterns.ApplicationLoadBalancedFargateService` L3 construct stands up an ALB, a target group, listeners, a Fargate service, a task definition, security groups, and the IAM roles in about ten lines. That is leverage Terraform's flat resource model does not give you out of the box (Terraform modules approximate it, but you assemble them yourself).

### 4.2 `grant*` methods make IAM less awful

This is the feature that sells CDK to anyone who suffered through Week 2. Instead of hand-writing an IAM policy that lets your Lambda read your bucket, you write:

```typescript
bucket.grantRead(myLambda);
```

CDK figures out the exact actions (`s3:GetObject`, `s3:GetBucket*`, `s3:List*`), scopes the resource ARNs to that bucket and `bucket/*`, *and* — because the bucket is KMS-encrypted — adds `kms:Decrypt` on the bucket's key to the Lambda's role. It writes least-privilege IAM that you would have gotten subtly wrong by hand. The `grant*` pattern is the single best argument for CDK in an AWS shop, and you will use it constantly.

### 4.3 The state problem disappears

Because CDK rides CloudFormation, **there is no state file to manage, lock, back up, or corrupt.** No S3 backend, no DynamoDB lock table, no "someone ran apply without pulling the latest state and now we have a fork." CloudFormation is the lock and the state, server-side, for free. For a team that does not want to operate Terraform state infrastructure, this is a real reduction in operational surface area. (The cost: you inherit CloudFormation's failure modes from §3.3.)

### 4.4 CDK Pipelines are first-class

`pipelines.CodePipeline` builds a self-mutating CI/CD pipeline that updates *itself* when you change its definition, then deploys your stacks across accounts and regions in waves. It is genuinely good, it is CDK-native, and it makes the multi-account deploy story (which you set up in Week 1) tractable. We build a small one in the mini-project.

---

## 5. The decision table you will defend in a design review

Here is the table. Memorize the shape, not the exact cells.

| If… | Reach for | Because |
|-----|-----------|---------|
| You are an AWS-only shop and your team writes TS/Python | **CDK** | `grant*`, L2/L3 constructs, no state to manage, CDK Pipelines |
| You run two or more clouds, or AWS + a pile of SaaS providers | **OpenTofu** | One provider model spans everything; CDK is AWS-only |
| You need a brand-new AWS feature CloudFormation does not support yet | **OpenTofu** (or a CDK custom resource as a stopgap) | The TF AWS provider often ships faster than CloudFormation |
| Your org has standardized on Terraform and has a module library + state platform | **OpenTofu** | Don't fight an existing, working investment |
| You are deploying purely serverless (Lambda, API GW, DynamoDB, SQS) and want fast local invoke | **SAM** or **CDK + `sam local`** | SAM's `local invoke`/`local start-api` are purpose-built |
| You want a real language but multi-cloud | **Pulumi** | Imperative + multi-provider; the niche CDK can't fill |
| You are writing one-off "click this together" infra and learning | **CloudFormation by hand once**, then never again | You should see the substrate once; then stop writing YAML by hand |

The honest senior-engineer answer to "CDK or Terraform?" in 2026 is: **it depends on your blast radius.** If your blast radius is one AWS account family and your team is TypeScript-native, CDK is the higher-leverage choice. The moment a second cloud or a meaningful SaaS-provider surface enters the picture, OpenTofu's single-pane-of-glass wins. This course teaches **CDK as primary** because Crunch AWS is an AWS course — but you write the OpenTofu version of every core stack *precisely so you can defend the boundary.*

---

## 6. Why OpenTofu, not Terraform

A note on naming, because it matters in 2026 and you will be asked about it.

In August 2023, HashiCorp relicensed Terraform from the MPL-2.0 open-source license to the **Business Source License (BSL 1.1)** — a "source-available" license that restricts using Terraform to compete with HashiCorp's commercial products. The community forked the last MPL-licensed version (Terraform 1.5.x) into **OpenTofu**, donated it to the Linux Foundation, and has maintained it as a true open-source project since. OpenTofu 1.6 shipped in early 2024; by 2026 OpenTofu has its own features (early state encryption, provider-defined functions, `-exclude` targeting) and is a drop-in replacement for most Terraform usage.

For a course whose charter is **open-source-first** (see the C19 README), **OpenTofu is the default.** The CLI is `tofu` instead of `terraform`; the file extension is still `.tf`; the AWS provider is the same `hashicorp/aws` provider (OpenTofu can use the registry mirror at `registry.opentofu.org`). Everything you learn transfers to Terraform and vice versa. We say "OpenTofu" throughout and you can mentally substitute "Terraform" if your employer is on the BSL version.

```bash
# Terraform                # OpenTofu
terraform init             tofu init
terraform plan             tofu plan
terraform apply            tofu apply
terraform destroy          tofu destroy
```

Install OpenTofu (macOS):

```bash
brew install opentofu
tofu version
# OpenTofu v1.9.x
```

---

## 7. CloudFormation, briefly, because it is the substrate

You will not hand-write much CloudFormation in this course. But you must be able to *read* it, because CDK synthesizes it and you debug at the CloudFormation layer when CDK's abstraction leaks. The minimum vocabulary:

- **Template.** A YAML or JSON document with up to nine top-level sections; the ones you care about are `Resources` (required), `Parameters`, `Outputs`, `Conditions`, and `Mappings`.
- **Stack.** A deployed instance of a template, identified by name, living in one account and one region. CloudFormation tracks every resource in the stack.
- **Change set.** The diff CloudFormation computes between the deployed stack and a new template. `cdk deploy` creates and executes a change set under the hood. You can create one without executing it to preview a deploy.
- **Resource.** A typed entry under `Resources`, e.g. `AWS::S3::Bucket`. Each type is backed by a *resource provider* that knows how to create/update/delete it via the AWS API.
- **Intrinsic functions.** `Ref` (get the default identifier of a resource or a parameter value), `Fn::GetAtt` (get a specific attribute, e.g. a bucket's ARN), `Fn::Sub` (string interpolation), `Fn::Join`, `Fn::ImportValue` (cross-stack references).
- **`DependsOn`.** Explicit ordering. CloudFormation infers most dependencies from `Ref`/`GetAtt`, but sometimes you must state ordering by hand. CDK adds these automatically when you call `node.addDependency`.

A minimal CloudFormation template, by hand, so you have seen one:

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: A bucket and its name as an output.
Resources:
  DataBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    Properties:
      VersioningConfiguration:
        Status: Enabled
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: aws:kms
Outputs:
  BucketName:
    Description: The generated bucket name.
    Value: !Ref DataBucket
```

Deploy it without any CDK:

```bash
aws cloudformation deploy \
  --template-file bucket.yaml \
  --stack-name hand-written-bucket \
  --profile crunch-dev

aws cloudformation describe-stacks \
  --stack-name hand-written-bucket \
  --query "Stacks[0].Outputs" \
  --profile crunch-dev
```

That is the substrate. CDK generates exactly this kind of document — just with hashed logical IDs and far more of it — and hands it to the same `cloudformation deploy` machinery. You will deploy this by hand in Exercise 1's warm-up so the substrate is concrete before you let CDK hide it.

---

## 8. SAM and `sam local` — the serverless slice

The **Serverless Application Model (SAM)** is a CloudFormation *transform*: a macro that expands shorthand resources like `AWS::Serverless::Function` into full CloudFormation. SAM's lasting value for us is not the template syntax — CDK is better for that — it is the **`sam local` command family**, which runs Lambda functions and APIs locally inside Docker:

```bash
sam local invoke MyFunction --event events/test.json
sam local start-api          # emulates API Gateway + Lambda on localhost:3000
sam local start-lambda       # emulates the Lambda invoke endpoint
```

`sam local invoke` builds your function's runtime in a Docker container that mirrors the real Lambda execution environment, feeds it an event JSON, and prints the result. Combined with LocalStack for the *other* services the function talks to (S3, DynamoDB), you get a full local loop with zero AWS calls. That is the Friday lab and the challenge. The key trick — which trips everyone up the first time — is pointing the function's AWS SDK at LocalStack's endpoint instead of real AWS, via an `AWS_ENDPOINT_URL` environment variable. We cover the exact wiring in the challenge.

---

## 9. LocalStack, dynamodb-local, MinIO — the local emulation stack

The three local emulators, and when each earns its place:

- **LocalStack.** A single container that emulates dozens of AWS services — S3, Lambda, IAM, KMS, SQS, SNS, DynamoDB, CloudFormation, Step Functions, and more — behind one endpoint (`http://localhost:4566`). The community edition covers everything this course needs. You point your AWS SDK / CLI / CDK at it with an endpoint override. There are wrapper CLIs — `cdklocal` (CDK against LocalStack) and `tflocal` (OpenTofu against LocalStack) — that pre-configure the endpoint for you. **Use LocalStack when you want to test the whole stack — CloudFormation deploy, IAM, multiple services — locally.**

- **dynamodb-local.** A standalone, AWS-published Java jar (also a Docker image) that runs DynamoDB locally. Lighter than LocalStack if DynamoDB is *all* you need. Week 9 (single-table design) leans on it hard. **Use it when DynamoDB is the only service in your loop.**

- **MinIO.** An S3-compatible object store, open-source, that you run yourself. Not an emulator — a real implementation of the S3 API. **Use it when you want a persistent, fast, S3-compatible store for development** (or, beyond this course, as a genuine self-hosted S3 alternative). For pure S3 testing it is faster and more faithful than LocalStack's S3.

The decision: **LocalStack for full-stack IaC loops, dynamodb-local for DynamoDB-only, MinIO for S3-heavy or self-hosted-S3 work.** This week you use LocalStack as the primary loop and touch MinIO and dynamodb-local so you know the alternatives exist.

A one-liner to get LocalStack running (you do this for real on Friday):

```bash
docker run --rm -d \
  --name localstack \
  -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  localstack/localstack:latest

aws --endpoint-url=http://localhost:4566 s3 mb s3://test-bucket --profile localstack
aws --endpoint-url=http://localhost:4566 s3 ls --profile localstack
```

The Docker socket mount matters: LocalStack uses it to spawn Lambda containers. Without it, Lambda emulation silently fails.

---

## 9a. The decision framework — what you say in a design review

Tool choice is not a vibe. Here is the framework I want you to be able to reproduce on a whiteboard, because some version of this question — "CDK or Terraform?" — comes up in every infra design review and most senior interviews.

Ask four questions, in order. The first one that gives a hard answer wins; you do not need to reach the fourth.

1. **Is the target more than one cloud, now or on a committed roadmap?** If you are deploying to AWS *and* GCP/Azure with the *same tool and the same engineers*, CDK is off the table — its substrate is CloudFormation, which only knows AWS. Reach for OpenTofu (or Pulumi if you want a real language). "Multi-cloud someday, maybe" is **not** a hard answer — see the homework memo. A *committed, dated* multi-cloud requirement is.

2. **Does the team already own a large Terraform/OpenTofu module library and the people who maintain it?** If yes, the switching cost to CDK is real and rarely worth it. Standardize on OpenTofu and keep your modules. Tooling follows the team, not the other way around.

3. **Is the workload AWS-native and serverless/event-driven (Lambda, Step Functions, EventBridge, DynamoDB)?** If yes, CDK's L2/L3 constructs and `grant*` ergonomics are a genuine productivity multiplier, and `sam local` gives you a local loop. This is the C19 capstone's shape, which is exactly why this course standardizes on CDK.

4. **None of the above gave a hard answer?** Default to the team's existing language. TS/Python team, all-AWS, greenfield → CDK. HCL-fluent team or "we might leave AWS" → OpenTofu. Document the exit cost either way.

The framing underneath all four is **blast radius under failure**, which comes straight from the two-substrate split in §1:

| Failure mode | CDK / CloudFormation | OpenTofu / Terraform |
|---|---|---|
| Laptop dies mid-deploy | Deploy continues server-side; stack reaches a terminal state | `apply` halts; state file may be mid-write — recover from backup or `force-unlock` |
| Two people deploy at once | CloudFormation serializes updates per stack; second waits or fails cleanly | Without remote-state locking, you can corrupt state; *with* a locking backend, the second blocks |
| Someone changes a resource in the console | Invisible until you run `detect-stack-drift` | Surfaced on the next `plan` (it refreshes from reality) |
| You lose your IaC code | Stack is fine; re-import code from the deployed template | Stack is fine, but losing the *state file* is a recovery project |

Notice the symmetry: CDK's weakness (drift is invisible until you ask) is OpenTofu's strength (every plan refreshes), and OpenTofu's weakness (you must protect the state file and lock it) is CDK's strength (there is no state file to lose). Neither is "better." They fail differently, and you pick the failure mode you would rather operate.

One more honest note for the review: **CDK locks you into AWS at the substrate level, not just the API level.** Even though CDK can target other providers via the CDK for Terraform (`cdktf`) project, mainstream CDK (`aws-cdk-lib`) compiles to CloudFormation, full stop. If "leave AWS" is a real future, you do not want your entire infra expressed in a tool whose only output is an AWS-only deployment document. That single sentence is the crux of "CDK won the AWS war and lost the open-source one," and it is the answer the next lecture's homework wants you to be able to give.

---

## 10. The token system — the one CDK concept that confuses everyone

Here is the conceptual landmine that catches every CDK beginner, so we defuse it now.

When you write `bucket.bucketName` in CDK, you do **not** get the actual bucket name as a string. The bucket name does not exist yet — the bucket has not been created. What you get is a **token**: a placeholder object that CDK renders into a CloudFormation intrinsic function (`{ "Ref": "Data6E1F4D8F" }`) at synth time. If you `console.log(bucket.bucketName)` you see something like `${Token[TOKEN.42]}`, not a name.

```typescript
const bucket = new Bucket(this, 'Data');
console.log(bucket.bucketName);
// ${Token[TOKEN.42]}   <-- NOT a bucket name. This is correct and expected.
```

The rule that follows: **never do string surgery on a token.** You cannot `bucket.bucketName.split('-')` or `.toUpperCase()` it — you are operating on a placeholder. To build a string *containing* a token, use CDK's token-aware helpers (`Fn.join`, `Fn.sub`, or just a template literal, which CDK intercepts):

```typescript
// Correct: CDK intercepts the template literal and renders a Fn::Join at synth.
const arn = `arn:aws:s3:::${bucket.bucketName}/*`;

// Wrong: this throws or produces garbage, because you're manipulating a placeholder.
const prefix = bucket.bucketName.substring(0, 3); // DON'T
```

Tokens are why CDK can let you write code that references values that do not exist yet. Once you accept "this is a promise, not a value," tokens stop being mysterious. We exploit them all week.

---

## 11. Recap

You should now be able to:

- Place CloudFormation, SAM, CDK, Terraform, OpenTofu, and Pulumi on a two-substrate map (CloudFormation vs state file).
- Explain that `cdk synth` produces a CloudFormation template and `cdk deploy` hands it to the CloudFormation service.
- State the three reasons CDK lost the multi-cloud war (AWS-only substrate, CloudFormation coverage/speed lag, CloudFormation's failure modes) and the four reasons it won the AWS one (constructs, `grant*`, no state to manage, CDK Pipelines).
- Defend a CDK-vs-OpenTofu choice using the blast-radius framing.
- Say why this course uses OpenTofu, not Terraform.
- Read a small CloudFormation template and name `Ref`, `Fn::GetAtt`, change sets, and `DeletionPolicy`.
- Explain what a CDK token is and why you must not do string surgery on one.

Next up: the mechanics — how `cdk bootstrap` solves a chicken-and-egg IAM problem, the L1/L2/L3 construct hierarchy, and how to catch drift. Continue to [Lecture 2 — bootstrap, Constructs, Drift, and the Substrate](./02-bootstrap-constructs-drift-and-the-substrate.md).

---

## References

- *AWS CDK Developer Guide* — the canonical reference: <https://docs.aws.amazon.com/cdk/v2/guide/home.html>
- *AWS CDK API reference (`aws-cdk-lib`)*: <https://docs.aws.amazon.com/cdk/api/v2/>
- *CloudFormation User Guide*: <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html>
- *AWS SAM Developer Guide* — `sam local`: <https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local.html>
- *OpenTofu documentation*: <https://opentofu.org/docs/>
- *OpenTofu vs Terraform — the fork explained*: <https://opentofu.org/manifesto/>
- *Terraform AWS provider*: <https://registry.terraform.io/providers/hashicorp/aws/latest/docs>
- *LocalStack documentation*: <https://docs.localstack.cloud/>
- *CDK Pipelines*: <https://docs.aws.amazon.com/cdk/v2/guide/cdk_pipeline.html>
- *CDK tokens*: <https://docs.aws.amazon.com/cdk/v2/guide/tokens.html>
