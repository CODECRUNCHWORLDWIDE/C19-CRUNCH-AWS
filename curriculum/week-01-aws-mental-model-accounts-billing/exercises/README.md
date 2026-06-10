# Week 1 — Exercises

Three focused drills that build the account-and-billing foundation. Do them in order: Exercise 2 assumes the account from Exercise 1, and Exercise 3 assumes the Organization from Exercise 2.

## Index

1. **[Exercise 1 — Root-lockdown runbook](exercise-01-root-lockdown-runbook.md)** — create a fresh AWS account, enable MFA on root, delete root access keys, set alternate contacts, and write the sealed-credential runbook. (~60 min)
2. **[Exercise 2 — Organization + SCP that denies a Region](exercise-02-org-with-scp-deny-region.tf)** — OpenTofu that builds an Organization with `dev` / `stage` / `prod` OUs and an SCP denying `us-east-1`, then *prove the deny*. (~75 min)
3. **[Exercise 3 — Budgets with email alerts](exercise-03-budgets-alerts.ts)** — AWS CDK (TypeScript) that creates three Budgets at `$5` / `$25` / `$80` wired to email notifications. (~60 min)

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the commands and code yourself.** Do not blind-copy. The point is reflexes you keep.
- **Always check `aws sts get-caller-identity` before a destructive action.** Know which account and role you are operating as.
- Every guardrail ends with a **proof**: attempt the blocked action and read the denial. A control you have not tested is a control you do not have.
- Watch the cost. Everything here is Free Tier or fractions of a cent. We tell you the cost of each step.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-01` to compare.

## A note on credentials

You will run these as an **administrative principal**, not as the root user. The recommended path:

1. Finish Exercise 1 (lock root).
2. Set up IAM Identity Center with an `AdministratorAccess` permission set assigned to yourself (Lecture 2 shows the consumer flow; the full setup is the first part of the mini-project).
3. `aws sso login --profile <your-admin-profile>` and `export AWS_PROFILE=<your-admin-profile>`.

If your Identity Center is not ready yet, you may temporarily use a bootstrap IAM user with an `AdministratorAccess` policy and MFA — but delete it and switch to SSO before the week ends. We do not keep long-lived IAM users for humans in this course.
