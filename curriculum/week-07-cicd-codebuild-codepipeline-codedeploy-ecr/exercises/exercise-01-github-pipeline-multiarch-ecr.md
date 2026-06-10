# Exercise 1 — GitHub-triggered pipeline → lint/test → multi-arch CodeBuild → ECR

> **Estimated time:** ~90 minutes. This is the foundation exercise; Exercises 2 and 3 bolt onto the pipeline you build here.

## Goal

Stand up a CodePipeline that:

1. Triggers on a push to `main` of a GitHub repo, via a **CodeConnections** connection (not a PAT).
2. Runs **lint** and **test** as two parallel CodeBuild actions (fail fast on either).
3. Runs a **build** CodeBuild action that builds a `linux/amd64` + `linux/arm64` image with `docker buildx` and pushes a single multi-arch manifest to **ECR**, tagged with the Git commit SHA.
4. Produces the `imagedefinitions.json` / `imageDetail.json` output artifact that Exercise 2's deploy stage will consume.

By the end you can run `docker manifest inspect` against your pushed tag and see both architectures under one manifest list.

## Prerequisites

- Exercise from Lecture 1 done: a CodeConnections connection to your GitHub repo in `AVAILABLE` state. Have its ARN handy.
- A CDK app you can `cdk deploy` into your `dev` account (Week 3). `aws-cdk-lib` ≥ `2.150.0`.
- A small app in your GitHub repo with a `Dockerfile`, a lint command, and a test command. A FastAPI "hello" service from Week 5 is perfect.

## Step 1 — The repository layout

Your GitHub repo (the *source*, not the CDK app) needs these files at its root:

```
.
├── Dockerfile
├── buildspec-lint.yml
├── buildspec-test.yml
├── buildspec-build.yml
├── app/
│   └── main.py
├── pyproject.toml          # ruff + pytest config
└── requirements.txt
```

A minimal `Dockerfile` that builds cleanly on both architectures (Python's slim base is multi-arch already; nothing arch-specific here):

```dockerfile
# Pulled through your ECR pull-through cache in production; Docker Hub directly here for simplicity.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

## Step 2 — The three buildspecs

The lint and test buildspecs are short. The build buildspec is where the multi-arch magic lives.

`buildspec-lint.yml`:

```yaml
version: 0.2
phases:
  install:
    runtime-versions:
      python: 3.12
    commands:
      - pip install ruff==0.6.9
  build:
    commands:
      - echo "Linting..."
      - ruff check app/
```

`buildspec-test.yml`:

```yaml
version: 0.2
phases:
  install:
    runtime-versions:
      python: 3.12
    commands:
      - pip install -r requirements.txt pytest==8.3.3
  build:
    commands:
      - echo "Testing..."
      - pytest -q
reports:
  pytest_reports:
    files:
      - "report.xml"
    file-format: JUNITXML
```

`buildspec-build.yml` — the load-bearing one. We use `docker buildx` with a single command that builds both platforms and pushes a manifest list. Because the CodeBuild image is arm64 (Graviton) we get a native arm64 build and an emulated amd64 build; for the production-grade native-matrix approach see the mini-project. Note `DOCKER_BUILDKIT=1` and the `buildx` builder bootstrap in `pre_build`:

```yaml
version: 0.2
env:
  variables:
    DOCKER_BUILDKIT: "1"
phases:
  pre_build:
    commands:
      - echo "Logging in to ECR..."
      - aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
      - IMAGE_TAG="release-${CODEBUILD_RESOLVED_SOURCE_VERSION:0:12}"
      - echo "Image tag is $IMAGE_TAG"
      # Bootstrap a buildx builder that can target multiple platforms.
      - docker run --privileged --rm tonistiigi/binfmt --install all
      - docker buildx create --use --name crunchbuilder --driver docker-container
      - docker buildx inspect --bootstrap
  build:
    commands:
      - echo "Building multi-arch image for linux/amd64,linux/arm64..."
      - |
        docker buildx build \
          --platform linux/amd64,linux/arm64 \
          --tag "$ECR_REPO_URI:$IMAGE_TAG" \
          --push \
          .
  post_build:
    commands:
      - echo "Writing image artifacts for the deploy stage..."
      - printf '{"ImageURI":"%s"}' "$ECR_REPO_URI:$IMAGE_TAG" > imageDetail.json
      - printf '[{"name":"order-service","imageUri":"%s"}]' "$ECR_REPO_URI:$IMAGE_TAG" > imagedefinitions.json
artifacts:
  files:
    - imageDetail.json
    - imagedefinitions.json
    - appspec.yaml
    - taskdef.json
```

## Step 3 — The CDK pipeline (starter)

In your CDK app, create a stack with the ECR repo, the three CodeBuild projects, and the pipeline. Fill in the four `TODO`s.

```typescript
import { Construct } from 'constructs';
import { Stack, StackProps, Duration } from 'aws-cdk-lib';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as cpactions from 'aws-cdk-lib/aws-codepipeline-actions';
import * as iam from 'aws-cdk-lib/aws-iam';

export interface PipelineStackProps extends StackProps {
  readonly connectionArn: string;
  readonly githubOwner: string;
  readonly githubRepo: string;
}

export class PipelineStack extends Stack {
  constructor(scope: Construct, id: string, props: PipelineStackProps) {
    super(scope, id, props);

    const repo = new ecr.Repository(this, 'AppRepo', {
      repositoryName: 'crunch/order-service',
      imageTagMutability: ecr.TagMutability.IMMUTABLE,
      imageScanOnPush: true,
      lifecycleRules: [
        { description: 'expire untagged 7d', tagStatus: ecr.TagStatus.UNTAGGED, maxImageAge: Duration.days(7) },
        { description: 'keep 20 release', tagStatus: ecr.TagStatus.TAGGED, tagPrefixList: ['release-'], maxImageCount: 20 },
      ],
    });

    // TODO 1 — lint project: BuildSpec.fromSourceFilename('buildspec-lint.yml').
    const lintProject = new codebuild.PipelineProject(this, 'Lint', {
      // YOUR CODE HERE
    });

    // TODO 2 — test project: BuildSpec.fromSourceFilename('buildspec-test.yml').
    const testProject = new codebuild.PipelineProject(this, 'Test', {
      // YOUR CODE HERE
    });

    // TODO 3 — build project on an arm64 image, privileged (for Docker), with
    // ECR_REGISTRY and ECR_REPO_URI environment variables.
    const buildProject = new codebuild.PipelineProject(this, 'Build', {
      // YOUR CODE HERE
    });
    // Scope the build role: account-level ECR auth + repo-scoped push.
    buildProject.addToRolePolicy(new iam.PolicyStatement({
      actions: ['ecr:GetAuthorizationToken'],
      resources: ['*'],
    }));
    repo.grantPullPush(buildProject);

    const sourceOutput = new codepipeline.Artifact('Source');
    const buildOutput = new codepipeline.Artifact('BuildOutput');

    // TODO 4 — assemble the pipeline:
    //   Stage "Source": CodeStarConnectionsSourceAction (uses props.connectionArn).
    //   Stage "Verify": lint and test as TWO actions with the SAME runOrder (parallel).
    //   Stage "Build":  the buildProject CodeBuildAction producing buildOutput.
    const pipeline = new codepipeline.Pipeline(this, 'Pipeline', {
      pipelineName: 'order-service-delivery',
      // YOUR CODE HERE (stages)
    });
  }
}
```

## Step 4 — The CDK pipeline (solution)

```typescript
import { Construct } from 'constructs';
import { Stack, StackProps, Duration } from 'aws-cdk-lib';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as cpactions from 'aws-cdk-lib/aws-codepipeline-actions';
import * as iam from 'aws-cdk-lib/aws-iam';

export interface PipelineStackProps extends StackProps {
  readonly connectionArn: string;
  readonly githubOwner: string;
  readonly githubRepo: string;
}

export class PipelineStack extends Stack {
  constructor(scope: Construct, id: string, props: PipelineStackProps) {
    super(scope, id, props);

    const repo = new ecr.Repository(this, 'AppRepo', {
      repositoryName: 'crunch/order-service',
      imageTagMutability: ecr.TagMutability.IMMUTABLE,
      imageScanOnPush: true,
      lifecycleRules: [
        { description: 'expire untagged 7d', tagStatus: ecr.TagStatus.UNTAGGED, maxImageAge: Duration.days(7) },
        { description: 'keep 20 release', tagStatus: ecr.TagStatus.TAGGED, tagPrefixList: ['release-'], maxImageCount: 20 },
      ],
    });

    const smallLinux = {
      buildImage: codebuild.LinuxBuildImage.AMAZON_LINUX_2_STANDARD_5_0,
      computeType: codebuild.ComputeType.SMALL,
    };

    const lintProject = new codebuild.PipelineProject(this, 'Lint', {
      environment: smallLinux,
      buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec-lint.yml'),
    });

    const testProject = new codebuild.PipelineProject(this, 'Test', {
      environment: smallLinux,
      buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec-test.yml'),
    });

    const buildProject = new codebuild.PipelineProject(this, 'Build', {
      environment: {
        // arm64 (Graviton) build host: native arm64 layers + cheaper build minutes.
        buildImage: codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
        computeType: codebuild.ComputeType.LARGE,
        privileged: true, // Docker daemon + buildx need this
      },
      buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec-build.yml'),
      cache: codebuild.Cache.local(codebuild.LocalCacheMode.DOCKER_LAYER, codebuild.LocalCacheMode.SOURCE),
      environmentVariables: {
        ECR_REGISTRY: { value: `${this.account}.dkr.ecr.${this.region}.amazonaws.com` },
        ECR_REPO_URI: { value: repo.repositoryUri },
      },
    });
    buildProject.addToRolePolicy(new iam.PolicyStatement({
      actions: ['ecr:GetAuthorizationToken'],
      resources: ['*'],
    }));
    repo.grantPullPush(buildProject);

    const sourceOutput = new codepipeline.Artifact('Source');
    const buildOutput = new codepipeline.Artifact('BuildOutput');

    new codepipeline.Pipeline(this, 'Pipeline', {
      pipelineName: 'order-service-delivery',
      restartExecutionOnUpdate: true,
      stages: [
        {
          stageName: 'Source',
          actions: [
            new cpactions.CodeStarConnectionsSourceAction({
              actionName: 'GitHub',
              owner: props.githubOwner,
              repo: props.githubRepo,
              branch: 'main',
              connectionArn: props.connectionArn,
              output: sourceOutput,
              triggerOnPush: true,
            }),
          ],
        },
        {
          stageName: 'Verify',
          actions: [
            new cpactions.CodeBuildAction({
              actionName: 'Lint',
              project: lintProject,
              input: sourceOutput,
              runOrder: 1, // same runOrder => parallel with Test
            }),
            new cpactions.CodeBuildAction({
              actionName: 'Test',
              project: testProject,
              input: sourceOutput,
              runOrder: 1,
            }),
          ],
        },
        {
          stageName: 'Build',
          actions: [
            new cpactions.CodeBuildAction({
              actionName: 'BuildAndPush',
              project: buildProject,
              input: sourceOutput,
              outputs: [buildOutput],
            }),
          ],
        },
      ],
    });
  }
}
```

Instantiate it in your `bin/app.ts`:

```typescript
import { App } from 'aws-cdk-lib';
import { PipelineStack } from '../lib/pipeline-stack';

const app = new App();
new PipelineStack(app, 'OrderServicePipeline', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },
  connectionArn: 'arn:aws:codeconnections:us-east-1:111122223333:connection/abcd1234-...',
  githubOwner: 'code-crunch-labs',
  githubRepo: 'crunch-aws-capstone',
});
```

## Step 5 — Deploy, push, and watch

```bash
cdk synth                       # read the generated IAM; grep for Resource: "*"
cdk deploy OrderServicePipeline # creates the pipeline; it runs once on creation
git commit --allow-empty -m "trigger pipeline" && git push origin main
```

Watch the pipeline in the console, or tail it from the CLI:

```bash
aws codepipeline get-pipeline-state --name order-service-delivery \
  --query 'stageStates[].{stage:stageName,status:latestExecution.status}' --output table
```

## Expected output

When the pipeline goes green, the Build stage's log ends with a successful `buildx` push, and the manifest in ECR is a multi-arch manifest list. Verify both architectures are present:

```bash
aws ecr describe-images --repository-name crunch/order-service \
  --query 'imageDetails[0].{tags:imageTags,pushedAt:imagePushedAt,artifactMediaType:artifactMediaType}'
```

```
{
  "tags": ["release-3f9a1c4b2e10"],
  "pushedAt": "2026-06-09T14:21:07+00:00",
  "artifactMediaType": "application/vnd.docker.distribution.manifest.list.v2+json"
}
```

The `manifest.list` media type is the tell: this is a fat manifest, not a single-arch image. Confirm the two platforms directly:

```bash
docker buildx imagetools inspect \
  111122223333.dkr.ecr.us-east-1.amazonaws.com/crunch/order-service:release-3f9a1c4b2e10
```

```
Name:      .../crunch/order-service:release-3f9a1c4b2e10
MediaType: application/vnd.docker.distribution.manifest.list.v2+json

Manifests:
  Platform:  linux/amd64
  Platform:  linux/arm64
```

Two platforms under one tag. Any host — x86 or Graviton — pulls the right one automatically. That is the whole point of the multi-arch build: ship arm64 to Fargate Graviton tasks for ~20% savings and keep amd64 available with zero changes to the deploy.

## Acceptance criteria

- [ ] The pipeline triggers automatically on a push to `main` (via CodeConnections, not a PAT).
- [ ] Lint and Test run as two parallel actions in the Verify stage (same `runOrder`); a failure in either fails the stage.
- [ ] The Build action produces an ECR image tagged `release-<sha12>` with `artifactMediaType` of `manifest.list` (i.e., multi-arch).
- [ ] `docker buildx imagetools inspect` shows both `linux/amd64` and `linux/arm64`.
- [ ] The build role has only `ecr:GetAuthorizationToken` (on `*`, unavoidable) plus the repo-scoped push actions from `grantPullPush` — no `iam:PassRole`, no `ecs:*`.
- [ ] `cdk synth` output has no unexplained `Resource: "*"` in the build role.
- [ ] The Build artifact (`imageDetail.json` + `appspec.yaml` + `taskdef.json`) is produced for Exercise 2 to consume.

## Reflection questions

Answer these in a `results-ex01.md` next to your CDK app:

1. The build uses an arm64 CodeBuild image and `--platform linux/amd64,linux/arm64`. Which of the two builds is *native* and which is *emulated* on this host? What is the time cost of the emulated one, and how would the mini-project's native-matrix approach avoid it?
2. Why is the lint/test stage `runOrder`-parallel but the Build stage sequential after it? What would break if you ran Build in parallel with Test?
3. The ECR repo is `IMMUTABLE`. What happens if the same commit SHA is built twice (e.g., a re-run)? Is that a problem? (Hint: the digest is identical; `PutImage` of the same digest to the same immutable tag is a no-op, not an error.)
4. The build role needs `ecr:GetAuthorizationToken` on `Resource: "*"`. Why can this *one* action not be scoped to a repository ARN? (Hint: read the ECR API — the auth token is account-scoped, not repo-scoped.)
