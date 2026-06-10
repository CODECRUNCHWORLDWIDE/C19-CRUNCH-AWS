# Week 5 — Exercises

Three deployments of **one** application. The discipline of the week: the FastAPI app never changes — only the platform around it does. Do them in order; exercise 1 builds the container image and the app code that 2 and 3 reuse.

## The shared application

All three exercises deploy the same tiny FastAPI service:

- `GET /healthz` → `{"status":"ok"}` (the load balancer / API Gateway health check target).
- `GET /compute?n=...` → does a small CPU loop (a deterministic Fibonacci-ish burn) so cold-start and CPU cost are measurable.
- `GET /read?key=...` → reads an object from S3 (`s3://$DATA_BUCKET/<key>`) and returns its first line — this is what exercises the platform's *identity* story (task role, IRSA, or Lambda execution role).

You write that app once in exercise 1. Exercises 2 and 3 reuse the identical `app/main.py`.

## Index

1. **[Exercise 1 — FastAPI on ECS Fargate behind an ALB](exercise-01-fargate-alb.md)** — write the app + Dockerfile, push to ECR, deploy with TypeScript CDK using `ApplicationLoadBalancedFargateService`, with autoscaling and a least-privilege task role. (~2h)
2. **[Exercise 2 — The same app on EKS with Karpenter Spot + IRSA](exercise-02-eks-karpenter-irsa.py)** — Python CDK stack that creates the EKS cluster, a small On-Demand managed node group, installs Karpenter / LB Controller via Helm, and wires an IRSA role scoped to one S3 prefix. You prove the negative (pod cannot read a forbidden prefix). (~2.5h)
3. **[Exercise 3 — The same app as Lambda + API Gateway behind CloudFront](exercise-03-lambda-apigw-cloudfront.ts)** — TypeScript CDK that packages the identical FastAPI app as a container-image Lambda via the Lambda Web Adapter, fronts it with an HTTP API and a CloudFront distribution, with the execution role scoped to the same S3 prefix. (~2h)

## How to work the exercises

- **Type the IaC yourself.** Do not copy-paste the whole file. The muscle memory of wiring an IRSA trust policy by hand is the point — you will debug it for real in the capstone.
- **Deploy to your Week-4 VPC.** Every workload lands in private subnets. No public IPs on tasks/nodes.
- **Tag everything** with `team`, `service=fastapi-spectrum`, `environment=dev`. The mini-project needs a cost breakdown and you can't produce it without tags.
- **Tear EKS down nightly.** Exercise 2 ships a `cdk destroy` reminder and a cron pattern. The control plane bills idle.
- Every exercise ends with a working `curl` against the deployed endpoint. If `curl https://.../healthz` doesn't return `{"status":"ok"}`, you're not done.

## The recurring marker

C19 uses a recurring "it's actually live" marker. Every exercise ends green when you see, against the real deployed URL:

```
$ curl -s https://<endpoint>/healthz
{"status":"ok"}
```

If that line doesn't print against a real AWS endpoint (not localhost), the exercise is not finished.

There are no solutions checked in beyond the starter code in these files. The course is open source — full solutions live in forks. After you finish, search GitHub for `c19-week-05` to compare.
