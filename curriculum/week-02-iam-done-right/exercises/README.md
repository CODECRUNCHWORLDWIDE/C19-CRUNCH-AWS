# Week 2 — Exercises

Three exercises, in order. Do them in order — Exercise 1 stands up the three-account topology and the human-access layer; Exercise 2 adds the permission boundary to the `dev` account it created; Exercise 3 runs Access Analyzer across all three. Together they are the skeleton of the mini-project.

Budget about **9 hours** total. None of these exercises provisions billable compute — IAM, IAM Identity Center, the policy simulator, and Access Analyzer are all free. The only cost risk is leaving a NAT Gateway or EC2 instance running from a previous week, so confirm Week 1's teardown is clean before you start.

| Exercise | File | What you build | Time |
|---|---|---|---|
| 1 | [exercise-01-three-account-identity-center.md](./exercise-01-three-account-identity-center.md) | A guided build of the `identity`/`dev`/`prod` topology: an Organization with the three accounts, IAM Identity Center with one permission set, and human users who assume `CrossAccountDeveloper` into `dev` and `CrossAccountReadOnly` into `prod`. Starter + solution CDK and CLI. | ~3h |
| 2 | [exercise-02-permission-boundary.ts](./exercise-02-permission-boundary.ts) | A runnable CDK TypeScript stack that defines the `developer-boundary` managed policy and a bounded developer role, then a test (`aws iam simulate-principal-policy`) that proves an over-privileged inline policy is neutralized by the boundary. | ~3h |
| 3 | [exercise-03-access-analyzer.py](./exercise-03-access-analyzer.py) | A runnable Python (boto3) script that enables external-access and unused-access analyzers, lists every finding, classifies each, and prints a triage report you can paste into your journal. | ~3h |

## Conventions used in all three

- **Account IDs** are placeholders: `111111111111` = `identity`, `222233334444` = `dev`, `333344445555` = `prod`. Replace with your real IDs (or your single learner account in fallback mode).
- **Region** is `us-east-1` unless noted. Identity Center is provisioned in one region per Organization; pick one and stay there.
- **Profiles** follow Week 1: `identity-sso`, `dev`, `prod`. The `dev`/`prod` profiles are *derived* — they assume a role using the `identity-sso` session as their source (`source_profile = identity-sso` in `~/.aws/config`).
- **Every `Resource: "*"` and `Principal: "*"`** you write must carry a one-line comment justifying it, per the week's rule. The solution code shows the form.

## How to check your work

Each exercise has an explicit **acceptance criteria** block and a **smoke output** showing what success looks like. The single most important check, in all three, is: *can you read the policy you wrote out loud and say what it allows and denies?* If you cannot, you have not finished, regardless of what the console shows.

When you finish, you should have:

- A working three-account Organization with Identity Center login.
- A developer role in `dev` that is bounded and provably cannot escalate.
- A read-only role in `prod` that humans can assume but not write through.
- A clean (or fully-triaged) Access Analyzer report across all three accounts.

That is the mini-project's foundation — keep the code, you will extend it.
