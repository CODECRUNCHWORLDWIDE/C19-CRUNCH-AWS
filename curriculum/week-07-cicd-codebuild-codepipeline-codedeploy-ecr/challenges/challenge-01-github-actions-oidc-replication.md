# Challenge 1 — Replicate the delivery flow with GitHub Actions + OIDC, then compare

> **Estimated time:** 120–180 minutes. Worth more than its time cost: this is the conversation you will have in every AWS-shop design review and most DevOps interviews.

You built the AWS-native delivery flow in the exercises: CodePipeline triggered by GitHub, lint/test, a multi-arch CodeBuild, an ECR push, and a CodeDeploy blue/green ECS deploy with a canary and auto-rollback. Now build the *same observable outcome* with GitHub Actions, federated into AWS with **OIDC** — and prove there is **no long-lived AWS credential anywhere**. Then write the comparison.

## What you are building

A `.github/workflows/deploy.yml` in your application repo that, on a push to `main`:

1. Mints a short-lived OIDC token and exchanges it for AWS credentials via `aws-actions/configure-aws-credentials@v4` — **no `AWS_ACCESS_KEY_ID` secret in the repo.**
2. Runs lint and test (as Actions jobs).
3. Builds a `linux/amd64` + `linux/arm64` image with `docker/build-push-action` and pushes it to ECR.
4. Hands the deploy to **CodeDeploy** for the blue/green canary (you keep the safety rails from Exercise 2; OIDC + Actions replaces the *orchestrator and credential model*, not the deployment discipline).

Plus the AWS side: an IAM OIDC identity provider for GitHub, and a deploy role whose trust policy is scoped to *your repo, your branch*.

## Step 1 — The OIDC provider and the deploy role (AWS side)

Register GitHub as an OIDC provider (once per account) and create the role. Do this in CDK so it is reproducible, but the CLI form makes the trust relationship explicit:

```bash
# 1. The OIDC identity provider (idempotent; skip if it already exists).
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
```

The CDK form of the role and provider:

```typescript
import { Construct } from 'constructs';
import { Stack, StackProps } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';

export class GithubOidcStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const provider = new iam.OpenIdConnectProvider(this, 'GitHubOidc', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
    });

    const deployRole = new iam.Role(this, 'GitHubDeployRole', {
      roleName: 'github-actions-deploy',
      assumedBy: new iam.WebIdentityPrincipal(provider.openIdConnectProviderArn, {
        // The audience pins the token; the subject pins repo + branch.
        StringEquals: {
          'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
        },
        StringLike: {
          'token.actions.githubusercontent.com:sub':
            'repo:code-crunch-labs/crunch-aws-capstone:ref:refs/heads/main',
        },
      }),
      // Scope exactly like the AWS-native build+deploy roles from Lecture 1.
      // No AdministratorAccess. iam:PassRole scoped to the task roles only.
    });

    // ECR push (account-level auth + repo-scoped layer ops).
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: ['ecr:GetAuthorizationToken'],
      resources: ['*'],
    }));
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'ecr:BatchCheckLayerAvailability', 'ecr:InitiateLayerUpload',
        'ecr:UploadLayerPart', 'ecr:CompleteLayerUpload', 'ecr:PutImage',
      ],
      resources: [`arn:aws:ecr:${this.region}:${this.account}:repository/crunch/order-service`],
    }));
    // CodeDeploy hand-off + scoped PassRole for the ECS task roles.
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: ['codedeploy:CreateDeployment', 'codedeploy:GetDeployment', 'codedeploy:RegisterApplicationRevision', 'codedeploy:GetDeploymentConfig'],
      resources: ['*'], // scope to the application ARN in production
    }));
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: ['iam:PassRole'],
      resources: [
        `arn:aws:iam::${this.account}:role/order-service-task-role`,
        `arn:aws:iam::${this.account}:role/order-service-task-execution-role`,
      ],
      conditions: { StringEquals: { 'iam:PassedToService': 'ecs-tasks.amazonaws.com' } },
    }));
  }
}
```

**The `sub` condition is the entire security boundary.** Read it again: only `main`-branch runs of `code-crunch-labs/crunch-aws-capstone` can assume this role. A PR from a fork gets a token whose `sub` is `repo:.../pull/NNN/merge` — it does not match, the assume is denied. A different repo's run does not match. This is what replaces the stored access key: a token that AWS will only honor for *this* workflow in *this* repo on *this* branch.

## Step 2 — The workflow (GitHub side)

`.github/workflows/deploy.yml`:

```yaml
name: deploy
on:
  push:
    branches: [main]

# Without id-token: write, GitHub will not mint the OIDC token. This is the
# line people forget, and the error ("Credentials could not be loaded") is opaque.
permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: us-east-1
  ECR_REPO: 111122223333.dkr.ecr.us-east-1.amazonaws.com/crunch/order-service

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install ruff==0.6.9 && ruff check app/

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt pytest==8.3.3 && pytest -q

  build-and-deploy:
    needs: [lint, test]   # gate the deploy on lint + test passing
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::111122223333:role/github-actions-deploy
          aws-region: ${{ env.AWS_REGION }}
          # NO aws-access-key-id / aws-secret-access-key. None exist.

      - name: Login to Amazon ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Set up buildx (multi-arch)
        uses: docker/setup-buildx-action@v3

      - name: Build and push multi-arch image
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ env.ECR_REPO }}:release-${{ github.sha }}

      - name: Render new task definition
        id: taskdef
        uses: aws-actions/amazon-ecs-render-task-definition@v1
        with:
          task-definition: taskdef.json
          container-name: order-service
          image: ${{ env.ECR_REPO }}:release-${{ github.sha }}

      - name: Deploy to ECS via CodeDeploy (blue/green canary)
        uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition: ${{ steps.taskdef.outputs.task-definition }}
          service: order-service
          cluster: crunch-prod
          codedeploy-appspec: appspec.yaml
          codedeploy-application: order-service
          codedeploy-deployment-group: order-service-bluegreen
          wait-for-service-stability: true
```

**Pin marketplace actions by SHA in production**, not by tag — a tag can be re-pointed at malicious code by a compromised maintainer; a SHA cannot. For the challenge, tags are acceptable; note in your writeup that production would pin SHAs.

## Step 3 — Prove there is no long-lived credential

This is the load-bearing acceptance check. Demonstrate, with evidence, that:

1. Your GitHub repo's `Settings → Secrets and variables → Actions` contains **no** `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY`. Screenshot it.
2. The `configure-aws-credentials` step log shows it assumed the role via web identity (it prints the assumed-role ARN, e.g. `arn:aws:sts::111122223333:assumed-role/github-actions-deploy/GitHubActions`).
3. A CloudTrail lookup shows the `AssumeRoleWithWebIdentity` event with the GitHub OIDC provider as the identity:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --query 'Events[0].CloudTrailEvent' --output text | python -m json.tool | grep -A2 federatedProvider
```

## Acceptance criteria

- [ ] An IAM OIDC provider for `token.actions.githubusercontent.com` exists, and a `github-actions-deploy` role whose trust policy pins both `aud` (`sts.amazonaws.com`) and `sub` (`repo:<owner>/<repo>:ref:refs/heads/main`).
- [ ] The workflow has `permissions: id-token: write` and uses `aws-actions/configure-aws-credentials@v4` with **no** stored AWS keys.
- [ ] A push to `main` runs lint + test, builds a multi-arch image, pushes to ECR (verify `manifest.list` media type as in Exercise 1), and triggers a CodeDeploy blue/green canary.
- [ ] You proved no long-lived credential exists (the three checks in Step 3).
- [ ] You deliberately push from a *non-`main`* branch or a fork PR and show the assume-role is **denied** because the `sub` does not match. (This is the proof your scoping works.)
- [ ] The deploy role has `iam:PassRole` scoped to the two task roles with the `iam:PassedToService` condition — no bare `iam:PassRole` on `*`.

## The comparison writeup (the actual deliverable)

Write `comparison.md` (600–900 words) comparing the AWS-native flow (exercises) against the GitHub Actions + OIDC flow (this challenge) on **three axes**. Do not hedge — take a position and defend it. For each axis, state which approach you would choose *for a specific context* and why:

1. **Security.** Blast radius of a poisoned pipeline/workflow. Credential model (in-account service roles vs short-lived OIDC). Where untrusted input (a PR) can reach privileged credentials. The `sub`-scoping footgun. Who can edit the YAML and how that changes the threat model.
2. **Cost.** CodeBuild build-minutes by compute size vs GitHub-hosted runner minutes (including arm64 / larger-runner premiums). CodePipeline per-active-pipeline charge. Data-transfer for cross-internet image pushes vs in-VPC pushes through endpoints. Where a pull-through cache changes the math.
3. **Operability.** Where the logs live (CloudWatch vs the Actions UI) and the two-pane reality (CodeDeploy state is in AWS either way). Local reproducibility. Marketplace-action supply-chain risk and SHA pinning. Multi-account fan-out (KMS-gated artifact bucket vs N OIDC roles).

End with a one-paragraph recommendation for **a specific org shape** (e.g., "a 12-person product team whose code lives on GitHub" vs "a platform team running 40 services across 5 accounts") and which delivery model you would put them on, and why.

## Hints

1. **The opaque "Credentials could not be loaded" error** almost always means a missing `permissions: id-token: write` or a `sub` mismatch. Check both before anything else.
2. **The `sub` claim format varies by trigger.** Pushes are `repo:owner/name:ref:refs/heads/<branch>`. Environments are `repo:owner/name:environment:<env>`. Tags are `repo:owner/name:ref:refs/tags/<tag>`. PRs are `repo:owner/name:pull_request`. Scope to the one you actually deploy from. For prod, prefer the *environment* form so the run must pass a GitHub Environment's protection rules.
3. **The thumbprint requirement is gone.** Older guides told you to fetch GitHub's OIDC thumbprint; AWS now trusts the GitHub OIDC issuer without a hardcoded thumbprint. Do not paste a stale thumbprint.
4. **Keep CodeDeploy.** The temptation is to replace the blue/green with a raw `aws ecs update-service`, which is an in-place rolling deploy. Don't — the point is that the *safety rails* survive the move to GitHub Actions. Hand off to CodeDeploy.

## Submission

Commit to your Week 7 repository at `challenges/challenge-01-oidc/` containing:

- `.github/workflows/deploy.yml`
- `lib/github-oidc-stack.ts` (the OIDC provider + scoped deploy role)
- `comparison.md` (the 600–900-word writeup)
- `evidence/` — screenshots/log excerpts proving no stored credential and the denied non-`main` assume.

The instructor reviews by reading `comparison.md`, confirming the `sub` scoping in the trust policy, and checking the evidence that no long-lived key exists. The most common review-fail is a too-broad `sub` (e.g., `repo:owner/*` or audience-only) — if your trust policy would let *any* repo or *any* branch assume the role, the challenge is not passed.

---

**References**

- GitHub — Configuring OpenID Connect in AWS: <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services>
- GitHub — About security hardening with OIDC (subject claims): <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect>
- IAM — Create OIDC identity providers: <https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html>
- `aws-actions/configure-aws-credentials`: <https://github.com/aws-actions/configure-aws-credentials>
- `aws-actions/amazon-ecs-deploy-task-definition`: <https://github.com/aws-actions/amazon-ecs-deploy-task-definition>
- CDK — `OpenIdConnectProvider` and `WebIdentityPrincipal`: <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam-readme.html>
