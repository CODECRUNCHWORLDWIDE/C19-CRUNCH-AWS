# Lecture 2 — Blue/Green Discipline: ECS Deployment Groups, Lambda Traffic Shifting, and OIDC Federation

> **Reading time:** ~80 minutes. **Hands-on time:** ~60 minutes (you stand up an ECS blue/green deployment group with a canary and a CloudWatch alarm, then wire a GitHub OIDC provider).

Lecture 1 made the pipeline's *identity* safe. This lecture makes the pipeline's *behavior* safe. The two failure modes are different: Lecture 1 defends against a malicious deploy; this lecture defends against an honest-but-broken one — the build that passes every test, ships a real bug, and would take an outage if you let it reach 100% of traffic at once. The defense is **blue/green deployment with a canary, a bake window, a CloudWatch alarm, and automatic rollback.** By the end of this lecture you can configure an ECS blue/green deployment group that shifts 10% of traffic to the new version, watches an alarm for five minutes, and either promotes to 100% or reverts to the untouched blue fleet without a human in the loop — and do the equivalent for a Lambda function with traffic shifting. Then we build the modern alternative the rest of the industry actually runs — GitHub Actions federated into AWS with OIDC — and compare the two honestly.

## 2.1 — In-place vs blue/green: the difference is whether you can take it back

There are two deployment models, and the difference between them is the answer to one question: *when the new version is bad, how fast and how cleanly can you get back to the old one?*

**In-place deployment** mutates the running fleet. For ECS rolling deployments, it stops a fraction of the old tasks and starts new ones in their place, repeating until the whole service runs the new version. For EC2/on-prem CodeDeploy, it logs into each instance and replaces the application there. The old version is *gone* as it goes — once a task is stopped and replaced, "rolling back" means deploying the *previous* version forward again, which takes as long as a deploy and during which you are running a mix of broken-new and being-replaced. In-place is simpler, uses no extra capacity, and is the right choice for low-stakes or stateless background workers where a minute of degraded service is acceptable. For a customer-facing API, it is how you turn a bad build into an incident.

**Blue/green deployment** stands the new version up *beside* the old one. The old fleet (blue) keeps serving 100% of traffic while the new fleet (green) comes up healthy. Then you shift traffic — all at once, or a canary slice, or linearly — from blue to green. Crucially, **blue is not torn down until green has proven itself.** Rollback is instant and clean: point the traffic back at blue, which never stopped running. The cost is that you run double capacity during the deploy (you pay for blue and green simultaneously for the bake window) and you need a load balancer that can swap which fleet it routes to. For anything customer-facing, this trade — a few minutes of double cost for instant, clean rollback — is the right one.

The vocabulary you must internalize: **canary** (shift a small slice, e.g. 10%, wait, then shift the rest), **linear** (shift in equal increments on a timer, e.g. 10% every minute), and **all-at-once** (shift 100% immediately — blue/green's rollback safety without the gradual exposure). CodeDeploy ships named configurations for each: `Canary10Percent5Minutes`, `Canary10Percent30Minutes`, `Linear10PercentEvery1Minute`, `Linear10PercentEvery3Minutes`, `AllAtOnce`. The name is the spec: `Canary10Percent5Minutes` means "send 10% to green, wait 5 minutes, then send the remaining 90%."

## 2.2 — How blue/green works on ECS: two target groups, one listener

This is the part students draw wrong on the whiteboard, so draw it right now. An ECS service behind an Application Load Balancer has, for blue/green:

- **One ALB** with a **production listener** (port 443, the one your users hit) and, optionally, a **test listener** (a separate port, e.g. 8443, for validation traffic before the canary).
- **Two target groups**: `blue-tg` and `green-tg`. At steady state, the production listener forwards to `blue-tg`, which contains the running (blue) tasks. `green-tg` is empty.
- **An ECS service with the `CODE_DEPLOY` deployment controller** (not the default `ECS` rolling controller, and not `EXTERNAL`). This tells ECS that CodeDeploy, not ECS itself, manages how new task sets take traffic.

When CodeDeploy runs a deployment:

1. It creates a new **task set** (the green tasks) running the new task definition, and registers them in `green-tg`.
2. It waits for the green tasks to pass their ELB health checks in `green-tg`.
3. Per the deployment config, it modifies the **production listener** to forward a slice (10% for a canary) to `green-tg` and the rest to `blue-tg`. This is the canary: 10% of real users now hit the new code.
4. It watches the configured **CloudWatch alarms** for the bake window (5 minutes for `Canary10Percent5Minutes`). If any alarm enters `ALARM` state, CodeDeploy **rolls back**: the listener reverts to 100% `blue-tg`, the green task set is destroyed, blue was never disturbed.
5. If the alarms stay healthy through the bake window, CodeDeploy shifts the production listener to 100% `green-tg`, waits the configured termination delay, then terminates the blue task set. Green is now blue; the next deploy reuses the now-empty target group.

The two-target-group dance is the whole mechanism. The listener is the switch; the target groups are the two positions; the alarm is the trip wire; the bake window is how long you watch before committing. In CDK, the `ApplicationLoadBalancedFargateService` from `aws-ecs-patterns` plus an `EcsDeploymentGroup` wires most of this; you provide the two target groups, the listeners, the alarm, and the deployment config. Exercise 2 builds it end to end.

## 2.3 — The alarm is the rollback trigger — pick it deliberately

Auto-rollback is only as good as the alarm that triggers it. A blue/green deploy with no alarm is just a slower in-place deploy: the canary shifts, the bake window passes, and a broken-but-not-crashing version gets promoted to 100% because nothing was watching the right signal. **The alarm is the deploy's definition of "healthy."** Choose it to catch the failure mode you actually fear.

The default and best first alarm is the ALB's **HTTP 5XX rate on the green target group**. If the new code throws, returns 500s, or fails to start cleanly, the target-group 5XX count spikes, the alarm fires within the bake window, and CodeDeploy reverts. A 5XX alarm catches the most common bad-deploy signature — the code is broken in a way that surfaces as server errors — and it does so within a minute or two of the canary taking traffic, while only 10% of users are exposed.

```typescript
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';

// 5XX on the GREEN target group: if the canary errors, this fires.
const green5xx = greenTargetGroup.metrics.httpCodeTarget(
  elbv2.HttpCodeTarget.TARGET_5XX_COUNT,
  { period: Duration.minutes(1), statistic: 'Sum' },
);

const rollbackAlarm = new cloudwatch.Alarm(this, 'Canary5xxAlarm', {
  metric: green5xx,
  threshold: 5,            // >5 server errors in a 1-minute period
  evaluationPeriods: 1,    // fire on the first bad minute
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
  treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
  alarmName: 'order-service-canary-5xx',
});
```

A second alarm worth adding is **target-group response-time p99** — a deploy that does not error but is suddenly 10× slower is also a bad deploy, and latency catches the "it works but it's pathological" class. You can hand CodeDeploy multiple alarms; if *any* of them fires during the bake window, it rolls back. Set `treatMissingData: NOT_BREACHING` so that a brand-new green target group with no traffic yet does not trip the alarm on missing data before the canary even starts — a classic false-rollback.

One subtlety: alarm evaluation has latency. A 1-minute period with 1 evaluation period means the fastest the alarm can fire is ~1–2 minutes after the bad data point. A `Canary10Percent5Minutes` bake window gives the alarm time to see the problem. Do not pair a 5-minute alarm window with a 1-minute canary — the canary would promote before the alarm could fire. Match the bake window to the alarm's reaction time, with margin.

## 2.4 — Lambda traffic shifting: same discipline, different mechanism

CodeDeploy applies the identical mental model — canary, bake window, alarm, rollback — to Lambda, but the mechanism is **aliases and versions** instead of target groups.

A Lambda **version** is an immutable snapshot of the function's code and config, numbered (`1`, `2`, `3`...). A Lambda **alias** is a named, movable pointer to a version (`prod` → version `7`). Clients invoke the alias (`my-function:prod`), not a raw version, so you can move what `prod` points at without changing the invoker. Critically, an alias can do a **weighted split**: `prod` can point 90% at version `7` and 10% at version `8`. That weighted split is the Lambda canary.

CodeDeploy's Lambda deployment shifts the alias weight per the config. `CodeDeployDefault.LambdaCanary10Percent5Minutes` moves the alias to 90/10 (old/new), waits 5 minutes watching the alarm, then moves it to 0/100. `CodeDeployDefault.LambdaLinear10PercentEvery1Minute` steps the weight 10% per minute. If the alarm fires, the alias snaps back to 100% old. The new version's code was deployed but never took more than 10% of invocations until it proved itself — exactly the ECS story, in alias-weight terms.

Lambda deployments also support **pre-traffic and post-traffic hooks**: small Lambda functions CodeDeploy invokes *before* shifting any traffic (pre-traffic — run a smoke test against the new version; if it fails, abort before any user hits the new code) and *after* the shift completes (post-traffic — run an integration check, fail the deploy if it does not pass). The hook is your programmatic gate, complementary to the alarm: the alarm watches production traffic; the hook actively probes.

In CDK, the pattern hinges on `fn.currentVersion` (a construct that creates a new `Version` whenever the function's code changes) and a `lambda.Alias` over it, wired into a `codedeploy.LambdaDeploymentGroup`:

```typescript
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as codedeploy from 'aws-cdk-lib/aws-codedeploy';

const handler = new lambda.Function(this, 'Handler', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'index.handler',
  code: lambda.Code.fromAsset('lambda/handler'),
});

// `currentVersion` publishes a new immutable Version on every code change.
const alias = new lambda.Alias(this, 'ProdAlias', {
  aliasName: 'prod',
  version: handler.currentVersion,
});

new codedeploy.LambdaDeploymentGroup(this, 'Canary', {
  alias,
  deploymentConfig: codedeploy.LambdaDeploymentConfig.CANARY_10PERCENT_5MINUTES,
  alarms: [errorRateAlarm],            // roll back if the function errors during the bake
  preHook: preTrafficSmokeTest,        // a Lambda that probes the new version first
});
```

The `errorRateAlarm` for Lambda is typically built on the function's `Errors` metric (or `Errors / Invocations` as a math expression for an error *rate*) over a 1-minute period. The same false-rollback caution applies: `treatMissingData: NOT_BREACHING` so an idle function does not roll back on no data.

There is a subtlety with Lambda canaries that does not exist for ECS: **a Lambda invocation is short-lived, so the weighted split is per-invocation, not per-connection.** When the alias is 90/10, each *invocation* has a 10% chance of hitting the new version. This makes the canary's statistical exposure cleaner than ECS (no sticky sessions, no long-lived connections pinning a user to one fleet), but it also means a *low-traffic* function may not get enough invocations during a 5-minute bake to surface an intermittent bug. For a function invoked a few times a minute, prefer a *linear* config with a longer total window (`LambdaLinear10PercentEvery3Minutes` gives a 30-minute total ramp) so the new version accumulates enough invocations to trip an alarm if it is going to. For a high-traffic function, `Canary10Percent5Minutes` exposes the new version to thousands of invocations in the bake window and a canary is plenty. The decision is the same as for any sampling problem: the bake window must be long enough, *at your invocation rate*, to collect a statistically meaningful sample of the new version's behavior. A 5-minute canary on a function invoked twice a minute samples ten invocations — too few to trust.

## 2.5 — The AppSpec file: what CodeDeploy reads to know what to do

CodeDeploy's deployment is driven by an `AppSpec` file that the build stage produces and the deploy stage consumes. Its shape differs by platform.

For **ECS**, the AppSpec names the task definition, the container and port to route, and the lifecycle hooks:

```yaml
version: 0.0
Resources:
  - TargetService:
      Type: AWS::ECS::Service
      Properties:
        TaskDefinition: <TASK_DEFINITION_ARN>   # placeholder CodePipeline substitutes
        LoadBalancerInfo:
          ContainerName: order-service
          ContainerPort: 8080
Hooks:
  - BeforeAllowTraffic: "arn:aws:lambda:us-east-1:111122223333:function:pre-traffic-check"
  - AfterAllowTraffic: "arn:aws:lambda:us-east-1:111122223333:function:post-traffic-check"
```

CodePipeline's ECS-to-CodeDeploy action substitutes the real task-definition ARN into the `<TASK_DEFINITION_ARN>` placeholder at deploy time, using the `imageDetail.json` / `taskdef.json` artifacts the build produced. The build stage's job is to produce a fresh `taskdef.json` (with the new image URI) and the `appspec.yaml`; the deploy action ties them together.

For **Lambda**, the AppSpec names the function, the alias, and the target version:

```yaml
version: 0.0
Resources:
  - my-function:
      Type: AWS::Lambda::Function
      Properties:
        Name: order-event-handler
        Alias: prod
        CurrentVersion: 7
        TargetVersion: 8
Hooks:
  - BeforeAllowTraffic: "pre-traffic-smoke-test"
  - AfterAllowTraffic: "post-traffic-integration-test"
```

When you use CDK's L2 constructs (`EcsDeploymentGroup`, `LambdaDeploymentGroup`), you rarely hand-write these — CDK and the CodePipeline action generate them. But you must be able to *read* one, because when a deploy hangs or fails the AppSpec is the first thing you inspect: wrong container port, wrong alias, a hook ARN that the deploy role cannot invoke.

## 2.5b — The lifecycle hook sequence, and why a hung deploy is almost always a hook that never reported

The single most common "my deploy hangs forever and then times out" failure has one cause: **a lifecycle hook Lambda that runs but never reports its status back to CodeDeploy.** Understanding the hook sequence makes this failure obvious instead of mysterious.

A CodeDeploy ECS blue/green deployment runs through an ordered sequence of lifecycle events, and you can attach a hook Lambda to several of them:

1. **`BeforeInstall`** — before the green task set is created. Rarely used for ECS.
2. **`Install`** — CodeDeploy creates the green task set and registers it in the green target group. (Not hookable; CodeDeploy does this.)
3. **`AfterInstall`** — green tasks exist but take no production traffic yet. A good place to run a migration check or warm a cache.
4. **`BeforeAllowTraffic`** — green is healthy in its target group but the production listener still points 100% at blue. This is your *gate before exposure*: run a smoke test against green via the test listener; if it fails, abort here and no user ever sees green.
5. **`AllowTraffic`** — CodeDeploy shifts the canary slice (10%) to green per the deployment config. (Not hookable; this is the shift itself.)
6. **`AfterAllowTraffic`** — the shift completed (canary or full). Run an integration test against the now-live green; fail the deploy to trigger rollback if it does not pass.

Each hook Lambda receives an event carrying a `DeploymentId` and a `LifecycleEventHookExecutionId`, and **it must call `codedeploy:PutLifecycleEventHookExecutionStatus` with one of those IDs and a status of `Succeeded` or `Failed`.** CodeDeploy then either proceeds (on `Succeeded`) or aborts and rolls back (on `Failed`). If the hook Lambda runs its logic, returns normally, but *forgets to call `PutLifecycleEventHookExecutionStatus`*, CodeDeploy has no status to act on — so it waits, for the full hook timeout (up to an hour), then fails the deployment with a timeout. The Lambda's CloudWatch logs show it ran successfully, which is exactly why this bug is confusing: the hook worked, but it never *told CodeDeploy* it worked.

```python
import os, json, boto3

codedeploy = boto3.client("codedeploy")
lambda_client = boto3.client("lambda")

def handler(event, context):
    deployment_id = event["DeploymentId"]
    hook_id = event["LifecycleEventHookExecutionId"]
    status = "Succeeded"
    try:
        resp = lambda_client.invoke(
            FunctionName=os.environ["TARGET_FUNCTION"],
            Payload=json.dumps({"smoke": True}).encode("utf-8"),
        )
        if json.loads(resp["Payload"].read()).get("statusCode") != 200:
            status = "Failed"
    except Exception:
        status = "Failed"
    # THE LINE PEOPLE FORGET. Without it the deploy hangs until timeout.
    codedeploy.put_lifecycle_event_hook_execution_status(
        deploymentId=deployment_id,
        lifecycleEventHookExecutionId=hook_id,
        status=status,
    )
    return {"status": status}
```

The hook's IAM role needs `codedeploy:PutLifecycleEventHookExecutionStatus` and `lambda:InvokeFunction` on the function-under-test. If the hook runs but the deploy still hangs, check the role first — a hook that cannot call `PutLifecycleEventHookExecutionStatus` (because its role lacks the permission) fails silently from CodeDeploy's perspective, identically to one that forgot the call. When you debug a hung deploy, the order of suspicion is: (1) did the hook report status? (2) does the hook's role allow the report? (3) is the hook ARN in the AppSpec correct and invokable by the deploy role?

## 2.6 — The modern alternative: GitHub Actions + OIDC federation into AWS

Everything above is the AWS-native flow. Now the alternative most teams in 2026 actually run: **GitHub Actions for CI, federated into AWS with OIDC for the deploy.** The reason is gravity — your code, PRs, and reviews already live on GitHub, so running CI there keeps the feedback loop in one place, and GitHub's marketplace of actions is enormous. The historical objection was credentials: to deploy from GitHub you used to store `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as repository secrets — long-lived keys for an IAM user, sitting in GitHub, one misconfiguration away from leaking. OIDC kills that objection.

**How OIDC federation works.** GitHub Actions can mint a short-lived OIDC token (a signed JWT) for each workflow run, issued by `token.actions.githubusercontent.com`. You register GitHub as an **OIDC identity provider** in IAM, create an IAM role whose **trust policy** says "allow `sts:AssumeRoleWithWebIdentity` for tokens from GitHub's OIDC provider, but only when the token's `sub` claim matches *this repo, this branch*," and your workflow calls `aws-actions/configure-aws-credentials@v4` to exchange the OIDC token for short-lived AWS credentials (valid ~1 hour). **There is no AWS secret stored in GitHub. There is nothing to leak.** The credentials are minted on demand, scoped to the role, and expire automatically.

The IAM OIDC provider and trust policy:

```bash
# Register GitHub as an OIDC provider (one per account).
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
```

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:code-crunch-labs/crunch-aws-capstone:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

Read the two conditions, because they are the entire security boundary:

- The `aud` (audience) condition pins the token to `sts.amazonaws.com`, so a token minted for some other audience cannot be replayed against this role.
- The `sub` (subject) condition is the load-bearing one. `repo:code-crunch-labs/crunch-aws-capstone:ref:refs/heads/main` means *only* workflow runs on the `main` branch of *that exact repo* can assume this role. A PR from a fork, a workflow on a feature branch, or a run from a different repo gets a token whose `sub` does not match, and the `AssumeRoleWithWebIdentity` call is denied. **If you scope the `sub` loosely — `repo:code-crunch-labs/*` or worse, just the audience with no `sub` — any workflow in your org (or, catastrophically, any GitHub repo if you forget the `sub` entirely) can assume the role.** The most common OIDC misconfiguration is a too-broad `sub`; for environment-gated deploys, use `repo:org/name:environment:prod` to require the run go through a GitHub Environment with its own approval rules.

The workflow side is short. Note `permissions: id-token: write` — without it, GitHub will not mint the OIDC token:

```yaml
name: deploy
on:
  push:
    branches: [main]

permissions:
  id-token: write      # required to mint the OIDC token
  contents: read

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::111122223333:role/github-actions-deploy
          aws-region: us-east-1
          # no aws-access-key-id, no aws-secret-access-key — none exist

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push multi-arch image
        uses: docker/build-push-action@v6
        with:
          platforms: linux/amd64,linux/arm64
          push: true
          tags: 111122223333.dkr.ecr.us-east-1.amazonaws.com/crunch/order-service:${{ github.sha }}

      - name: Deploy to ECS (blue/green via CodeDeploy)
        uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition: taskdef.json
          service: order-service
          cluster: crunch-prod
          codedeploy-appspec: appspec.yaml
          codedeploy-application: order-service
          codedeploy-deployment-group: order-service-bluegreen
          wait-for-service-stability: true
```

Notice the deploy step still hands off to **CodeDeploy** for the blue/green canary — OIDC replaces the *credential model* and GitHub Actions replaces the *orchestrator*, but the deployment-safety machinery (canary, alarm, rollback) is the same AWS service either way. You do not give up blue/green discipline by moving CI to GitHub; you keep CodeDeploy and change only who calls it and how it authenticates.

## 2.7 — AWS-native vs GitHub Actions + OIDC: the honest comparison

This is the design-review question. Here is the comparison on the three axes that matter, stated as a senior engineer would defend them.

| Axis | AWS-native (CodePipeline + CodeBuild + CodeDeploy) | GitHub Actions + OIDC (+ CodeDeploy for the deploy step) |
|---|---|---|
| **Credential model** | No external credential; all roles are in-account, assumed by AWS services. Strong by default. | OIDC: short-lived, federated, no stored secret. Equally strong *if* the `sub` claim is scoped tightly. A loose `sub` is the main footgun. |
| **Blast radius / threat surface** | Build runs inside your account; a poisoned buildspec is contained by the build role + boundary (Lecture 1). No third party in the trust path. | Build runs on GitHub-hosted runners (outside your account); the OIDC role is the only thing that touches AWS. A poisoned workflow is contained by the OIDC role's scope; you also trust GitHub's runner integrity and the marketplace actions you pin. |
| **Source-of-truth integration** | Source via CodeConnections; PR review, code, and CI live in two places (GitHub + AWS console). Context-switching cost. | Code, PR review, CI logs, and status checks all on GitHub. One place. Lower cognitive load for developers. |
| **Cost** | CodeBuild billed per build-minute by compute size; no idle cost. CodePipeline billed per active pipeline per month. Build traffic stays in-VPC (cheap via endpoints; watch NAT if not). | GitHub Actions: free minutes on the plan, then per-minute for GitHub-hosted runners; arm64 runners and larger runners cost more. Cross-internet image pushes to ECR incur data-transfer; mitigate with a pull-through cache and by pushing from a runner in a sensible region. |
| **Operability / debugging** | Logs in CloudWatch, deploy state in the CodeDeploy console, all under one AWS pane. Native CloudWatch alarms and EventBridge integration. Harder to reproduce a build locally. | Logs in the GitHub Actions UI, deploy state still in CodeDeploy. Two panes. Workflows reproduce locally with `act` (imperfectly). Marketplace actions can break on upstream changes — pin by SHA, not tag. |
| **Who owns the YAML** | `buildspec.yml` + CDK pipeline definition; owned by the platform/infra team, reviewed as IaC. | `.github/workflows/*.yml`; tends to be owned by app teams, edited more freely — which is the convenience *and* the PPE risk (Lecture 1). |
| **Multi-account fan-out** | CodePipeline cross-account with the KMS-gated artifact bucket (Lecture 1, §1.5) is a well-trodden, AWS-documented pattern. | Per-account OIDC roles, one trust policy per account/repo/env. Clean, but you manage N roles and N trust policies yourself. |

The defensible summary: **for an AWS-centric platform team that wants the pipeline as governed IaC inside the account, AWS-native is the lower-blast-radius choice. For a developer-experience-centric org where the code already lives on GitHub and the team values one pane of glass, GitHub Actions + OIDC is the better fit — and OIDC closes the historical credential gap completely.** Either way, keep CodeDeploy for the blue/green canary and keep the pipeline role scoped per Lecture 1. The two are not mutually exclusive: a common 2026 shape is GitHub Actions for build/test (developer-facing, fast feedback) handing off to CodeDeploy for the deploy (AWS-governed safety rails). You will build both this week and pick your hill in the challenge writeup.

A word on the hybrid pattern, because it is what the capstone actually uses and what a lot of mature shops converge on. The split that works is along the trust boundary: **untrusted, fast-feedback work (lint, unit tests, the image build) runs on GitHub Actions, where developers can edit the workflow and iterate; trusted, privileged work (the production deploy) hands off to a tightly-scoped OIDC role that calls CodeDeploy.** The OIDC role is the chokepoint — it is the only principal that can touch production, its `sub` is scoped to the protected `production` environment, and that environment requires a manual approval and a restricted branch. A developer can break the build workflow all day on a feature branch and never get near production, because the OIDC token minted for their feature branch fails the `sub` condition. This is the same separation-of-duties idea as Lecture 1's three-role split, expressed across the GitHub/AWS boundary: the people and automation that *write and test* code are not the same principal that *ships* it, and the OIDC `sub` + GitHub Environment is the enforcement point. When you write the comparison in the challenge, do not treat the two paths as a binary — the senior answer is often "GitHub for CI, OIDC + CodeDeploy for CD," and you should be able to draw exactly where the trust boundary sits.

One more operational note that decides real incidents: **observability of the deploy itself.** With the AWS-native flow, the deploy's state, the canary's progress, the alarm history, and the task logs are all in CloudWatch and the CodeDeploy console — one query language, one pane, native EventBridge events you can route to Slack. With GitHub Actions, the *orchestration* logs are on GitHub but the *deploy* state is still in CodeDeploy, so an on-call engineer debugging a stuck canary at 02:00 is in the AWS console regardless of which CI ran the build. This matters for the runbook: write it against CodeDeploy and CloudWatch, because that is where the deploy actually lives no matter who triggered it. The CI orchestrator is where you find "why did the build fail"; the AWS console is where you find "why did the canary roll back" — and the second question is the one that pages you.

## 2.8 — The reflexes to internalize this week

- **Blue/green for anything customer-facing; in-place only for low-stakes stateless workers.** The question is always "how clean is the rollback."
- **Two target groups, one listener, `CODE_DEPLOY` controller.** Draw it; it is the mechanism.
- **The alarm is the deploy's definition of healthy.** No alarm means no rollback means a slow in-place deploy with extra steps.
- **Match the bake window to the alarm's reaction time.** A 5-minute window for a 1-minute alarm; never the reverse.
- **`treatMissingData: NOT_BREACHING`** on canary alarms so an idle green fleet does not false-roll-back.
- **Lambda = versions + aliases + weighted split.** Same canary discipline, alias-weight mechanism, plus pre/post-traffic hooks for active probing.
- **OIDC over stored keys, always.** And the `sub` claim is the boundary — scope it to repo + branch (or repo + environment), never just the audience.
- **Pin marketplace actions by SHA, not tag.** A tag can be re-pointed at malicious code; a SHA cannot.
- **Keep CodeDeploy regardless of orchestrator.** GitHub Actions changes who calls the deploy; it should not change the deploy's safety rails.

## 2.9 — What we did not cover

This lecture gates deploys on a *single CloudWatch alarm* — a binary "is the error rate above threshold" check, which is the correct starting point and catches the common bad-deploy signatures. It does not cover **statistical canary analysis** (comparing the canary's metric distribution against the baseline's with confidence intervals, the way Kayenta/Spinnaker or CloudWatch's automated analysis do) — that is a Week 12 observability topic, and it is the natural next step once you trust the binary alarm. It also does not cover **progressive delivery on EKS** (Argo Rollouts, Flagger) — the in-cluster controller model is a different mechanism for the same discipline, and it is an elective. And it does not cover **database migrations in the deploy** — the expand/contract pattern that lets blue and green coexist against one evolving schema — which is Week 8, because you cannot do zero-downtime data changes until you have the zero-downtime *code* changes this week gives you.

---

## Lecture 2 — checklist before moving on

- [ ] I can explain in-place vs blue/green in terms of rollback cleanliness, and name when each is appropriate.
- [ ] I can draw the ECS blue/green mechanism: two target groups, one production listener, `CODE_DEPLOY` controller, the canary shift, the alarm trip wire.
- [ ] I can name the CodeDeploy configs (`Canary10Percent5Minutes`, `Linear10PercentEvery1Minute`, `AllAtOnce`) and read the name as a spec.
- [ ] I configured a CloudWatch alarm on green-target-group 5XX with `NOT_BREACHING` missing-data and understand why the bake window must exceed the alarm reaction time.
- [ ] I can explain Lambda traffic shifting in terms of versions, aliases, weighted splits, and pre/post-traffic hooks.
- [ ] I can write a GitHub OIDC trust policy with the `aud` and `sub` conditions scoped to repo + branch.
- [ ] I can defend a choice between AWS-native and GitHub Actions + OIDC on security, cost, and operability.

If any box is unchecked, re-read that section. The exercises and the mini-project assume the blue/green mechanism is solid.

---

**References cited in this lecture**

- AWS CodeDeploy — Deployment configurations: <https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-configurations.html>
- AWS CodeDeploy — Blue/green on ECS: <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html>
- AWS CodeDeploy — AppSpec file reference: <https://docs.aws.amazon.com/codedeploy/latest/userguide/reference-appspec-file.html>
- Lambda — Versions and aliases: <https://docs.aws.amazon.com/lambda/latest/dg/configuration-aliases.html>
- CDK — `aws_codedeploy` (Ecs/Lambda deployment groups): <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_codedeploy-readme.html>
- GitHub — Configuring OpenID Connect in AWS: <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services>
- `aws-actions/configure-aws-credentials`: <https://github.com/aws-actions/configure-aws-credentials>
- AWS Well-Architected — Operational Excellence (deployment safety): <https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html>
