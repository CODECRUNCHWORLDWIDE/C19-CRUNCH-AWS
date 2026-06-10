# Week 7 — Exercises

Three exercises that build on each other into one pipeline. Do them in order: Exercise 1 stands up the GitHub-triggered build-and-push pipeline, Exercise 2 adds the blue/green ECS deploy with a canary and auto-rollback onto the end of it, and Exercise 3 adds a sibling Lambda's traffic shifting into the same pipeline. By the end you have the spine of the mini-project.

## Index

1. **[Exercise 1 — GitHub-triggered pipeline → lint/test → multi-arch CodeBuild → ECR](exercise-01-github-pipeline-multiarch-ecr.md)** — guided, with steps, starter + solution CDK and `buildspec.yml`, and the expected console/CLI output. Build a CodePipeline triggered by GitHub that runs lint and test in parallel, then a CodeBuild project that builds a `linux/amd64`+`linux/arm64` image with `buildx` and pushes a single multi-arch manifest to ECR. (~90 min)
2. **[Exercise 2 — Blue/green ECS Fargate deploy with a 10% canary and alarm rollback](exercise-02-ecs-blue-green-canary.ts)** — runnable CDK (TypeScript). Add a `deploy` stage that does a CodeDeploy blue/green onto ECS Fargate: two target groups, one listener, `Canary10Percent5Minutes`, and a CloudWatch 5XX alarm that triggers automatic rollback. Includes a deliberate-break drill. (~90 min)
3. **[Exercise 3 — Lambda canary / linear traffic shifting in the same pipeline](exercise-03-lambda-traffic-shifting.py)** — runnable CDK (Python). Add a sibling Lambda function with versions, an alias, and a `LambdaDeploymentGroup` doing canary (then linear) traffic shifting, gated by a pre-traffic smoke-test hook and an error-rate alarm. (~75 min)

## How to work the exercises

- Read the prompt. Skim the cited docs; do not memorize them.
- **Type the CDK yourself.** Do not copy-paste the solution wholesale. The point is that the construct names and the wiring become reflexes.
- `cdk synth` *before* `cdk deploy`. Read the generated CloudFormation. Grep the IAM for `Resource: "*"` and ask whether each wildcard is justified (Lecture 1).
- Every exercise ends with a real artifact: a green pipeline run, a multi-arch manifest in ECR, a blue/green deployment that you watched shift and then deliberately rolled back.
- **The rollback drill is mandatory, not optional.** Exercise 2 is not done until you have deliberately shipped a broken build and watched CodeDeploy revert to blue on its own. A deploy you have not rolled back is a deploy you do not understand.
- Tear down with `cdk destroy` when you finish each session — CodePipeline charges per active pipeline per month, ECS Fargate charges per running task, and a forgotten blue/green deploy leaves double capacity running. Check the ECS console for orphaned task sets after a failed deploy.

## Cost note

These exercises fit in low-double-digit dollars if you tear down nightly. The line items: CodeBuild minutes (a multi-arch build on `LARGE` is a few minutes per run), CodePipeline (\$1/active pipeline/month), ECS Fargate tasks (per-second billing while running; blue/green doubles it during a deploy), an ALB (~\$0.025/hour while it exists), and ECR storage (pennies with the lifecycle policy). The ALB is the silent cost if you leave it up — `cdk destroy` it when you stop for the day.

There are no solutions checked in beyond the starter+solution shown inline in each exercise. The course is open source — fuller solutions live in forks. After you finish, search GitHub for `c19-week-07` to compare against other cohorts.
