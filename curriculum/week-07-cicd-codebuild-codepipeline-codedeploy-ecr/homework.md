# Week 7 Homework

Six practice problems that revisit the week's topics. The full set should take about **5 hours**. Work in your Week 7 Git repository so each problem produces at least one commit you can point to later.

Each problem includes:

- A short **problem statement**.
- **Deliverables** and **acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

---

## Problem 1 — Audit a pipeline role for over-grants

**Problem statement.** Take the CDK pipeline you built in Exercise 1. Run `cdk synth` and extract the IAM policy attached to the **CodeBuild build role**. For every statement, write down (a) the actions, (b) the resource scope, and (c) whether each `Resource: "*"` is genuinely unscopable or just lazy. Then write a one-paragraph threat statement: "If this role's credentials leaked, an attacker could ..."

**Deliverables.**

- `notes/build-role-audit.md` with the extracted policy, the per-statement table, and the threat paragraph.

**Acceptance criteria.**

- The audit identifies `ecr:GetAuthorizationToken` as the one action that legitimately requires `Resource: "*"` (it is account-scoped, not repo-scoped) and confirms every *other* action is resource-scoped.
- The threat paragraph correctly bounds the blast radius (can push images to one repo; cannot deploy, cannot pass roles, cannot touch IAM).
- File committed.

**Hint.** `cdk synth > template.yaml`, then search for the `AWS::IAM::Policy` resource whose role references the build project. Lecture 1, §1.2 and §1.7.

**Estimated time.** 45 minutes.

---

## Problem 2 — Write the permission boundary and prove it blocks an escalation

**Problem statement.** Implement the Lecture-1 permission boundary (§1.3) as a CDK `ManagedPolicy`, apply it at the `App` level via an Aspect, and then deliberately add a statement to one of your roles that grants `iam:CreateUser` and `iam:AttachUserPolicy`. Deploy. Then, from a session using that role, attempt to create an IAM user. Capture the `AccessDenied`.

**Deliverables.**

- `notes/boundary-proof.md` with the boundary policy, the over-granting statement you added, and the `AccessDenied` output proving the boundary's explicit deny won.

**Acceptance criteria.**

- The boundary denies IAM-user creation, `*FullAccess`/`AdministratorAccess` attachment, and destructive KMS actions.
- The proof shows the role *has* `iam:CreateUser` in its identity policy but is *still* denied because the boundary's deny intersects it to nothing.
- File committed.

**Hint.** The effective permission is the intersection of the identity policy and the boundary; an explicit deny in either always wins. Week 2 IAM mechanics + Lecture 1, §1.3.

**Estimated time.** 60 minutes.

---

## Problem 3 — Multi-arch verification and the Graviton cost delta

**Problem statement.** Take the multi-arch image your Exercise 1 pipeline pushed. Verify it carries both `linux/amd64` and `linux/arm64`. Then compute the monthly Fargate cost of running 2 tasks (0.5 vCPU, 1 GB) 24/7 on **x86** vs **arm64** in your region, using the current Fargate pricing page. State the dollar delta and the percentage.

**Deliverables.**

- `notes/multiarch-cost.md` with the `buildx imagetools inspect` output, both cost calculations (show the per-vCPU-hour and per-GB-hour numbers you used), and the delta.

**Acceptance criteria.**

- The inspect output shows both architectures under one manifest list.
- The cost calculation uses real current numbers from the Fargate pricing page (cited with the date you pulled them), and the arm64 figure is roughly 20% lower per vCPU-hour.
- The note states the absolute monthly dollar delta for the 2-task workload.

**Hint.** Fargate cost = (vCPU × vCPU-hour-price + GB × GB-hour-price) × hours × tasks. Resources page has the pricing URL; the date matters because prices change.

**Estimated time.** 45 minutes.

---

## Problem 4 — Read a CodeDeploy AppSpec and find the bug

**Problem statement.** A teammate's ECS deploy hangs forever at the `BeforeAllowTraffic` step and eventually times out. Here is their `appspec.yaml`:

```yaml
version: 0.0
Resources:
  - TargetService:
      Type: AWS::ECS::Service
      Properties:
        TaskDefinition: <TASK_DEFINITION>
        LoadBalancerInfo:
          ContainerName: order-service
          ContainerPort: 8080
Hooks:
  - BeforeAllowTraffic: "arn:aws:lambda:us-east-1:111122223333:function:pre-traffic-check"
```

The pre-traffic Lambda exists and runs (you see its logs), but the deploy never proceeds. Identify the bug and write the fix.

**Deliverables.**

- `notes/appspec-bug.md` naming the bug and giving the corrected hook code.

**Acceptance criteria.**

- The note identifies that the hook Lambda runs but never calls `codedeploy:PutLifecycleEventHookExecutionStatus`, so CodeDeploy waits forever for a status it never receives.
- The fix shows the hook calling `put_lifecycle_event_hook_execution_status` with the `deploymentId` and `lifecycleEventHookExecutionId` from the event, plus the IAM permission the hook's role needs.
- File committed.

**Hint.** A lifecycle hook must *report* its result back to CodeDeploy. Lecture 2, §2.4–§2.5; Exercise 3's hook code.

**Estimated time.** 30 minutes.

---

## Problem 5 — Design a GitHub OIDC trust policy for three environments

**Problem statement.** Your team deploys from GitHub to three AWS accounts: `dev` (any branch), `stage` (the `main` branch), and `prod` (only through a protected GitHub Environment named `production`). Write the three IAM trust policies (one per account's deploy role), each scoped as tightly as the environment warrants. Explain why `prod` uses the `environment:` form of `sub` rather than the `ref:` form.

**Deliverables.**

- `notes/oidc-three-envs.md` with the three trust policies and the explanation.

**Acceptance criteria.**

- `dev` allows `repo:org/repo:ref:refs/heads/*` (or `pull_request` if you build PRs there); `stage` allows `repo:org/repo:ref:refs/heads/main`; `prod` allows `repo:org/repo:environment:production`.
- All three pin `aud` to `sts.amazonaws.com`.
- The explanation correctly states that the `environment:` form forces the run through a GitHub Environment, which can require manual approval / wait timers / restricted branches — protection the `ref:` form does not give.

**Hint.** The `sub` claim format varies by trigger: `ref:refs/heads/<branch>`, `environment:<name>`, `pull_request`. Lecture 2, §2.6; Challenge 1 hint 2.

**Estimated time.** 45 minutes.

---

## Problem 6 — The rollback runbook

**Problem statement.** Write a one-page runbook entry titled "Canary alarm fired — what now?" for the on-call engineer who gets paged when the ECS blue/green canary auto-rolls-back. It must cover: how to confirm the rollback happened (the exact `aws deploy` commands), how to confirm blue was never impacted, where to find the green tasks' logs to diagnose *why* the canary failed, and the decision tree for next steps (re-deploy a fix vs hold).

**Deliverables.**

- `runbook/canary-rollback.md` — the runbook entry.

**Acceptance criteria.**

- Includes the `aws deploy get-deployment` command showing `status: Stopped` + `rollbackInfo`, and a CloudWatch query to confirm blue's 5XX stayed flat.
- Includes the CloudWatch Logs path to the green task set's logs and one sentence on what to look for (the error that spiked 5XX).
- The decision tree is concrete: when to roll forward with a fix, when to hold and investigate, who to escalate to.
- File committed.

**Hint.** The mini-project requires you to actually trigger this rollback; write the runbook from what you observed, not from imagination. Lecture 2, §2.3; Exercise 2's drill section.

**Estimated time.** 45 minutes.

---

## Submission

Push the entire `notes/` and `runbook/` directories to your Week 7 Git repository. The instructor reviews by:

1. Reading each note and runbook entry.
2. Re-running any CLI commands attached and verifying the outputs are real (e.g., the `AccessDenied` in Problem 2, the multi-arch manifest in Problem 3).
3. Cross-checking the cited pricing/doc URLs and the IAM scoping claims.

A submission whose notes are present and whose captured outputs are real is a pass. The most common review-fail is "the note claims the boundary blocks X but the captured output does not actually show the deny" — capture the real output, not a description of it.

---

## Rubric

| Component | Weight | Pass bar |
|---|---|---|
| P1 — Build-role audit | 15% | Correctly identifies the one justified `*` and bounds the blast radius. |
| P2 — Permission boundary proof | 20% | Shows a real `AccessDenied` where the boundary's deny beats an over-granting identity policy. |
| P3 — Multi-arch + cost delta | 15% | Real manifest-list output + real Fargate numbers with a correct ~20% arm64 delta. |
| P4 — AppSpec bug | 15% | Names the missing `PutLifecycleEventHookExecutionStatus` and gives the fix. |
| P5 — OIDC three-env trust | 20% | Three correctly-scoped `sub` claims; correct rationale for the `environment:` form on prod. |
| P6 — Rollback runbook | 15% | Concrete commands + a real decision tree drawn from an observed rollback. |

A pass on the homework is 70% across the six problems. The mini-project is where the real grade lives; treat the homework as the drills that make the mini-project land.

---

**References**

- IAM — Permissions boundaries: <https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html>
- AWS CodeDeploy — AppSpec hooks: <https://docs.aws.amazon.com/codedeploy/latest/userguide/reference-appspec-file.html>
- AWS Fargate pricing: <https://aws.amazon.com/fargate/pricing/>
- GitHub — OIDC subject claims: <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect>
- AWS CLI — `deploy get-deployment`: <https://docs.aws.amazon.com/cli/latest/reference/deploy/get-deployment.html>
