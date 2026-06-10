# Lecture 1 — Your Pipeline IAM Role Is More Dangerous Than Your Prod IAM Role — Here's Why

> **Reading time:** ~75 minutes. **Hands-on time:** ~45 minutes (you scope a CodeBuild role, wire CodeConnections, and configure an ECR repo with lifecycle + scanning).

This is the lecture that decides whether your delivery pipeline is an asset or a liability. Everything else this week — the multi-arch build, the blue/green canary, the OIDC federation — is downstream of one truth that most teams discover the hard way: **the principal that deploys your code is more powerful than the principal that runs it.** Your production application role can read a table and publish to a topic. Your pipeline role can *replace the application* — and it does so automatically, on every merge, with no human in the approval path unless you deliberately put one there. If an attacker controls your pipeline, they do not need to find a vulnerability in your code; they ship their own. By the end of this lecture you will understand the pipeline's blast radius, scope the three roles CodeBuild/CodePipeline/CodeDeploy actually need, wrap them in a permission boundary, gate the cross-account artifact path behind a KMS key policy, and connect GitHub the right way (CodeConnections) instead of the dangerous way (a long-lived PAT in an environment variable).

## 1.1 — The asymmetry, stated plainly

Picture two IAM roles in your `prod` account.

The first is `OrderServiceTaskRole` — the task role attached to your ECS Fargate order service. Its policy is tight: `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:Query` on one table; `sqs:SendMessage` on one queue; `kms:Decrypt` on one key. You spent a week in the Week 2 IAM lab getting this right. If an attacker compromises a running task and steals its credentials via the container metadata endpoint, the blast radius is *that table, that queue, that key*. Bad, recoverable, scoped.

The second is `DeployPipelineRole` — the role CodeBuild assumes to deploy that same order service. What can it do? It can `ecs:RegisterTaskDefinition` (define what container image runs), `ecs:UpdateService` or hand a deployment to CodeDeploy (decide *which* code is live), `ecr:PutImage` (push the image that becomes the task), `iam:PassRole` (attach `OrderServiceTaskRole` — or anything else it is allowed to pass — to the new task), and read every secret the build needs from Secrets Manager. Now ask: if an attacker compromises *this* role, what is the blast radius?

The attacker pushes a malicious image to ECR, registers a task definition that runs it with `OrderServiceTaskRole` attached (or, if `iam:PassRole` is scoped too loosely, with a *more* privileged role), and updates the service. The malicious code now runs *as your application*, with your application's identity, inside your production VPC, and the CloudTrail entry says `DeployPipelineRole` did it — which is exactly what a deploy looks like. There was no exploit. There was no anomaly. The pipeline did its job; it just did it for the attacker.

**This is the asymmetry: the prod role is scoped to data; the pipeline role is scoped to *code and identity*. The pipeline role can grant itself the prod role's powers by passing it to a task. The reverse is not true.** A pipeline role with a wildcard is not "a CI convenience." It is a standing grant of the union of everything the pipeline can pass and everything it can deploy, available to anyone who can make the pipeline run.

And making the pipeline run is *easy*, because pipelines are designed to run on input from outside your trust boundary: a Git push, a pull request, a tag. The class of attacks here has a name — **poisoned pipeline execution (PPE)** — and it is the reason the CI/CD supply chain is on every serious threat model in 2026. A contributor opens a PR that edits the `buildspec.yml` to add a step that exfiltrates the build role's credentials. If your pipeline builds PRs with the deploy role attached, you just handed a stranger your deploy credentials. The CodeCov breach, the various npm/PyPI supply-chain incidents, the SolarWinds build-system compromise — all are variations on "the build system is privileged and accepts untrusted input."

## 1.2 — The three roles, and what each one actually needs

A CodePipeline-based delivery flow has, at minimum, three distinct IAM roles. Conflating them — giving one role all three jobs — is the first mistake. Keep them separate and scope each one.

### The CodePipeline service role

CodePipeline itself assumes a role to orchestrate. It does *not* run your build commands; it moves artifacts between stages, invokes CodeBuild and CodeDeploy, reads from the source, and writes to the artifact bucket. Its policy needs:

- `codebuild:StartBuild`, `codebuild:BatchGetBuilds` — to invoke and poll the build project.
- `codedeploy:CreateDeployment`, `codedeploy:GetDeployment`, `codedeploy:GetDeploymentConfig`, `codedeploy:RegisterApplicationRevision` — to drive the deploy stage.
- `s3:GetObject`, `s3:PutObject`, `s3:GetBucketVersioning` on the *artifact bucket only*.
- `kms:Decrypt`, `kms:GenerateDataKey` on the *artifact bucket's KMS key only*.
- `codestar-connections:UseConnection` (now `codeconnections:UseConnection`) on the *specific connection ARN*.

It does **not** need `ecs:*`, `ecr:*`, or `iam:PassRole` for the task role. That is the build/deploy roles' job. CDK generates a sensible pipeline role for you, but you should read it (`cdk synth` and grep the template) and confirm it is scoped to your resources, not `Resource: "*"`.

### The CodeBuild project role

This is the dangerous one, because it runs *your code* — the `buildspec.yml`, which is editable in the source repo. It needs:

- `logs:CreateLogStream`, `logs:PutLogEvents` on its own log group.
- `s3:GetObject` / `s3:PutObject` on the artifact bucket and, if you use S3 build caching, the cache bucket.
- `ecr:GetAuthorizationToken` (account-level — this one genuinely is `Resource: "*"`, it is how it works), and `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload` scoped to the *specific repository ARN* it pushes to.
- `secretsmanager:GetSecretValue` on the *specific secret ARNs* the build needs — not `secretsmanager:GetSecretValue` on `*`.
- `kms:Decrypt` on the keys protecting those secrets and the artifact bucket.

It does **not** need `ecs:UpdateService` (the deploy stage does that via CodeDeploy), and it absolutely does **not** need `iam:*`. The most common over-grant is `AmazonEC2ContainerRegistryFullAccess` or `AdministratorAccess` on the build role "to make it work." Resist. When the build fails on a permission error, read the error, add *that one action on that one resource*, and re-run.

### The CodeDeploy service role and the ECS task execution/task roles

CodeDeploy assumes a role to manage the deployment — for ECS blue/green it needs `ecs:DescribeServices`, `ecs:CreateTaskSet`, `ecs:UpdateServicePrimaryTaskSet`, `ecs:DeleteTaskSet`, `elasticloadbalancing:*` (scoped to the listener/target groups), `cloudwatch:DescribeAlarms`, and `lambda:InvokeFunction` for the lifecycle hooks. The AWS-managed `AWSCodeDeployRoleForECS` policy is a reasonable starting point, but in a hardened account you scope it down. Separately, the *task* gets two roles you defined in Week 5: the **task execution role** (pulls the image from ECR, fetches secrets, writes logs — used by the ECS agent) and the **task role** (your application's runtime identity). The pipeline's `iam:PassRole` permission must be scoped, via a condition, to *only* those two role ARNs and *only* for the `ecs-tasks.amazonaws.com` service:

```json
{
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": [
    "arn:aws:iam::111122223333:role/order-service-task-role",
    "arn:aws:iam::111122223333:role/order-service-task-execution-role"
  ],
  "Condition": {
    "StringEquals": { "iam:PassedToService": "ecs-tasks.amazonaws.com" }
  }
}
```

Without that `Resource` list and that condition, `iam:PassRole` on `*` lets the pipeline attach *any* role in the account to a task — including `OrganizationAccountAccessRole` if it exists. That is privilege escalation through the front door. The `iam:PassedToService` condition is not optional decoration; it is what stops a passed role from being used in a context you did not intend.

## 1.3 — The permission boundary: the only safe way to delegate the pipeline

You learned permission boundaries in Week 2: a boundary is a managed policy that defines the *maximum* permissions an identity can have, regardless of what its attached policies grant. The effective permissions are the *intersection* of the boundary and the identity policy. Boundaries are how you let a team create their own pipeline roles without letting them create an admin.

Here is the operational rule: **every role your CI creates — including roles the pipeline itself provisions during a `cdk deploy` — must carry a permission boundary that denies IAM writes outside a known path, denies `kms:ScheduleKeyDeletion`, denies `ecr:DeleteRepository` on production repos, and denies attaching `*FullAccess`/`AdministratorAccess` managed policies.** If a poisoned buildspec tries to escalate by creating a new admin role, the boundary intersects its grant to nothing.

A minimal boundary for pipeline-created roles, expressed as an IAM managed policy document:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowMostServices",
      "Effect": "Allow",
      "Action": "*",
      "Resource": "*"
    },
    {
      "Sid": "DenyIamEscalation",
      "Effect": "Deny",
      "Action": [
        "iam:CreateUser",
        "iam:CreateAccessKey",
        "iam:AttachUserPolicy",
        "iam:PutUserPolicy",
        "iam:CreateLoginProfile"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyBoundaryRemoval",
      "Effect": "Deny",
      "Action": [
        "iam:DeleteRolePermissionsBoundary",
        "iam:DeleteUserPermissionsBoundary"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyDestructiveSecurity",
      "Effect": "Deny",
      "Action": [
        "kms:ScheduleKeyDeletion",
        "kms:DisableKey",
        "kms:PutKeyPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyAttachAdmin",
      "Effect": "Deny",
      "Action": ["iam:AttachRolePolicy", "iam:AttachUserPolicy"],
      "Resource": "*",
      "Condition": {
        "ArnLike": {
          "iam:PolicyARN": [
            "arn:aws:iam::aws:policy/AdministratorAccess",
            "arn:aws:iam::aws:policy/*FullAccess"
          ]
        }
      }
    }
  ]
}
```

The `AllowMostServices` statement is the "max," and the explicit `Deny` statements carve out the escalation paths. Remember the Week 2 rule: **an explicit deny always wins.** Even if a poisoned buildspec convinces the role's attached policy to grant `iam:CreateUser`, the boundary's deny vetoes it. In CDK you attach a boundary to *every* role the app creates with a single line in the app's `Aspects`, which is the cleanest enforcement point:

```typescript
import { Aspects } from 'aws-cdk-lib';
import { PermissionsBoundary } from 'aws-cdk-lib/aws-iam';

// In the App scope, applied to every Role construct in every stack:
Aspects.of(app).add(
  PermissionsBoundary.fromName('crunch-pipeline-boundary'),
);
```

This is the single most leveraged line of code in your delivery infrastructure. Apply the boundary at the `App` level and you do not have to remember it role by role.

## 1.4 — CodeConnections, not a personal access token

You have two ways to let CodePipeline read from GitHub. One is correct in 2026; one is a 2018 anti-pattern that still shows up in copied tutorials.

**The wrong way: a GitHub personal access token (PAT) in an environment variable.** You generate a classic PAT with `repo` scope, drop it in Secrets Manager, and a webhook-style source action uses it. The problems: the PAT is a long-lived bearer credential with broad `repo` scope (read *and write* to all your repos if it is a classic token), it does not expire unless you remember to rotate it, anyone who can read that secret (including a poisoned buildspec with `secretsmanager:GetSecretValue` on too wide a resource) now has push access to your source, and revoking it breaks every pipeline that shares it. A leaked PAT is a leaked key to your source of truth.

**The right way: CodeConnections (formerly CodeStar Connections).** You install the *AWS Connector for GitHub* GitHub App on your org or repo, and AWS manages a short-lived, OAuth-style connection. CodePipeline references the connection by ARN; there is no token in your account to leak. The GitHub App's permissions are visible and revocable from GitHub's UI, scoped to the repos you select, and the connection's use is gated by `codeconnections:UseConnection`, which you scope to the specific connection ARN on the pipeline role. Setting it up is a two-step handshake: create the connection (it starts in `PENDING`), then complete the OAuth flow in the console to move it to `AVAILABLE`.

```bash
# Create the connection (returns a connection ARN, status PENDING).
aws codeconnections create-connection \
  --provider-type GitHub \
  --connection-name crunch-aws-github \
  --region us-east-1

# Then open the returned connection in the console and click
# "Update pending connection" to authorize the AWS Connector for GitHub
# GitHub App against your org/repo. Status moves to AVAILABLE.
aws codeconnections get-connection \
  --connection-arn arn:aws:codeconnections:us-east-1:111122223333:connection/abcd1234-... \
  --query 'Connection.ConnectionStatus'
```

In CDK the source action references the connection ARN and nothing else — no token, no webhook secret to manage:

```typescript
import { CodeStarConnectionsSourceAction } from 'aws-cdk-lib/aws-codepipeline-actions';
import { Artifact } from 'aws-cdk-lib/aws-codepipeline';

const sourceOutput = new Artifact('SourceOutput');
const sourceAction = new CodeStarConnectionsSourceAction({
  actionName: 'GitHub_Source',
  owner: 'code-crunch-labs',
  repo: 'crunch-aws-capstone',
  branch: 'main',
  connectionArn: 'arn:aws:codeconnections:us-east-1:111122223333:connection/abcd1234-...',
  output: sourceOutput,
  triggerOnPush: true,
});
```

The construct is still named `CodeStarConnectionsSourceAction` in `aws-cdk-lib` even though the service was renamed to CodeConnections — AWS renamed the service but kept the API names for backward compatibility. The action it produces uses `codeconnections:UseConnection` under the hood.

## 1.5 — The artifact bucket is a security boundary, and KMS is the lock

CodePipeline passes data between stages as *artifacts* stored in an S3 bucket. The source action zips the repo into the bucket; the build action reads it, produces an output artifact (the `imagedefinitions.json` or the `appspec.yaml`), writes it back; the deploy action reads that. In a single-account pipeline the bucket is mostly an implementation detail. In a **cross-account** pipeline — the common shape where a central `tooling` account runs the pipeline and deploys into separate `dev`/`stage`/`prod` accounts — the artifact bucket becomes a genuine trust boundary, and getting its encryption wrong silently breaks the pipeline or silently widens access.

The rule: **encrypt the artifact bucket with a customer-managed KMS key (CMK), and the KMS key policy — not the bucket policy — is the real boundary.** The deploy account's CodeDeploy/CodePipeline role must be granted `kms:Decrypt` and `kms:GenerateDataKey` in the *key policy* (or via a grant). If you only fix the bucket policy and forget the key policy, the cross-account role can `GetObject` the encrypted bytes but cannot decrypt them — and the failure mode is a confusing `AccessDenied` on KMS, not S3. Conversely, if you make the key policy too generous (`kms:Decrypt` for the whole org), every account can read every artifact, which may include source code and secrets baked into build output.

A correct cross-account key policy statement grants the *deploy account root* (so the deploy account's IAM can sub-delegate) decrypt rights, scoped by the encryption context where possible:

```json
{
  "Sid": "AllowDeployAccountDecrypt",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:root"
  },
  "Action": ["kms:Decrypt", "kms:DescribeKey"],
  "Resource": "*"
}
```

Pair it with the matching bucket policy that allows the deploy account `s3:GetObject` on the artifact prefix. Both must agree. The mental model: **the bucket controls who can fetch the ciphertext; the key controls who can turn it into plaintext.** A multi-account pipeline that "works" with the bucket policy alone and an AWS-managed key is leaking the wrong default — switch to a CMK and make the grant explicit.

## 1.6 — ECR: the registry is part of the supply chain

The image your pipeline pushes is the artifact that actually runs in production, so the registry deserves the same security posture as the pipeline. Three controls matter this week.

**Tag immutability.** Set the repository to `IMMUTABLE` tags for anything that ships to production. With mutable tags, `v1.4.2` can be overwritten — push a new image to the same tag and the running task pulls different bytes on its next restart, with no record that the tag moved. Immutable tags mean a tag points to exactly one image digest forever; you deploy by digest or by an immutable tag, and "what is `v1.4.2`?" has one answer. Use a content-addressable tag (the Git SHA) as the canonical reference and immutable tags so it cannot be rewritten.

**Lifecycle policies.** ECR storage costs money and old images pile up fast when you build on every commit. A lifecycle policy expires images by age or count. The canonical policy: keep the last 20 images tagged with your release prefix, and expire untagged images (the layers left behind by overwritten manifests and failed pushes) after 7 days.

```json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Expire untagged images after 7 days",
      "selection": {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 7
      },
      "action": { "type": "expire" }
    },
    {
      "rulePriority": 2,
      "description": "Keep only the last 20 release-tagged images",
      "selection": {
        "tagStatus": "tagged",
        "tagPrefixList": ["release-"],
        "countType": "imageCountMoreThan",
        "countNumber": 20
      },
      "action": { "type": "expire" }
    }
  ]
}
```

Lifecycle rules evaluate by priority, lowest first, and an image expires when it matches a rule. Test a policy with the ECR "preview" API before you apply it to a production repo — a wrong `tagPrefixList` can expire images you are still running.

**Scanning.** ECR offers two scan modes. *Basic scanning* runs the open-source CVE database (Clair) on push and is free; turn on scan-on-push so every image gets a CVE report the moment it lands. *Enhanced scanning*, powered by Amazon Inspector, scans both OS packages and language-package dependencies continuously (not just on push), re-evaluates existing images when new CVEs are published, and feeds findings into Security Hub. Enhanced scanning costs per image and per re-scan; it is the right default for production registries and we wire it in Week 13's security stack. For this week, scan-on-push with basic scanning is enough, and you should fail the build on a `CRITICAL` finding — a CVE gate in the pipeline is cheap insurance.

**Pull-through cache.** When your build pulls a base image (`public.ecr.aws/docker/library/python:3.12-slim`, or a Docker Hub image), pulling directly from the upstream registry on every build hits rate limits (Docker Hub's anonymous pull limit is brutal in CI) and means an upstream outage breaks your build. A pull-through cache rule mirrors an upstream registry into your private ECR: the first pull fetches from upstream and caches it; subsequent pulls serve from your registry, at your latency, inside your VPC endpoints, scanned by your scanner. Configure a rule per upstream you depend on:

```bash
aws ecr create-pull-through-cache-rule \
  --ecr-repository-prefix dockerhub \
  --upstream-registry-url registry-1.docker.io \
  --credential-arn arn:aws:secretsmanager:us-east-1:111122223333:secret:ecr-pullthroughcache/dockerhub-AbCdEf \
  --region us-east-1
```

Then your Dockerfile's `FROM` line references `111122223333.dkr.ecr.us-east-1.amazonaws.com/dockerhub/library/python:3.12-slim` instead of Docker Hub directly. The cache is transparent, the rate limit is gone, and every base image you depend on is now inside your registry and your scan scope.

## 1.7 — Putting the IAM story together: a CDK PipelineProject with a scoped role

Here is the shape of a CodeBuild project in CDK with a deliberately scoped role — the kind you would defend in a review. Note that we add only the actions the build needs, scoped to the resources it touches, and we rely on the App-level permission boundary from §1.3 to cap the rest.

```typescript
import { Construct } from 'constructs';
import { Stack, StackProps, Duration } from 'aws-cdk-lib';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as iam from 'aws-cdk-lib/aws-iam';

export class BuildStack extends Stack {
  public readonly project: codebuild.PipelineProject;

  constructor(scope: Construct, id: string, props: StackProps) {
    super(scope, id, props);

    const repo = new ecr.Repository(this, 'AppRepo', {
      repositoryName: 'crunch/order-service',
      imageTagMutability: ecr.TagMutability.IMMUTABLE,
      imageScanOnPush: true,
      lifecycleRules: [
        { description: 'Expire untagged after 7 days', tagStatus: ecr.TagStatus.UNTAGGED, maxImageAge: Duration.days(7) },
        { description: 'Keep last 20 release images', tagStatus: ecr.TagStatus.TAGGED, tagPrefixList: ['release-'], maxImageCount: 20 },
      ],
    });

    this.project = new codebuild.PipelineProject(this, 'BuildProject', {
      // arm64 build image so we can build native arm64 layers fast (see Lecture 2 / Exercise 1).
      environment: {
        buildImage: codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
        computeType: codebuild.ComputeType.LARGE,
        privileged: true, // required for the Docker daemon inside the build
      },
      buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec.yml'),
      environmentVariables: {
        ECR_REPO_URI: { value: repo.repositoryUri },
      },
    });

    // Scope the build role: ECR auth is account-level; push is repo-scoped.
    this.project.addToRolePolicy(new iam.PolicyStatement({
      actions: ['ecr:GetAuthorizationToken'],
      resources: ['*'], // this action does not support resource-level scoping
    }));
    repo.grantPullPush(this.project); // grants the layer-upload + PutImage actions, repo-scoped
  }
}
```

Read what is *not* here. No `iam:PassRole`. No `ecs:*`. No `secretsmanager:GetSecretValue` on `*`. The build builds and pushes; it does not deploy. The deploy stage, with its own role, does the deploy. Separation of duties is not bureaucracy here — it is the difference between "a poisoned buildspec can push a bad image (which the canary will catch)" and "a poisoned buildspec can pass itself an admin role."

## 1.8 — The reflexes to internalize this week

Build these reflexes; they are the spine of safe delivery:

- **Three roles, not one.** Pipeline orchestrator, build, deploy — each scoped to its job. Conflating them is the first over-grant.
- **`iam:PassRole` is always scoped by resource and by `iam:PassedToService`.** A bare `iam:PassRole` on `*` is privilege escalation waiting to happen.
- **Every CI-created role carries a permission boundary.** Apply it at the `App` level via an Aspect so you cannot forget.
- **CodeConnections, never a PAT.** No long-lived bearer token to your source of truth should exist in your account.
- **The KMS key policy is the cross-account boundary, not the bucket policy.** Fix both; the key is the one people forget.
- **Immutable production tags, lifecycle policies, scan-on-push, pull-through cache.** The registry is part of the supply chain; treat it like one.
- **When the build fails on a permission error, add that one action on that one resource.** Never reach for `*FullAccess` to "unblock."
- **Read the role CDK generated.** `cdk synth`, grep for `Resource: "*"`, and ask whether each wildcard is genuinely unscopable (a few, like `ecr:GetAuthorizationToken`, are) or just lazy.

## 1.9 — What we did not cover (Lecture 2 picks it up)

This lecture is about *who the pipeline is* — its identity, its blast radius, its boundary. Lecture 2 is about *what the pipeline does safely* — the blue/green deployment discipline that means even a build that passes CI and ships a bad image never takes more than 10% of traffic before an alarm rolls it back. The two halves are complementary: a scoped role limits what a *malicious* deploy can reach; a canary with auto-rollback limits what an *honest-but-broken* deploy can break. You need both. A perfectly scoped pipeline that does an all-at-once in-place deploy of a crashing build is still an outage; a sloppy wildcard role that does a beautiful canary is still a breach waiting to happen.

---

## Lecture 1 — checklist before moving on

- [ ] I can explain, in one sentence, why the pipeline role is more dangerous than the prod role (it controls code and identity, not just data).
- [ ] I can name the three distinct roles in a CodePipeline flow and what each one needs.
- [ ] I can write an `iam:PassRole` statement scoped by resource ARN and `iam:PassedToService`.
- [ ] I can write a permission boundary that denies IAM escalation and `*FullAccess` attachment, and apply it at the CDK `App` level.
- [ ] I set up a CodeConnections connection to GitHub and can explain why it beats a PAT.
- [ ] I configured an ECR repo with immutable tags, a lifecycle policy, scan-on-push, and I understand pull-through cache.
- [ ] I can explain why the KMS key policy — not the bucket policy — is the real boundary on a cross-account artifact bucket.

If any box is unchecked, re-read that section. Lecture 2 assumes the role model is solid.

---

**References cited in this lecture**

- AWS — "Security best practices for CodeBuild": <https://docs.aws.amazon.com/codebuild/latest/userguide/security-best-practices.html>
- AWS — "Security best practices for CodePipeline": <https://docs.aws.amazon.com/codepipeline/latest/userguide/security-best-practices.html>
- IAM — Permissions boundaries: <https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html>
- IAM — The confused deputy problem: <https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html>
- CodeConnections — Connect to GitHub: <https://docs.aws.amazon.com/dtconsole/latest/userguide/connections-create-github.html>
- Amazon ECR — Lifecycle policies: <https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html>
- Amazon ECR — Image scanning: <https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html>
- Amazon ECR — Pull-through cache: <https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache.html>
- AWS KMS — Key policies: <https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html>
