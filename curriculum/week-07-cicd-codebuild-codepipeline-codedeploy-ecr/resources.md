# Week 7 — Resources

Every AWS doc here is free and current as of 2026. The CDK API reference is generated from the source. The open-source projects are public on GitHub. AWS pricing pages change constantly; always re-check the dollar figure before you commit it to a design doc — the URLs below are stable, the numbers are not.

## Required reading (work it into your week)

- **AWS CodePipeline — User Guide (concepts: stages, actions, artifacts)**:
  <https://docs.aws.amazon.com/codepipeline/latest/userguide/welcome-introducing.html>
- **AWS CodeBuild — `buildspec` reference (the single most-referenced page this week)**:
  <https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html>
- **AWS CodeBuild — build caching (local cache modes and S3 cache)**:
  <https://docs.aws.amazon.com/codebuild/latest/userguide/build-caching.html>
- **AWS CodeDeploy — deployment configurations (canary, linear, all-at-once)**:
  <https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-configurations.html>
- **AWS CodeDeploy — blue/green deployments on Amazon ECS**:
  <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html>
- **AWS CodeDeploy — `AppSpec` file reference (ECS and Lambda sections)**:
  <https://docs.aws.amazon.com/codedeploy/latest/userguide/reference-appspec-file.html>
- **Amazon ECR — lifecycle policies**:
  <https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html>
- **Amazon ECR — image scanning (basic and enhanced via Inspector)**:
  <https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html>
- **Amazon ECR — pull-through cache rules**:
  <https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache.html>
- **CodeConnections (formerly CodeStar Connections) — connect to GitHub**:
  <https://docs.aws.amazon.com/dtconsole/latest/userguide/connections-create-github.html>
- **Configuring OpenID Connect in Amazon Web Services (GitHub Actions docs)**:
  <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services>
- **IAM — creating OIDC identity providers**:
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html>

## CDK API references (the ones you will keep open in a tab)

- **`aws-cdk-lib.aws_codepipeline` — module overview**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_codepipeline-readme.html>
- **`aws-cdk-lib.aws_codepipeline_actions` — the source/build/deploy actions**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_codepipeline_actions-readme.html>
- **`aws-cdk-lib.aws_codebuild` — `PipelineProject`, `BuildSpec`, `LinuxArmBuildImage`**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_codebuild-readme.html>
- **`aws-cdk-lib.aws_codedeploy` — `EcsDeploymentGroup`, `LambdaDeploymentGroup`, deployment configs**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_codedeploy-readme.html>
- **`aws-cdk-lib.aws_ecs_patterns.ApplicationLoadBalancedFargateService`**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs_patterns-readme.html>
- **`aws-cdk-lib.aws_ecr` — `Repository`, `LifecycleRule`, `TagMutability`**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecr-readme.html>
- **`aws-cdk-lib.aws_lambda` — `Version`, `Alias`, and the `currentVersion` pattern**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda-readme.html>
- **`aws-cdk-lib.pipelines` — CDK Pipelines (the self-mutating, higher-level construct)**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.pipelines-readme.html>

## Authoritative deep dives

- **AWS blog — "Build a continuous delivery pipeline for your container images with Amazon ECR as source"**:
  <https://aws.amazon.com/blogs/devops/build-a-continuous-delivery-pipeline-for-your-container-images-with-amazon-ecr-as-source/>
- **AWS blog — "Deploying to Amazon ECS with GitHub Actions" (OIDC pattern, current)**:
  <https://aws.amazon.com/blogs/containers/deploying-to-amazon-elastic-container-service-with-github-actions/>
- **AWS Well-Architected — Operational Excellence pillar (deployment safety, rollback)**:
  <https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html>
- **AWS Prescriptive Guidance — CI/CD strategy and pipeline best practices**:
  <https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-cicd-litmus/welcome.html>
- **Docker docs — `docker buildx` and multi-platform images**:
  <https://docs.docker.com/build/building/multi-platform/>
- **Docker docs — `buildx imagetools create` (joining per-arch images into one manifest list)**:
  <https://docs.docker.com/reference/cli/docker/buildx/imagetools/create/>
- **AWS — "Building and deploying multi-architecture container images" (ECS dev guide)**:
  <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/build-and-deploy-multi-arch.html>

## Graviton / arm64 cost references

- **AWS Graviton — getting started and the cost/performance claims**:
  <https://aws.amazon.com/ec2/graviton/>
- **AWS Fargate pricing (per-vCPU-hour and per-GB-hour, x86 vs arm64)**:
  <https://aws.amazon.com/fargate/pricing/>
- **AWS Graviton Technical Guide (the open-source porting + benchmarking handbook)**:
  <https://github.com/aws/aws-graviton-getting-started>

> The number you will quote in your cost report: as of 2026, Fargate on arm64 (Graviton) is priced roughly **20% lower per vCPU-hour** than the equivalent x86 Fargate task, before accounting for arm64's frequently-better perf-per-vCPU on memory-bound and throughput workloads. Confirm the current per-vCPU-hour figures on the pricing page for your region before you put a dollar number in a design doc.

## Security: the pipeline-as-target reading

- **AWS — "Security best practices for CodeBuild"**:
  <https://docs.aws.amazon.com/codebuild/latest/userguide/security-best-practices.html>
- **AWS — "Security best practices for CodePipeline"**:
  <https://docs.aws.amazon.com/codepipeline/latest/userguide/security-best-practices.html>
- **IAM — permissions boundaries (the only safe way to delegate the pipeline role)**:
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html>
- **IAM — the confused-deputy problem and `aws:SourceArn` / `aws:SourceAccount`**:
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html>
- **AWS KMS — key policies (the actual boundary on a cross-account artifact bucket)**:
  <https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html>
- **GitHub — security hardening for OIDC (subject claim customization)**:
  <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect>
- **Supply-chain attack literature** — search for recent (2024–2025) write-ups on poisoned-pipeline-execution (PPE) and the CodeCov / SolarWinds class of supply-chain attacks. The threat model in Lecture 1 is built on this literature; the OWASP "Top 10 CI/CD Security Risks" page is the best single index.

## Official action / tool references

- **`aws-actions/configure-aws-credentials` (the OIDC credential exchange action)**:
  <https://github.com/aws-actions/configure-aws-credentials>
- **`aws-actions/amazon-ecr-login`**:
  <https://github.com/aws-actions/amazon-ecr-login>
- **`aws-actions/amazon-ecs-deploy-task-definition` (used in the OIDC challenge)**:
  <https://github.com/aws-actions/amazon-ecs-deploy-task-definition>
- **`docker/setup-buildx-action` and `docker/build-push-action`**:
  <https://github.com/docker/build-push-action>
- **AWS CLI v2 command reference — `ecs`, `ecr`, `codedeploy`, `codepipeline`**:
  <https://docs.aws.amazon.com/cli/latest/reference/>

## OpenTofu / Terraform cross-tool references

This course is vendor-aware. The same pipeline expressed in OpenTofu is a useful comparison — it makes the IAM surface explicit in a way CDK's auto-generated roles hide.

- **OpenTofu — registry and provider docs (the AWS provider mirrors Terraform's)**:
  <https://opentofu.org/docs/>
- **Terraform AWS provider — `aws_codepipeline`**:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/codepipeline>
- **Terraform AWS provider — `aws_codebuild_project`**:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/codebuild_project>
- **Terraform AWS provider — `aws_codedeploy_deployment_group`**:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/codedeploy_deployment_group>
- **Terraform AWS provider — `aws_iam_openid_connect_provider`**:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_openid_connect_provider>

## Talks worth watching (all free, no account)

- **AWS re:Invent — "Best practices for CI/CD using AWS" (DOP track)** — search YouTube for "re:Invent CI/CD best practices DOP". The annual DOP-track deployment talks are the canonical AWS-shop material.
- **AWS re:Invent — "Advanced continuous delivery best practices"** — search YouTube for "re:Invent advanced continuous delivery deployment safety".
- **AWS re:Invent — "Deploying with confidence: blue/green and canary deployments"** — search YouTube for "re:Invent blue green canary deployment".
- **GitHub Universe — "Secure deployments to AWS with OIDC"** — search YouTube for "GitHub Actions OIDC AWS".
- **AWS re:Invent — "Save up to 20% with Graviton: a migration deep dive"** — search YouTube for "re:Invent Graviton migration savings".

## How to use this resource list

The lectures cite specific URLs from this page at decision points. The links you should read end-to-end *this* week are:

1. **CodeBuild `buildspec` reference** — you will write three buildspecs; read it twice.
2. **CodeDeploy deployment configurations** — the canary/linear vocabulary is load-bearing for the whole week.
3. **CodeDeploy blue/green on ECS** — the target-group-swap mental model is the thing students get wrong.
4. **GitHub OIDC in AWS (both the GitHub doc and the IAM OIDC-provider doc)** — decisive for the challenge.
5. **IAM permissions boundaries** — the spine of Lecture 1.

The rest are reference material — bookmark them and return when a specific question arises. Even senior engineers re-read the `AppSpec` reference every time they touch a CodeDeploy config; do not feel you must memorize it.

---

*Bookmarks decay. If an AWS doc URL 404s, the doc almost certainly still exists under a renamed path — search the page title from the AWS Documentation landing page and you will find it.*
