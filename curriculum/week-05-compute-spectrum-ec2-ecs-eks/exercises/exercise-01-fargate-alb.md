# Exercise 1 — FastAPI on ECS Fargate behind an ALB

**Goal:** Containerize the shared FastAPI app, push it to ECR, and deploy it on ECS Fargate behind an Application Load Balancer using TypeScript CDK — with autoscaling, health checks, and a task role scoped to read exactly one S3 prefix. This is the *boring-correct* container platform from Lecture 1; you should be able to do it half-asleep by the end of the course.

**Estimated time:** 2 hours.

---

## Prerequisites

- Week-4 VPC deployed, with private subnets and an S3 gateway endpoint. You'll import it by name.
- Node.js 20+, the AWS CDK v2 CLI (`npm i -g aws-cdk`), Docker, and the AWS CLI logged in (`aws sts get-caller-identity` works).
- An S3 bucket for the `/read` endpoint. We create it in this exercise.

---

## Step 1 — Write the shared app (you reuse this in exercises 2 and 3)

Create a folder `fastapi-spectrum/app/`. This app is the spine of the whole week.

`app/main.py`:

```python
import os
from fastapi import FastAPI, HTTPException
import boto3
from botocore.exceptions import ClientError

app = FastAPI(title="fastapi-spectrum")
_s3 = boto3.client("s3")
DATA_BUCKET = os.environ.get("DATA_BUCKET", "")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/compute")
def compute(n: int = 30) -> dict[str, int]:
    # Deterministic CPU burn so we can measure compute cost/latency.
    n = max(0, min(n, 35))  # clamp so a hostile query can't wedge the worker

    def fib(k: int) -> int:
        return k if k < 2 else fib(k - 1) + fib(k - 2)

    return {"n": n, "result": fib(n)}


@app.get("/read")
def read(key: str = "public/hello.txt") -> dict[str, str]:
    if not DATA_BUCKET:
        raise HTTPException(status_code=500, detail="DATA_BUCKET not configured")
    try:
        obj = _s3.get_object(Bucket=DATA_BUCKET, Key=key)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        # AccessDenied here is the whole point of the IRSA exercise: prove the scope.
        raise HTTPException(status_code=403 if code == "AccessDenied" else 404, detail=code)
    first_line = obj["Body"].read().splitlines()[0].decode("utf-8")
    return {"key": key, "first_line": first_line}
```

`app/requirements.txt`:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
boto3==1.35.90
```

`app/Dockerfile` — multi-stage, Graviton-friendly, runs uvicorn:

```dockerfile
FROM public.ecr.aws/docker/library/python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY main.py .
EXPOSE 8080
# Run on 8080; the ALB target group health-checks /healthz.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Build it locally for arm64 (Graviton) and smoke-test:

```bash
cd fastapi-spectrum/app
docker build --platform linux/arm64 -t fastapi-spectrum:dev .
docker run --rm -p 8080:8080 -e DATA_BUCKET="" fastapi-spectrum:dev &
sleep 2
curl -s localhost:8080/healthz   # {"status":"ok"}
curl -s "localhost:8080/compute?n=25"
kill %1
```

---

## Step 2 — Scaffold the CDK app

```bash
cd fastapi-spectrum
mkdir infra-fargate && cd infra-fargate
cdk init app --language typescript
npm install aws-cdk-lib constructs
```

---

## Step 3 — Write the Fargate stack

Replace `lib/infra-fargate-stack.ts` with the following. This uses the `ecs-patterns` L3 construct, which wires the ALB, target group, security groups, and service in one shot — exactly what you want for the common case. We then add autoscaling and the least-privilege S3 task role by hand, because the L3 doesn't know your bucket.

```typescript
import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecsPatterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';

export class InfraFargateStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Import the Week-4 VPC by its tag/name. Adjust the lookup to match yours.
    const vpc = ec2.Vpc.fromLookup(this, 'Vpc', { vpcName: 'c19-week04-vpc' });

    // S3 bucket the /read endpoint reads from.
    const dataBucket = new s3.Bucket(this, 'DataBucket', {
      bucketName: `c19-week05-data-${this.account}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // dev only — auto-empties on destroy
      autoDeleteObjects: true,
    });

    const cluster = new ecs.Cluster(this, 'Cluster', {
      vpc,
      containerInsights: true, // metrics for the benchmark
    });

    // The L3 wires service + ALB + target group + listener + log group.
    const service = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'Svc', {
      cluster,
      cpu: 512, // 0.5 vCPU
      memoryLimitMiB: 1024, // 1 GB
      desiredCount: 2, // 2 tasks across 2 AZs
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64, // Graviton: ~20% cheaper
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
      taskImageOptions: {
        // Builds and pushes the image from ../app at deploy time.
        image: ecs.ContainerImage.fromAsset('../app', { platform: cdk.aws_ecr_assets.Platform.LINUX_ARM64 }),
        containerPort: 8080,
        environment: { DATA_BUCKET: dataBucket.bucketName },
      },
      publicLoadBalancer: true,
      assignPublicIp: false, // tasks stay in private subnets
      taskSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
    });

    // Point the ALB health check at /healthz.
    service.targetGroup.configureHealthCheck({
      path: '/healthz',
      healthyHttpCodes: '200',
      interval: cdk.Duration.seconds(15),
    });

    // Least-privilege task role: read ONLY the public/ prefix of the bucket.
    service.taskDefinition.taskRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ['s3:GetObject'],
        resources: [`${dataBucket.bucketArn}/public/*`],
      }),
    );

    // Target-tracking autoscaling on CPU.
    const scaling = service.service.autoScaleTaskCount({ minCapacity: 2, maxCapacity: 6 });
    scaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 50,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    cdk.Tags.of(this).add('team', 'crunch-aws');
    cdk.Tags.of(this).add('service', 'fastapi-spectrum');
    cdk.Tags.of(this).add('environment', 'dev');

    new cdk.CfnOutput(this, 'Url', { value: `http://${service.loadBalancer.loadBalancerDnsName}` });
    new cdk.CfnOutput(this, 'BucketName', { value: dataBucket.bucketName });
  }
}
```

---

## Step 4 — Deploy

```bash
cdk bootstrap          # once per account/region, if not already done in Week 3
cdk deploy
```

CDK builds the arm64 image, pushes it to an ECR repo it manages, and stands up the cluster, service, and ALB. Watch the output for `InfraFargateStack.Url`.

Seed the bucket so `/read` has something to read:

```bash
BUCKET=$(aws cloudformation describe-stacks --stack-name InfraFargateStack \
  --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)
echo "hello from fargate" | aws s3 cp - "s3://$BUCKET/public/hello.txt"
echo "you should never read this from the task" | aws s3 cp - "s3://$BUCKET/private/secret.txt"
```

---

## Step 5 — Verify (the green marker)

```bash
URL=$(aws cloudformation describe-stacks --stack-name InfraFargateStack \
  --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text)

curl -s "$URL/healthz"
# {"status":"ok"}

curl -s "$URL/compute?n=28"
# {"n":28,"result":317811}

curl -s "$URL/read?key=public/hello.txt"
# {"key":"public/hello.txt","first_line":"hello from fargate"}

# Prove the negative — the task role can't read the private prefix:
curl -s "$URL/read?key=private/secret.txt"
# {"detail":"AccessDenied"}
```

That last `AccessDenied` is not a bug — it's the proof your task role is scoped to `public/*` only. **Screenshot it.** Same idea returns in the EKS exercise with IRSA.

---

## Expected output

```
$ curl -s http://InfraF-Svc-XXXX.eu-west-1.elb.amazonaws.com/healthz
{"status":"ok"}
$ curl -s ".../compute?n=28"
{"n":28,"result":317811}
$ curl -s ".../read?key=public/hello.txt"
{"key":"public/hello.txt","first_line":"hello from fargate"}
$ curl -s ".../read?key=private/secret.txt"
{"detail":"AccessDenied"}
```

---

## Acceptance criteria

- [ ] `app/main.py`, `requirements.txt`, and `Dockerfile` exist and the image builds for `linux/arm64`.
- [ ] `cdk deploy` succeeds; tasks run in **private** subnets with no public IP.
- [ ] `curl .../healthz` returns `{"status":"ok"}` against the real ALB DNS name.
- [ ] `/read?key=public/hello.txt` succeeds; `/read?key=private/secret.txt` returns `AccessDenied`.
- [ ] Autoscaling is configured (min 2, max 6, CPU target 50%).
- [ ] Every resource is tagged `team`, `service`, `environment`.
- [ ] Record the steady-state monthly cost (2 tasks + ALB) for the mini-project's table.

## Tear-down

```bash
cdk destroy
```

(The bucket auto-empties because `autoDeleteObjects: true`. Fargate has no idle node cost, but the ALB bills hourly — don't leave it up over the week.)

---

## Hints

<details>
<summary>If `Vpc.fromLookup` fails</summary>

`fromLookup` needs your account/region set (`CDK_DEFAULT_ACCOUNT`/`CDK_DEFAULT_REGION` or `env` on the stack) and uses the context cache in `cdk.context.json`. If your Week-4 VPC isn't named `c19-week04-vpc`, look it up by tags instead: `ec2.Vpc.fromLookup(this, 'Vpc', { tags: { Name: 'your-vpc-name' } })`.
</details>

<details>
<summary>If the image push is slow or fails on Apple Silicon</summary>

You're already on arm64, so the `LINUX_ARM64` build is native — fast. On an x86 laptop, CDK uses Docker buildx emulation, which is slow; that's expected. Ensure `docker buildx` is available (`docker buildx version`).
</details>

<details>
<summary>If tasks never become healthy</summary>

Check the ECS service events and the target-group health in the console. The usual causes: the container listens on the wrong port (must be 8080 to match `containerPort`), the health check path is wrong (must be `/healthz`), or the task can't reach ECR/S3 because the VPC is missing the interface/gateway endpoints from Week 4. CloudWatch Logs (the L3 created a log group) will show uvicorn's startup line.
</details>
