# Week 3 — Resources

Everything linked here is **free** and **current as of 2026**. AWS docs are free without an account. OpenTofu and LocalStack docs are open. Open-source repos are public. No paywalled books are linked; where a book is worth owning, it is noted as optional.

## Required reading (work it into your week)

- **AWS CDK Developer Guide — Getting started** — the canonical entry point:
  <https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html>
- **AWS CDK — Concepts: Constructs, Apps, Stacks, Environments**:
  <https://docs.aws.amazon.com/cdk/v2/guide/core_concepts.html>
- **CDK bootstrapping** — read this before you bootstrap anything:
  <https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html>
- **CloudFormation — How does CloudFormation work** (the substrate):
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-whatis-concepts.html>
- **OpenTofu — Get started with AWS**:
  <https://opentofu.org/docs/intro/>
- **LocalStack — Getting started**:
  <https://docs.localstack.cloud/getting-started/>

## The CDK API reference (skim, then bookmark)

You will live in this. It is generated from `aws-cdk-lib` and is the authoritative source for every construct's props.

- **`aws-cdk-lib` v2 API reference**: <https://docs.aws.amazon.com/cdk/api/v2/>
- **`aws-s3` module** (the `Bucket` L2): <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3-readme.html>
- **`aws-kms` module** (the `Key` L2): <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_kms-readme.html>
- **`aws-ec2` module** (the `Vpc` L2): <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2-readme.html>
- **`aws-lambda` module** (the `Function` L2): <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda-readme.html>
- **`pipelines` module** (CDK Pipelines): <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.pipelines-readme.html>

## CloudFormation, for when the abstraction leaks

- **CloudFormation template anatomy**: <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-anatomy.html>
- **Intrinsic functions reference** (`Ref`, `Fn::GetAtt`, `Fn::Sub`): <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference.html>
- **Resource and property types reference** (what every `Cfn*` maps to): <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html>
- **Detecting unmanaged configuration changes (drift)**: <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html>
- **`DeletionPolicy` attribute** — the data-saving flag: <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-attribute-deletionpolicy.html>

## OpenTofu / Terraform

- **OpenTofu documentation home**: <https://opentofu.org/docs/>
- **OpenTofu CLI commands** (`init`, `plan`, `apply`, `state`): <https://opentofu.org/docs/cli/commands/>
- **Terraform AWS provider** (OpenTofu uses the same provider): <https://registry.terraform.io/providers/hashicorp/aws/latest/docs>
  - `aws_s3_bucket`, `aws_kms_key`, `aws_vpc`, `aws_lambda_function` resource pages — read the one you need.
- **OpenTofu state and backends** (why your laptop holds state, and how to move it to S3):
  <https://opentofu.org/docs/language/state/>
- **The OpenTofu manifesto** — why the fork exists (read once, for the design-review answer):
  <https://opentofu.org/manifesto/>

## SAM and local Lambda

- **AWS SAM CLI — Using `sam local`**: <https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local.html>
- **`sam local invoke`**: <https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-local-invoke.html>
- **SAM + CDK integration** (`sam local invoke` against a synthesized CDK template):
  <https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-cdk.html>

## Local emulation tooling

- **LocalStack — AWS service coverage** (what's emulated, what isn't): <https://docs.localstack.cloud/references/coverage/>
- **`cdklocal`** — CDK against LocalStack: <https://github.com/localstack/aws-cdk-local>
- **`tflocal` / `tofu` against LocalStack**: <https://github.com/localstack/terraform-local>
- **`awslocal`** — the AWS CLI pre-pointed at LocalStack: <https://github.com/localstack/awscli-local>
- **DynamoDB local** (AWS-published): <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html>
- **MinIO — the S3-compatible object store**: <https://min.io/docs/minio/container/index.html>

## Talks worth your time (free, no signup)

- **AWS re:Invent — "Best practices for AWS CDK"** (search the AWS Events YouTube channel for the latest year's session; the IaC track is updated annually): <https://www.youtube.com/@AWSEventsChannel>
- **"Infrastructure as Code on AWS"** — AWS re:Invent CON/DOP track, current year: search "re:Invent CDK best practices" on the channel above.
- **HashiConf / OpenTofu Day talks** — the OpenTofu project posts conference talks: <https://www.youtube.com/@opentofu>
- **LocalStack — "Develop and test AWS apps locally"** — the project's own channel: <https://www.youtube.com/@localstack>

## Open-source projects to read this week

You learn more from one hour reading a well-built CDK construct library than from three hours of tutorials. Pick one and scroll:

- **`aws/aws-cdk`** — the CDK itself, all the L2s; read `packages/aws-cdk-lib/aws-s3/lib/bucket.ts` to see how `grantRead` is implemented:
  <https://github.com/aws/aws-cdk>
- **`cdklabs/cdk-nag`** — a rules engine that lints your CDK app against AWS Well-Architected; we adopt it in Week 13:
  <https://github.com/cdklabs/cdk-nag>
- **`aws-samples/aws-cdk-examples`** — runnable example stacks in TS and Python:
  <https://github.com/aws-samples/aws-cdk-examples>
- **`opentofu/opentofu`** — the OpenTofu source: <https://github.com/opentofu/opentofu>
- **`localstack/localstack`** — the emulator source; the README alone is a tour of AWS service surface area: <https://github.com/localstack/localstack>

## Tools you'll use this week

- **AWS CLI v2** — `aws --version` should print 2.x. Install: <https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html>
- **Node.js 20+ and npm** — for the CDK CLI and TypeScript CDK. The CDK CLI installs via `npm i -g aws-cdk` or runs through `npx cdk`.
- **Python 3.12+ with `venv`** — for Python CDK (`aws-cdk-lib` from PyPI).
- **OpenTofu** — `brew install opentofu`; `tofu version`.
- **Docker** — required by LocalStack, MinIO, `sam local invoke`, and CDK asset bundling.
- **AWS SAM CLI** — `brew install aws-sam-cli`; `sam --version`.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **CloudFormation** | AWS's native, server-side deployment engine. Takes a template, manages a stack. The substrate. |
| **Stack** | A deployed instance of a template in one account + region. |
| **Change set** | The diff CloudFormation computes before applying. `cdk deploy` makes one under the hood. |
| **CDK** | A program (TS/Py/…) that synthesizes a CloudFormation template. `aws-cdk-lib` v2. |
| **Construct** | A node in the CDK tree. L1 (`Cfn*`), L2 (curated), L3 (patterns). |
| **`cdk synth`** | Run your CDK program; emit a CloudFormation template into `cdk.out/`. |
| **`cdk bootstrap`** | One-time setup of the CDKToolkit stack (staging bucket, ECR repo, deploy roles) per account+region. |
| **Token** | A CDK placeholder for a value that does not exist until deploy time. Never do string surgery on one. |
| **Logical ID** | The CloudFormation-side identifier CDK derives from a construct's tree path + hash. Renaming it can replace the resource. |
| **Drift** | The gap between what your IaC says is deployed and what is actually deployed. |
| **`grant*`** | L2 methods that write least-privilege IAM for you (`bucket.grantRead(fn)`). |
| **OpenTofu** | The open-source (MPL-2.0) fork of Terraform 1.5.x, maintained by the Linux Foundation. CLI: `tofu`. |
| **State file** | Terraform/OpenTofu's client-side mapping of code to real resource IDs. CDK has no equivalent — CloudFormation holds it server-side. |
| **LocalStack** | A container emulating many AWS services behind one endpoint (`localhost:4566`) for local dev. |
| **`sam local invoke`** | Runs a Lambda locally in a Docker container that mirrors the real Lambda runtime. |

---

*If a link 404s, please open an issue so we can replace it.*
