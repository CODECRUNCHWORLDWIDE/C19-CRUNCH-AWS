# Mini-Project — The Safety-Rail Pipeline: the CI that ships the capstone

> Deliver a working, production-shaped delivery pipeline: a push to GitHub `main` triggers a build that lints, tests, produces a multi-architecture container image, pushes it to ECR, and does a **blue/green deploy onto ECS Fargate with a 10% canary and automatic rollback on a CloudWatch alarm** — plus a sibling Lambda's traffic shifting in the same flow. Then deliver the **GitHub Actions + OIDC equivalent** of the same outcome, with no long-lived credentials. By the end you have a pipeline anyone on a production team would recognize, and you can defend every safety rail in it.

This is not a throwaway lab. **This delivery flow is the CI used to deploy the capstone monorepo.** The pipeline you build this week is the same machinery you will use in Weeks 13–15 to ship the Event-Driven SaaS Backbone — GitHub-triggered build, multi-arch ECR push, blue/green ECS deploy with canary and auto-rollback. The capstone's CDK monorepo (per the syllabus) deploys on GitHub Actions with OIDC federation into AWS; the OIDC half of this mini-project is literally that pipeline, scaled down to one service. Build it well now. You will not rebuild it in Week 13; you will *extend* it.

**Estimated time:** ~11 hours (split across Thursday, Friday, Saturday, Sunday in the suggested schedule).

---

## What you will build

A single application repo on GitHub and a CDK app that, together, give you **two complete delivery paths to the same running service**:

### Path A — AWS-native (CodePipeline)

1. **Source** — GitHub `main`, via a CodeConnections connection (no PAT).
2. **Verify** — parallel CodeBuild lint + test actions; either failing fails the stage.
3. **Build** — a CodeBuild project that builds `linux/amd64` + `linux/arm64` with `buildx`, pushes a single multi-arch manifest to ECR (immutable tags, lifecycle policy, scan-on-push), and emits the deploy artifacts.
4. **Approve** — a manual approval gate with SNS notification (so a human signs off before prod).
5. **Deploy (ECS)** — a CodeDeploy blue/green onto ECS Fargate: two target groups, one listener, `Canary10Percent5Minutes`, a 5XX alarm and a p99-latency alarm as rollback triggers.
6. **Deploy (Lambda)** — a sibling `order-event-handler` Lambda whose alias gets `Canary10Percent5Minutes` traffic shifting, gated by a pre-traffic smoke-test hook and an Errors alarm.

### Path B — GitHub Actions + OIDC

A `.github/workflows/deploy.yml` that reproduces lint → test → multi-arch build → ECR push → CodeDeploy blue/green, authenticating into AWS purely via an OIDC role scoped to `repo:<owner>/<repo>:ref:refs/heads/main`. **No stored AWS keys.** This is the half that becomes the capstone's CI.

You ship **one solution** with a CDK monorepo and one application repo:

- `infra/` — the CDK app (TypeScript primary; the Lambda canary stack in Python per the syllabus's "one stack in Python" rule).
  - `infra/lib/ecr-stack.ts` — the ECR repo with lifecycle, immutability, scan-on-push, and a pull-through cache rule.
  - `infra/lib/pipeline-stack.ts` — Path A: the CodePipeline (source, verify, build, approve, deploy).
  - `infra/lib/ecs-bluegreen-stack.ts` — the ECS service (CODE_DEPLOY controller), ALB, two target groups, alarms, the EcsDeploymentGroup.
  - `infra/order_pipeline/lambda_canary_stack.py` — the sibling Lambda, alias, pre-traffic hook, LambdaDeploymentGroup (Python).
  - `infra/lib/github-oidc-stack.ts` — Path B: the OIDC provider and the scoped deploy role.
- `app/` (in the application repo) — the FastAPI service, `Dockerfile`, the three buildspecs, and `.github/workflows/deploy.yml`.

---

## Rules

- **You may** read AWS docs, the CDK API reference, the lecture notes, your Week 7 exercises, and the AWS/GitHub OIDC guidance.
- **You may NOT** store any long-lived AWS credential in GitHub. The OIDC path must use `AssumeRoleWithWebIdentity`. A stored `AWS_ACCESS_KEY_ID` is an automatic fail of the security rubric.
- **You may NOT** attach `AdministratorAccess` or any `*FullAccess` managed policy to the build, deploy, or pipeline roles. Scope per Lecture 1.
- The container image **must** be multi-arch (`linux/amd64` + `linux/arm64`); the ECS task and the Lambda **must** run on arm64 (Graviton) to bank the cost saving.
- Every role created by the CDK app **must** carry the permission boundary from Lecture 1 (§1.3), applied at the `App` level via an Aspect.
- Target frameworks: `aws-cdk-lib` ≥ `2.150.0`, Node 20+, Python 3.12+, AWS CLI v2.
- The ECS deploy **must** be blue/green with a canary and a real CloudWatch-alarm rollback trigger — not an ECS rolling deploy, not all-at-once.
- **The rollback must be proven, not asserted.** You ship a deliberately-broken build and capture the CodeDeploy events showing the automatic rollback to blue. A pipeline whose rollback you have not demonstrated does not pass.

---

## Acceptance criteria

The grading rubric is below. Each box maps to a deliverable.

### Path A — AWS-native pipeline (35%)

- [ ] A CodePipeline triggers on push to `main` via CodeConnections (no PAT in the account).
- [ ] Lint and test run as parallel actions; a failure in either fails the stage before any build.
- [ ] The build produces a multi-arch ECR image (`artifactMediaType` = `manifest.list`); `buildx imagetools inspect` shows both architectures.
- [ ] The ECR repo has immutable tags, a lifecycle policy (expire untagged 7d, keep 20 release), scan-on-push, and a pull-through cache rule for the base image.
- [ ] A manual-approval action with SNS notification gates the deploy stage.
- [ ] The ECS service uses the `CODE_DEPLOY` controller; the deploy is blue/green with `Canary10Percent5Minutes` and at least one alarm rollback trigger.
- [ ] The sibling Lambda deploys with canary traffic shifting, a pre-traffic hook, and an Errors alarm.

### Path B — GitHub Actions + OIDC (25%)

- [ ] An IAM OIDC provider for GitHub and a deploy role scoped by `aud` and `sub` (repo + branch or repo + environment).
- [ ] The workflow has `permissions: id-token: write` and uses `aws-actions/configure-aws-credentials@v4` with no stored AWS keys.
- [ ] A push to `main` runs the full lint → test → multi-arch build → ECR push → CodeDeploy blue/green flow.
- [ ] A push from a non-`main` branch (or a fork PR) is **denied** the role assume — you captured the proof.

### Security (20%)

- [ ] The build, deploy, and pipeline roles are each scoped to their job; `cdk synth` shows no unexplained `Resource: "*"`.
- [ ] `iam:PassRole` is scoped to the two task roles with the `iam:PassedToService` condition.
- [ ] The permission boundary is applied at the `App` level and denies IAM escalation, `*FullAccess` attachment, and destructive KMS actions.
- [ ] If the pipeline is cross-account, the artifact bucket uses a CMK and the KMS key policy (not just the bucket policy) grants the deploy account decrypt.

### The rollback drill + documentation (20%)

- [ ] You shipped a deliberately-broken build and captured the CodeDeploy deployment events showing the canary alarm firing and the automatic rollback to blue (timestamps included).
- [ ] You captured the Lambda pre-traffic-hook abort (deploy aborted before any traffic) *and* the alarm-triggered rollback (after 10% flowed) — two distinct failure modes.
- [ ] `README.md` at the solution root: a one-paragraph description, the architecture diagram (Path A and Path B), the multi-arch verification output, and the rollback evidence.
- [ ] `comparison.md`: a 600–900-word comparison of Path A vs Path B on security, cost, and operability (the challenge's writeup, expanded), ending with which you would put the capstone on and why.
- [ ] A `cost.md`: the actual dollar figure for one week of running this pipeline (CodeBuild minutes, CodePipeline, ALB, Fargate, ECR storage), with the arm64-vs-x86 Fargate delta called out.

---

## Suggested implementation outline

The order matters. Build Path A first (you already have the pieces from the exercises), prove the rollback, then add Path B, then write the comparison.

### Day 1 (Thursday — ~1 hour, alongside Exercise 3)

1. Scaffold the CDK monorepo: `cdk init app --language typescript` in `infra/`, add the Python Lambda stack via the standard CDK polyglot pattern (a Python construct deployed by the same app, or a separate `cdk.json` app — the syllabus only requires one stack be Python).
2. Apply the Lecture-1 permission boundary at the `App` level with an Aspect. Do this *first* so every role you create afterward inherits it.
3. Stand up the `EcrStack` (from Exercise 1, plus the pull-through cache rule).

### Day 2 (Friday — ~3 hours)

4. Assemble the `PipelineStack` (Exercise 1) — source, verify (parallel lint/test), build (multi-arch). Deploy it and confirm a push produces a multi-arch image.
5. Add the `EcsBlueGreenStack` (Exercise 2) and wire the `Approve` + `Deploy` stages onto the pipeline with `CodeDeployEcsDeployAction`.
6. Add the Lambda canary stack (Exercise 3) and a second deploy action (or a parallel action in the deploy stage) for the sibling function.
7. Run the whole pipeline green once with a healthy build. Capture the multi-arch verification and a clean deploy.

### Day 3 (Saturday — ~3 hours)

8. **The rollback drill.** Ship a build whose `/health` returns 500. Watch the canary take 10%, the 5XX alarm fire, CodeDeploy revert to blue. Capture `aws deploy get-deployment` showing `Stopped` + `rollbackInfo`. Then do the Lambda drills: a pre-traffic-hook abort and an alarm rollback.
9. Build Path B: the `GithubOidcStack` (OIDC provider + scoped role) and `.github/workflows/deploy.yml`. Prove no stored credential and prove the non-`main` denial.
10. Reconcile: both paths produce the same multi-arch image and hand the same CodeDeploy deployment group the same blue/green canary. Confirm they are interchangeable.

### Day 4 (Sunday — ~1 hour)

11. Write `README.md`, `comparison.md`, and `cost.md`. Pull the real dollar figures from Cost Explorer (or estimate from the pricing pages and your build-minute counts). Push everything.

---

## Architecture (Path A, the AWS-native flow)

```
 GitHub main ──push──▶ CodeConnections ──▶ CodePipeline
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼ Verify            ▼ Build              ▼ Approve ──▶ Deploy
                    ┌───────────┐       ┌──────────────┐                   │
                    │ Lint (CB) │       │ CodeBuild     │                   ▼
                    │ Test (CB) │       │ buildx        │           ┌──────────────────┐
                    └───────────┘       │ amd64 + arm64 │           │ CodeDeploy        │
                     (parallel)         │ push to ECR   │           │ ECS blue/green    │
                                        └──────┬────────┘           │  blue-tg ◀ listener│
                                               │                    │  green-tg          │
                                          ┌────▼─────┐              │  Canary10%5min     │
                                          │   ECR    │              │  5XX alarm ─▶ROLLBK│
                                          │ immutable│              └─────────┬──────────┘
                                          │ lifecycle│                        │
                                          │ scan     │              ┌─────────▼──────────┐
                                          └──────────┘              │ Lambda alias shift │
                                                                    │ canary + pretraffic│
                                                                    └────────────────────┘
```

Path B replaces the left two columns (CodeConnections + CodePipeline + CodeBuild) with GitHub Actions runners authenticated via OIDC, and keeps the entire right side (ECR + CodeDeploy blue/green + Lambda shift) unchanged.

---

## Hints

- **Build Path A from the exercises; do not start from scratch.** Exercises 1–3 are the three stacks; the mini-project is mostly wiring them together and adding the approval gate, the pull-through cache, and the OIDC path.
- **The `imageDetail.json` / `taskdef.json` / `appspec.yaml` handoff is fiddly.** The build's `artifacts.files` must include all three; the `CodeDeployEcsDeployAction` reads them. If the deploy action complains about a missing file, your buildspec's `artifacts` block is the first place to look.
- **arm64 everywhere.** The CodeBuild *host* is arm64 (native arm64 build, emulated amd64), the ECS task `runtimePlatform` is `ARM64`, and the Lambda `architecture` is `ARM_64`. Verify each independently; a Lambda accidentally left on x86 is silently more expensive.
- **The pre-traffic hook needs `codedeploy:PutLifecycleEventHookExecutionStatus`** to report its result. If the hook runs but the deploy hangs at the hook step, the hook almost certainly cannot report back — check its role.
- **Prove the rollback before you write the README.** The README's rollback evidence is the deliverable that separates "I built a pipeline" from "I built a pipeline I understand." Capture the timestamps.
- **The OIDC `sub` denial proof is easy to skip and easy to grade.** Push from a feature branch, show the `AssumeRoleWithWebIdentity` `AccessDenied` in the Actions log. That single screenshot proves your scoping is real.

---

## Anti-goals

The following are explicitly **not** part of this mini-project. Do not pursue them; they distract from the lesson.

- **Database migrations in the pipeline.** The expand/contract migration pattern is Week 8. This pipeline ships stateless code.
- **Statistical canary analysis.** We gate on a binary CloudWatch alarm. Automated canary *scoring* (CloudWatch Evidently / Kayenta-style) is Week 12.
- **EKS / Argo Rollouts.** The progressive-delivery-on-Kubernetes path is a different controller model. We are on ECS + Lambda this week.
- **A full multi-account fan-out.** Single account (`dev`) is fine for the mini-project; the cross-account KMS-gated artifact bucket is a documented stretch goal, and it is the Week-13 capstone shape.

---

## Submission

Push the solution to your Week 7 GitHub repository at `mini-project/safety-rail-pipeline/`. The instructor reviews by:

1. Reading `README.md`, `comparison.md`, and `cost.md`.
2. Confirming the multi-arch image (`buildx imagetools inspect`) and the ECR lifecycle/scan/immutability config.
3. Confirming the rollback evidence (CodeDeploy events with timestamps) is real and matches the alarm config.
4. Reading the `cdk synth` output for unexplained `Resource: "*"` and confirming the permission boundary is applied.
5. Confirming Path B has no stored AWS credential and the non-`main` assume is denied.

A submission whose rollback drill is documented with real timestamps and whose OIDC path provably has no long-lived key is a pass. The two most common review-fails are (a) "the pipeline is green but the rollback was never demonstrated" and (b) "the OIDC `sub` is too broad" — verify both before submitting.

---

## Stretch goals (no extra grade)

- **Cross-account fan-out.** Run the pipeline in a `tooling` account and deploy into a separate `prod` account with a KMS-gated artifact bucket (Lecture 1, §1.5). This is the capstone's actual shape.
- **Native multi-arch matrix.** Replace the single emulated-amd64 buildx build with two native builders (an arm64 CodeBuild project and an amd64 one) joined with `buildx imagetools create`. Faster builds; the production pattern.
- **A test listener validation step.** Use CodeDeploy's `BeforeAllowTraffic` hook on the ECS deploy to run a smoke test against the green fleet via the *test* listener before the canary shifts production traffic.
- **OpenTofu equivalent of the OIDC role.** Express the OIDC provider + scoped role in OpenTofu and diff it against the CDK output. The Terraform/OpenTofu form makes the IAM trust policy explicit in a way CDK abstracts — a useful comparison for the cross-tool fluency this course values.

---

**References**

- AWS CodePipeline — User Guide: <https://docs.aws.amazon.com/codepipeline/latest/userguide/welcome-introducing.html>
- AWS CodeDeploy — Blue/green on ECS: <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html>
- AWS CodeBuild — buildspec reference: <https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html>
- CDK — `aws_codedeploy`: <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_codedeploy-readme.html>
- GitHub — OpenID Connect in AWS: <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services>
- AWS Fargate pricing (x86 vs arm64): <https://aws.amazon.com/fargate/pricing/>
