# Week 7 — CI/CD on AWS: CodeBuild, CodePipeline, CodeDeploy, and ECR with Safety Rails

Welcome to **C19 · Crunch AWS**, Week 7. This is the last week of Phase 2 — Compute, Network & Storage — and it is the week where everything you have built so far stops being a thing you `cdk deploy` from your laptop and becomes a thing that ships *itself*, on every commit, with a rollback path you can defend in an incident review. Week 4 gave you the VPC. Week 5 gave you the compute spectrum: EC2, ECS Fargate, EKS, Lambda. Week 6 gave you the storage layer. This week we wire a delivery pipeline that takes a Git push and turns it into a running, health-checked, automatically-rollable deployment of a container onto ECS Fargate — and the sibling Lambda function next to it — with **zero long-lived credentials anywhere a human can copy them**.

The single conviction that organizes this week is the one in the lecture title: **your pipeline IAM role is more dangerous than your production IAM role.** A production role can read a database and write to a queue. A pipeline role can *replace the code that reads the database and writes to the queue* — and it can do it across every environment you let it touch, without a human in the loop, with the full trust of your deploy automation. If an attacker phishes a developer's GitHub PAT and you have wired that PAT to a CodeBuild project with `AdministratorAccess`, the attacker now ships whatever they want to production and the audit trail says "the pipeline did it." Most teams get this exactly backwards: they lock down the prod role to least privilege, then hand the CI system a wildcard. We will not do that. We will treat the pipeline as the highest-value target it actually is, scope its role down to the resources it deploys, gate cross-account artifact movement behind KMS grants, and federate GitHub into AWS with OIDC so there is no static key to steal in the first place.

The second conviction is about **deployment discipline**. In-place deployment — stop the old task, start the new task, hope — is how you take an outage with your own hands. Blue/green deployment stands up the new version *beside* the old one, shifts a slice of traffic (a 10% canary) to it, watches a CloudWatch alarm for the duration of a bake window, and either promotes to 100% or rolls back to the untouched blue fleet automatically. The new code never sees more than 10% of traffic until it has *proven* it is healthy. CodeDeploy gives you this for ECS and for Lambda with the same mental model — a deployment group, a traffic-shifting config (canary, linear, all-at-once), and an alarm that, if it fires, reverts the shift. By Friday you will have a pipeline that does a 10% ECS canary with auto-rollback and a linear Lambda traffic shift, and you will have deliberately broken a deploy to watch the rollback fire.

The third conviction is **vendor-aware, not vendor-loyal**, the same posture this whole course takes. AWS-native CodePipeline + CodeBuild + CodeDeploy is a coherent, deeply-integrated delivery stack — and most teams in 2026 run their CI on GitHub Actions instead, federating into AWS with OIDC and using CodeDeploy (or a raw `aws ecs update-service`) only for the deploy step. We will build the AWS-native flow end to end *and* the GitHub Actions OIDC equivalent, then compare them honestly on security, cost, and operability. You will leave knowing which trade-off you took and why, which is the only kind of knowing that survives a design review.

This delivery flow is not a throwaway lab. **It is the CI that ships the capstone monorepo.** The pipeline you build this week — GitHub-triggered build, multi-arch ECR push, blue/green ECS deploy with canary and auto-rollback, plus the GitHub Actions OIDC equivalent — is the same machinery you will use in Weeks 13–15 to deploy the Event-Driven SaaS Backbone. Build it well now; you will live with it for the rest of the course.

## Learning objectives

By the end of this week, you will be able to:

- **Author** a CodeBuild `buildspec.yml` that runs lint and test phases, logs in to ECR, and builds a container image — with local and S3 build caching configured so incremental builds are fast.
- **Build** multi-architecture container images (`linux/amd64` + `linux/arm64`) with `docker buildx` inside CodeBuild and publish a single multi-arch manifest to ECR, so the same image tag runs on Graviton (arm64) for ~20% compute savings and on x86 where you still need it.
- **Compose** a CodePipeline with a GitHub source (via the CodeStar Connections / CodeConnections app, not a webhook PAT), parallel `lint` and `test` actions, a `build` stage, a manual-approval gate, and a `deploy` stage — defined in CDK so the whole pipeline is reproducible.
- **Configure** ECR repositories with lifecycle policies (expire untagged images after N days, keep the last N tagged images), scan-on-push (basic and enhanced via Amazon Inspector), and a pull-through cache rule for upstream public registries.
- **Distinguish** CodeDeploy in-place from blue/green deployment, and configure an ECS blue/green deployment group with a `Canary10Percent5Minutes` traffic-shifting config and a CloudWatch alarm that triggers automatic rollback.
- **Configure** Lambda traffic shifting (canary and linear) with CodeDeploy, aliases, and pre/post-traffic hooks, and roll a sibling Lambda function in the same pipeline as the ECS service.
- **Reason** about the pipeline IAM role as the highest-value principal in the account: scope it to the resources it deploys, use permission boundaries, gate cross-account artifact buckets behind KMS key policies, and never attach `AdministratorAccess`.
- **Federate** GitHub Actions into AWS with an OIDC identity provider and a `sts:AssumeRoleWithWebIdentity` trust policy scoped to `repo:org/name:ref:refs/heads/main`, eliminating long-lived access keys entirely.
- **Compare** the AWS-native delivery flow against the GitHub Actions + OIDC flow on three axes — security (blast radius, credential model, audit trail), cost (CodeBuild minutes vs GitHub-hosted runners, NAT and data-transfer), and operability (where the logs live, how you debug a failed deploy, who owns the YAML).
- **Cite** the AWS service docs, the CDK API reference, and the OIDC federation guidance that justify each decision.

## Prerequisites

- **Weeks 1 through 6 of C19 complete.** You have a multi-account Organization with IAM Identity Center (Week 1–2), you can read and write IAM policies and permission boundaries (Week 2), you have a CDK app that you `cdk bootstrap`-ed and `cdk deploy`-ed (Week 3), you have a production-shape VPC with VPC endpoints for ECR API, ECR DKR, S3, and CloudWatch Logs (Week 4), and you have containerized a service and run it on ECS Fargate behind an ALB (Week 5).
- **A working `aws --version` of `2.x`** on your PATH, authenticated via `aws sso login` to your `dev` account with a role that can create CodePipeline, CodeBuild, CodeDeploy, ECR, IAM, and CloudWatch resources.
- **Node 20+ and the AWS CDK v2 CLI** (`npm i -g aws-cdk`, targeting `aws-cdk-lib` `2.150.0` or later). Python 3.12+ if you do the Python-CDK variants.
- **Docker with `buildx`** available locally (Docker Desktop 4.x or Colima with the containerd image store) so you can reproduce the multi-arch build locally before pushing it into CodeBuild.
- **A GitHub account and a repository you control.** The exercises trigger pipelines from GitHub; you need push access and the ability to install the AWS Connector for GitHub (the CodeConnections GitHub App) on the repo or org.
- **Familiarity with ECS Fargate task definitions, services, and ALB target groups from Week 5.** Blue/green on ECS swaps target groups behind a listener; if "target group" and "listener rule" are not yet reflexes, re-read the Week 5 lab before starting.

## Topics covered

- **CodeCommit, and why you probably will not use it.** AWS's managed Git. Functional, integrated, and almost universally passed over in favor of GitHub or GitLab. We cover *why* (developer-experience gravity, the PR review surface, the ecosystem) and when CodeCommit still makes sense (air-gapped accounts, FedRAMP boundaries where GitHub is not authorized).
- **CodeBuild — the build environment.** `buildspec.yml` phases (`install`, `pre_build`, `build`, `post_build`), environment variables and secrets via Secrets Manager / SSM Parameter Store, compute types (`BUILD_GENERAL1_SMALL` through `2XLARGE`, and the arm64 / Graviton build images), build caching (local cache modes — `DOCKER_LAYER`, `SOURCE`, `CUSTOM` — and S3 cache), and the `reports` section for test reports.
- **Multi-architecture builds.** `docker buildx build --platform linux/amd64,linux/arm64`, the manifest-list (fat manifest) that lets one tag serve both architectures, why Graviton (arm64) is ~20% cheaper per vCPU-hour on Fargate, and the two strategies for building multi-arch in CI: a single emulated build (slow, QEMU) vs a matrix of native builders joined with `buildx imagetools create` (fast, the production choice).
- **CodePipeline — the orchestrator.** Sources (CodeConnections for GitHub, S3, ECR), stages and actions, parallel actions (run-order), input/output artifacts and the artifact bucket, manual approval actions (with SNS notification), and variables passed between stages. CDK's `aws-codepipeline` and the higher-level `pipelines.CodePipeline` (CDK Pipelines) construct.
- **CodeDeploy — in-place vs blue/green.** The deployment models: in-place (EC2/on-prem only), blue/green for ECS (swap target groups), and blue/green for Lambda (shift alias traffic). Deployment configurations: `AllAtOnce`, `Canary10Percent5Minutes`, `Canary10Percent30Minutes`, `Linear10PercentEvery1Minute`, `Linear10PercentEvery3Minutes`. The `AppSpec` file. Lifecycle hooks. Automatic rollback on alarm or on failed deployment.
- **ECS blue/green specifics.** The deployment controller (`CODE_DEPLOY` vs `ECS` rolling vs `EXTERNAL`), the two target groups (blue and green) behind one ALB listener, the test listener for validation traffic, the production listener for the canary shift, and the `DeploymentConfiguration` choices in the service stack.
- **Lambda traffic shifting.** Versions and aliases, the `CodeDeployDefault.LambdaCanary10Percent5Minutes` config, pre-traffic and post-traffic Lambda hooks (smoke tests that gate the shift), and how CDK's `aws-codedeploy.LambdaDeploymentGroup` + `lambda.Alias` wire it together.
- **ECR — the registry.** Repository creation, image tag mutability (`IMMUTABLE` for production), lifecycle policies (expire untagged after N days, keep last N by tag prefix), scan-on-push (basic CVE scan vs enhanced scanning via Amazon Inspector), and pull-through cache rules (mirror Docker Hub / ECR Public / Quay through your private registry to dodge rate limits and centralize scanning).
- **Cross-account artifact buckets and KMS.** Why a multi-account pipeline needs a shared, KMS-encrypted artifact bucket; the bucket policy and KMS key policy that let the deploy account decrypt; and why the KMS key policy is the actual security boundary, not the bucket policy.
- **GitHub Actions OIDC federation.** The GitHub OIDC provider (`token.actions.githubusercontent.com`), the IAM OIDC identity provider, the trust policy scoped by `sub` claim (`repo:org/name:ref:...`, `repo:org/name:environment:prod`), `aws-actions/configure-aws-credentials@v4`, and why this beats `AWS_ACCESS_KEY_ID` secrets in every dimension that matters.

## Weekly schedule

The schedule adds up to approximately **36 hours**. Treat it as a target, not a contract. CI/CD work has a lot of "wait for the deploy" idle time; use it to read the lecture notes and the cited docs rather than refreshing the console.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Pipeline IAM threat model; CodeConnections; ECR + lifecycle |   2h     |   1.5h    |    0h      |   0.5h    |   1h     |     0h       |    0.5h    |    5.5h     |
| Tuesday   | CodeBuild buildspec, caching, multi-arch buildx; Exercise 1 |   2h     |   2h      |    0h      |   0.5h    |   1h     |     0h       |    0.5h    |    6h       |
| Wednesday | CodeDeploy blue/green on ECS; canary + alarm; Exercise 2    |   1.5h   |   2h      |    0h      |   0.5h    |   1h     |     0h       |    0.5h    |    6h       |
| Thursday  | Lambda traffic shifting; Exercise 3; start the challenge    |   0.5h   |   1.5h    |    2h      |   0.5h    |   1h     |     1h       |    0.5h    |    7h       |
| Friday    | GitHub Actions OIDC challenge; mini-project build           |   0h     |   0h      |    1.5h    |   0.5h    |   1h     |     3h       |    0.5h    |    6.5h     |
| Saturday  | Mini-project deep work, rollback drill, comparison writeup  |   0h     |   0h      |    0h      |   0h      |   0h     |     3h       |    0h      |    3h       |
| Sunday    | Quiz, review, cost report, polish                          |   0h     |   0h      |    0h      |   1h      |   0h     |     1h       |    0h      |    2h       |
| **Total** |                                                            | **6h**   | **7h**    | **3.5h**   | **4h**    | **5h**   | **11h**      | **2.5h**   | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | AWS service docs, CDK API references, the CodeConnections / OIDC guidance, the Graviton cost data, and the talks to watch |
| [lecture-notes/01-your-pipeline-role-is-more-dangerous.md](./lecture-notes/01-your-pipeline-role-is-more-dangerous.md) | The pipeline IAM threat model end to end: blast radius, scoping the CodeBuild/CodePipeline/CodeDeploy roles, permission boundaries, cross-account artifact buckets, KMS as the real boundary, and CodeConnections vs PAT |
| [lecture-notes/02-blue-green-discipline-ecs-lambda-oidc.md](./lecture-notes/02-blue-green-discipline-ecs-lambda-oidc.md) | Blue/green discipline: ECS deployment groups, canary + alarm + auto-rollback, Lambda versions/aliases/traffic shifting, and the GitHub Actions OIDC alternative with a head-to-head comparison |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-github-pipeline-multiarch-ecr.md](./exercises/exercise-01-github-pipeline-multiarch-ecr.md) | Guided: build a CodePipeline triggered by GitHub that runs lint → test → a CodeBuild multi-arch container build → push to ECR. Steps, starter + solution CDK, expected output |
| [exercises/exercise-02-ecs-blue-green-canary.ts](./exercises/exercise-02-ecs-blue-green-canary.ts) | Runnable CDK (TypeScript): add a CodeDeploy blue/green deploy onto ECS Fargate with a 10% canary and automatic rollback on a CloudWatch alarm |
| [exercises/exercise-03-lambda-traffic-shifting.py](./exercises/exercise-03-lambda-traffic-shifting.py) | Runnable CDK (Python): add Lambda traffic shifting (canary/linear) for a sibling Lambda function in the same pipeline, with a pre-traffic smoke-test hook |
| [challenges/README.md](./challenges/README.md) | Index of the challenge |
| [challenges/challenge-01-github-actions-oidc-replication.md](./challenges/challenge-01-github-actions-oidc-replication.md) | Replicate the entire delivery flow with GitHub Actions + OIDC federation (no long-lived keys) and write the two-approach comparison |
| [mini-project/README.md](./mini-project/README.md) | Full spec for the safety-rail pipeline that ships the capstone monorepo: GitHub-triggered build → multi-arch ECR push → blue/green ECS deploy with canary and auto-rollback, plus the OIDC equivalent |
| [quiz.md](./quiz.md) | 13 questions on buildspec, multi-arch, CodeDeploy configs, ECR lifecycle, pipeline IAM, and OIDC |
| [homework.md](./homework.md) | Six practice problems with deliverables and a rubric |

## The "the deploy rolled back on its own" promise

Most CI/CD courses end at "the pipeline turned green." That is the easy half. This week we treat a *successful rollback* as a first-class deliverable: **every student deliberately ships a broken build and proves the canary alarm fired and CodeDeploy reverted to blue without a human touching the console.** A deploy you cannot roll back is a deploy you should not have shipped. The phrase "we'll roll forward with a hotfix" is what you say when you did not build the rollback; the phrase "the alarm fired at 14:03, the deployment auto-rolled-back at 14:04, blue was never impacted" is what you say when you did. Practice the second this week.

## A note on what's not here

Week 7 introduces CI/CD on AWS with safety rails. It does **not** introduce:

- **Argo Rollouts / Flagger on EKS.** Progressive delivery on Kubernetes is a real and excellent pattern (we mention it in the EKS context in Week 5's notes), but it lives inside the cluster with a different controller model. CodeDeploy is the AWS-native ECS/Lambda path; the EKS progressive-delivery deep dive is an elective.
- **Full GitOps (Flux / ArgoCD) reconciliation.** Pull-based GitOps is a legitimate alternative to push-based pipelines. We are building push-based delivery this week because it maps cleanly onto CodePipeline and onto the most common GitHub Actions pattern. GitOps is a Week-13-adjacent topic for the EKS workloads.
- **Spinnaker, Harness, Octopus, or other third-party CD platforms.** All viable; all out of scope. We compare exactly two delivery models — AWS-native and GitHub Actions + OIDC — because those are the two you will actually be asked to choose between in an AWS shop.
- **Database migration orchestration in the pipeline.** Running schema migrations as a deploy step (with the expand/contract pattern) is critical production practice and it gets its own treatment in Week 8 (RDS/Aurora). This week's pipeline ships stateless code; the data layer comes next week.
- **Canary analysis with statistical confidence (CloudWatch Evidently, automated canary scoring).** We gate on a single CloudWatch alarm this week — a binary "is the error rate above threshold" check, which is the right starting point. Automated canary *analysis* (comparing baseline vs canary metrics statistically) is a Week 12 observability topic.

## Up next

Continue to **Week 8 — Relational: RDS, Aurora, Aurora Serverless v2** once your mini-project pipeline ships a blue/green ECS deploy with auto-rollback and you have the OIDC equivalent working. Week 8 adds the data layer the pipeline has been deploying *around* — and it introduces the migration-in-the-pipeline pattern (expand/contract, online schema change) that turns the stateless pipeline you built this week into one that can also evolve a database without downtime. The safety-rail habits you build this week — canary, bake window, alarm-gated rollback — are exactly the habits a zero-downtime migration depends on.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
