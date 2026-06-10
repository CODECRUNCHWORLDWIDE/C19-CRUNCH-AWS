# Week 3 — CDK, CloudFormation & Local Tooling

Welcome to Week 3 of **C19 · Crunch AWS**. Weeks 1 and 2 were about posture: a multi-account Organization, SCPs, IAM Identity Center, and permission boundaries. You can now log into `dev` and `prod` as a human who assumes a role, and you have a permission boundary that stops you from doing anything catastrophic. This week we stop clicking in the console and start describing infrastructure as code — because every artifact you build for the rest of this course gets deployed through the scaffold you build this week.

The thesis of Week 3 is simple and opinionated: **CloudFormation is the substrate, CDK is the ergonomic layer on top of it, and OpenTofu is your escape hatch when you need to leave AWS.** You will write the same stack — a VPC, a KMS-encrypted S3 bucket with lifecycle rules, and a Lambda that reads from the bucket — three times: in TypeScript CDK (the primary language for this course), in Python CDK, and in OpenTofu. You will synthesize the CloudFormation template each tool produces and diff them. By Friday you will understand, concretely and not as folklore, what CDK is actually doing when you type `cdk deploy`, why `cdk bootstrap` exists, and why the bootstrap role is the most dangerous IAM principal in your account.

You will also stand up a **local emulation loop** with LocalStack, dynamodb-local, and MinIO. AWS is not free; the fastest way to blow your $80 course budget is to run your inner development loop against real AWS. We iterate locally and deploy to real AWS only when we want to see real-AWS-only behavior. That loop — synth, deploy to LocalStack, `sam local invoke`, assert, repeat — is the muscle you build this week and use every week after.

> **The "clean synth" promise.** Every exercise that ends in working code ends with `cdk synth` producing a CloudFormation template with **zero errors and zero unresolved tokens**, or `tofu plan` reporting a plan with **no errors and the resource count you expected**. If your synth fails or your plan errors, you are not done. We treat a failed synth the way Week 1 of C9 treats a compiler warning: as a bug.

## Learning objectives

By the end of this week, you will be able to:

- **Explain** the relationship between CloudFormation (the substrate), CDK (the synthesizer), and OpenTofu/Terraform (the cross-cloud alternative) without conflating them.
- **Scaffold** a CDK app in TypeScript from a blank folder with `cdk init`, and read every file the template generates.
- **Distinguish** L1 (`Cfn*`), L2, and L3 (pattern) constructs, and choose the right level for a given resource.
- **Provision** a production-shaped stack — VPC, KMS-encrypted S3 bucket with lifecycle rules, and a Lambda with least-privilege read access — and deploy it to a `dev` account.
- **Re-implement** the identical stack in Python CDK and confirm it synthesizes an equivalent CloudFormation template.
- **Write** the equivalent stack in OpenTofu and diff its plan against the CDK-synthesized template, naming the structural differences.
- **Bootstrap** an environment with `cdk bootstrap`, and explain the chicken-and-egg IAM problem the bootstrap stack solves — and the four roles it creates.
- **Detect drift** on a deployed stack with CloudFormation drift detection after mutating a resource out-of-band, and explain why drift is the hidden tax of IaC.
- **Run** a Lambda locally against an emulated S3 bucket using LocalStack and `sam local invoke`, with no real AWS calls.
- **Compose** a CDK pipeline (`CodePipeline` via `pipelines.CodePipeline`) that self-mutates and deploys the stack to `dev`.

## Prerequisites

This week assumes you have completed **C19 Weeks 1 and 2**, or have equivalent fluency:

- A multi-account AWS Organization with at least a `dev` account you can assume a role into via `aws sso login`.
- A working `aws` CLI v2 with named profiles, and the ability to run `aws sts get-caller-identity` and see the role you expect.
- Comfort reading IAM JSON: you know what `sts:AssumeRole`, a trust policy, and a permission boundary are. Week 2 is load-bearing here.
- Node.js 20+ and npm (for TypeScript CDK and the CDK CLI), Python 3.12+ with `venv` (for Python CDK), and Docker (LocalStack, MinIO, `sam local invoke`, and CDK asset bundling all need it).
- Terraform/OpenTofu fluency from **C15 · Crunch DevOps** — you have written a `.tf` file and run `plan`/`apply` before. We do not teach HCL from scratch; we teach the AWS provider and the diff against CDK.

You do **not** need prior CDK experience. We start at `cdk init`.

## Topics covered

- The IaC landscape on AWS in 2026: CloudFormation, CDK (TS/Py/Java/Go/.NET), SAM, OpenTofu, Terraform, Pulumi — and which won which war.
- CloudFormation as the substrate: templates, stacks, change sets, the resource provider model, `DependsOn`, intrinsic functions (`Ref`, `Fn::GetAtt`, `Fn::Sub`).
- The `aws-cdk-lib` v2 model: `App`, `Stack`, `Construct`, the construct tree, tokens, and `cdk synth`.
- Construct levels: L1 (`CfnBucket`, a 1:1 CloudFormation mapping), L2 (`Bucket`, with sane defaults and helper methods), L3 (patterns like `aws-ecs-patterns`).
- `cdk bootstrap`: the CDKToolkit stack, the staging S3 bucket and ECR repo, and the four IAM roles (`deploy`, `file-publishing`, `image-publishing`, `lookup`) — and the chicken-and-egg IAM problem.
- The CDK deploy mechanics: assets, the staging bucket, change sets, `--require-approval`, `--hotswap`.
- CDK Pipelines: `pipelines.CodePipeline`, self-mutation, stages, and waves.
- Drift detection: `aws cloudformation detect-stack-drift`, why drift happens, and the operational discipline around it.
- OpenTofu for the same stack: the AWS provider, state files and backends, `plan`/`apply`, and the structural diff against a synthesized CloudFormation template.
- Local emulation: LocalStack (S3, Lambda, IAM, KMS, CloudFormation), dynamodb-local, MinIO. `cdklocal` and `tflocal` wrappers. `sam local invoke`.
- KMS-encrypted S3 with lifecycle rules and a least-privilege Lambda reader — the stack that becomes the substrate for the rest of the course.

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                              | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | IaC landscape; CloudFormation substrate; read docs |    2h    |    1h     |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5h      |
| Tuesday   | CDK TS app: VPC + KMS S3 + Lambda; constructs       |    2h    |    2.5h   |     0h     |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | bootstrap + IAM; Python CDK parity; synth diff      |    1h    |    2.5h   |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6.5h    |
| Thursday  | OpenTofu equivalent; diff vs CloudFormation         |    1h    |    1.5h   |     1h     |    0.5h   |   1h     |     1.5h     |    0h      |     6.5h    |
| Friday    | LocalStack loop; sam local invoke; drift detection  |    0h    |    1h     |     1.5h   |    0.5h   |   1h     |     2h       |    0h      |     6h      |
| Saturday  | Mini-project deep work (the IaC starter)            |    0h    |    0h     |     0h     |    0h     |   0.5h   |     3h       |    0h      |     3.5h    |
| Sunday    | Quiz, cost report, reflection, polish               |    0h    |    0h     |     0h     |    1h     |   0h     |     1h       |    0.5h    |     2.5h    |
| **Total** |                                                    | **6h**   | **8.5h**  | **4.5h**   | **3.5h**  | **5.5h** | **11h**      | **1.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated, current (2026) docs, talks, and open-source for CDK / CloudFormation / OpenTofu / LocalStack |
| [lecture-notes/01-cdk-vs-opentofu-the-iac-landscape.md](./lecture-notes/01-cdk-vs-opentofu-the-iac-landscape.md) | Why CDK lost the open-source war but won the AWS one — and when to reach for OpenTofu instead |
| [lecture-notes/02-bootstrap-constructs-drift-and-the-substrate.md](./lecture-notes/02-bootstrap-constructs-drift-and-the-substrate.md) | `cdk bootstrap` and the chicken-and-egg IAM problem; L1/L2/L3 constructs; drift detection; the IaC substrate |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-cdk-ts-vpc-s3-lambda.md](./exercises/exercise-01-cdk-ts-vpc-s3-lambda.md) | Guided: write a TS CDK app (VPC + KMS S3 + Lambda) and deploy to `dev` |
| [exercises/exercise-02-python-cdk-parity.py](./exercises/exercise-02-python-cdk-parity.py) | Re-implement the identical stack in Python CDK; confirm template equivalence |
| [exercises/exercise-03-opentofu-equivalent.tf](./exercises/exercise-03-opentofu-equivalent.tf) | The equivalent stack in OpenTofu; diff against the CDK-synthesized template |
| [challenges/README.md](./challenges/README.md) | Index of the challenge |
| [challenges/challenge-01-localstack-sam-drift.md](./challenges/challenge-01-localstack-sam-drift.md) | Run the Lambda against LocalStack with `sam local invoke`; then catch real-AWS drift |
| [quiz.md](./quiz.md) | 14 questions with an answer key |
| [homework.md](./homework.md) | Concrete deliverables with a rubric |
| [mini-project/README.md](./mini-project/README.md) | The reusable IaC starter — TS CDK (primary) + Python CDK + OpenTofu + a LocalStack test loop |

## The substrate note

Read this carefully because it shapes the next twelve weeks.

The mini-project this week is not a throwaway. It is the **IaC scaffold every subsequent lab deploys through.** When Week 4 builds a production VPC, it extends the VPC construct you wrote this week. When Week 6 builds the S3 lifecycle lab, it extends the bucket. When Week 9's single-table DynamoDB lab needs a table, it lands in this repo. The capstone (Weeks 13–15) is deployed from a descendant of this exact monorepo. So spend the time. A sloppy scaffold this week is a tax you pay every week after.

## Cost discipline for this week

- **Default to LocalStack.** Your inner loop (synth, deploy, invoke, assert) runs against LocalStack for free. You deploy to real `dev` AWS at most a handful of times this week — to see real bootstrap, real drift, and a real CDK pipeline.
- **The stack you deploy is near-free.** A VPC with **no NAT Gateway** (we use no NAT this week deliberately — NAT is the silent budget killer from the Week 4 lecture), an S3 bucket, a KMS key (~$1/month prorated to pennies for a few days), and a Lambda well inside the free tier. Expect **well under $1** of real spend if you `cdk destroy` when you finish each day.
- **`cdk destroy` is part of the loop.** End every real-AWS session with `cdk destroy`. The KMS key has a deletion window (7 days minimum); that is fine — it stops billing immediately on schedule-for-deletion.
- A KMS customer-managed key costs **$1/month** while it exists. Three days of one key is about **$0.10**. That is the entire real cost of this week if you destroy nightly.

## Up next

Continue to **Week 4 — VPC, Networking & Edge** once you have pushed the mini-project IaC starter to your GitHub. Week 4 extends the VPC you build this week into a real three-AZ production VPC with endpoints — so the cleaner your scaffold, the easier Week 4 is.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
