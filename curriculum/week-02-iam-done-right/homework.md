# Week 2 Homework

Six problems that drill the week's IAM skills until they are reflexes. Budget about **6 hours** total. Work in your Week 2 Git repository so each problem produces at least one commit. Several problems use the IAM policy simulator (`aws iam simulate-custom-policy` / `simulate-principal-policy`) — that is on purpose. By Sunday, reaching for the simulator to *prove* a claim about a policy should feel as natural as running a test.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — Read five policies out loud, in writing

**Problem statement.** Find five real IAM policies — from the AWS managed-policy catalog (`aws iam list-policies --scope AWS`), your own past projects, or any open-source `cdk`/`terraform` repo on GitHub. For each, write the four-line read-out-loud (effect / what / where / when) and then one sentence: *is this least-privilege, and if not, what is the single most over-broad thing in it?*

Pick at least one AWS-managed policy that is famously broad (e.g. `PowerUserAccess` or `AmazonS3FullAccess`) and one you wrote or found in the wild.

**Acceptance criteria.**

- File `homework/p1-read-out-loud.md` with five entries, each with the four-line reading and the one-sentence verdict.
- At least one AWS-managed policy and at least one third-party/your-own policy.
- Committed.

**Hint.** `aws iam get-policy-version --policy-arn arn:aws:iam::aws:policy/PowerUserAccess --version-id $(aws iam get-policy --policy-arn arn:aws:iam::aws:policy/PowerUserAccess --query 'Policy.DefaultVersionId' --output text)` dumps the JSON. `PowerUserAccess` is `NotAction` on the IAM/Org namespaces — read what that actually permits.

**Estimated time.** 45 minutes.

---

## Problem 2 — Scope a `PassRole`

**Problem statement.** You are given this over-broad fragment:

```json
{
  "Effect": "Allow",
  "Action": ["ecs:RegisterTaskDefinition", "ecs:RunTask", "iam:PassRole"],
  "Resource": "*"
}
```

Rewrite it so that: ECS task-definition registration and task runs are scoped to one cluster's resources in account `111122223333` region `us-east-1`; and `iam:PassRole` is scoped to only the ECS task-execution roles under `arn:aws:iam::111122223333:role/ecs-task-exec-*` *and* pinned with `iam:PassedToService` to ECS. Then **prove** with the simulator that passing `arn:aws:iam::111122223333:role/admin` is denied while passing `arn:aws:iam::111122223333:role/ecs-task-exec-web` to ECS is allowed.

**Acceptance criteria.**

- File `homework/p2-passrole.json` with the corrected policy.
- File `homework/p2-proof.md` showing two `simulate-custom-policy` runs (admin role → not allowed; the ecs-task-exec role with `iam:PassedToService=ecs-tasks.amazonaws.com` → allowed) with the actual `EvalDecision` pasted in.
- Committed.

**Hint.** The service principal for ECS tasks in the `iam:PassedToService` condition is `ecs-tasks.amazonaws.com`. Pass it via `--context-entries ContextKeyName=iam:PassedToService,ContextKeyType=string,ContextKeyValues=ecs-tasks.amazonaws.com`.

**Estimated time.** 45 minutes.

---

## Problem 3 — Write a correct cross-account trust policy

**Problem statement.** Write the trust policy for a role `AuditReadOnly` in your `prod` account that may be assumed **only** by a specific role `arn:aws:iam::444455556666:role/security-auditor` in your audit account, **only** by principals inside your Org `o-abc123def4`, and **only** when MFA is present. Then write the matching *identity* policy that the `security-auditor` role needs in the audit account to be allowed to call `sts:AssumeRole` on the target.

**Acceptance criteria.**

- File `homework/p3-trust.json` (the trust policy on `AuditReadOnly`) and `homework/p3-caller-identity.json` (the identity policy on `security-auditor`).
- The trust policy includes `aws:PrincipalOrgID` and `aws:MultiFactorAuthPresent`.
- A short note (`homework/p3-notes.md`) explaining why **both** policies are required for the cross-account assume to work (the two-sided rule).
- Committed.

**Hint.** The trust policy `Principal` is `{ "AWS": "arn:aws:iam::444455556666:role/security-auditor" }`; the conditions go in the same statement. The caller-side identity policy is `Allow sts:AssumeRole` on `Resource: arn:aws:iam::<prod>:role/AuditReadOnly`.

**Estimated time.** 45 minutes.

---

## Problem 4 — Build and prove a read-only-except-secrets boundary

**Problem statement.** Author a permission boundary `analyst-boundary` (as a JSON managed policy) that says: an analyst may **read** anything (`*:Get*`, `*:List*`, `*:Describe*`) but may **not** read Secrets Manager secret values, may **not** read `kms:Decrypt`, and may **not** perform any write/delete action. Then, using `simulate-custom-policy` with the boundary as one of the policies and a broad `ReadOnlyAccess`-like allow as another, prove: `s3:ListBucket` = allowed, `secretsmanager:GetSecretValue` = denied, `dynamodb:DeleteTable` = denied.

**Acceptance criteria.**

- File `homework/p4-analyst-boundary.json`.
- File `homework/p4-proof.md` with three simulator runs and their actual decisions.
- The boundary uses an explicit `Deny` for the secret/KMS/write actions (not merely omission), and you explain in one sentence why an explicit deny is stronger than omission here.
- Committed.

**Hint.** A boundary is just a policy document; to simulate "identity ∩ boundary," put both documents in `--policy-input-list` and treat the deny statements as the load-bearing part. The "why explicit deny" answer: omission relies on no other policy granting it; an explicit deny holds even if a future identity policy or resource policy grants it.

**Estimated time.** 1 hour.

---

## Problem 5 — Resolve a synthetic Access Analyzer finding

**Problem statement.** Create (in your `dev` sandbox, or describe precisely if on the $0 track) an S3 bucket with a bucket policy that grants `s3:GetObject` to `Principal: "*"`. Enable an Access Analyzer account analyzer. Capture the external-access finding it raises. Then resolve it two ways and document both: (a) by adding an `aws:PrincipalOrgID` condition that scopes the grant to your Org, and (b) by archiving the finding *with* a written justification if the public access were intended. Show the finding before and after.

**Acceptance criteria.**

- File `homework/p5-analyzer.md` with: the `list-findings` output showing the finding, the plain-English explanation of what it meant, the corrected bucket policy, and the `list-findings` output after (the finding resolved/archived).
- You explain the difference between *resolving* (changing the policy so the access no longer exists) and *archiving* (acknowledging intended access).
- Committed.

**Hint.** `aws accessanalyzer list-findings --analyzer-arn <arn> --query 'findings[?status==\`ACTIVE\`]'`. After you tighten the bucket policy, the analyzer re-scans and the finding moves to `RESOLVED`. To archive, `update-findings --status ARCHIVED --ids <id>`.

**Estimated time.** 1 hour.

---

## Problem 6 — IAM reflection essay

**Problem statement.** Write a 350–450 word reflection at `homework/week-02-reflection.md` answering:

1. Before this week, how did you reason about IAM — as a union ("this policy plus that policy") or an intersection? Where did that mental model break?
2. Which of the five bug families (over-broad resource, missing condition, wrong attribute, `Not*` trap, ARN-granularity/escalation) will you be most likely to *write* yourself, and what habit will you adopt to catch it?
3. Explain "why your CDK deploy needs three roles" to a teammate who thinks one admin role is simpler. One paragraph.
4. What is one thing about IAM you still find genuinely confusing after this week, that you want Week 3 or later to clarify?

**Acceptance criteria.**

- File exists, 350–450 words, each numbered question in its own paragraph.
- Committed.

**Hint.** This is for *you*. Be honest about (4) especially — the confusing parts are where the real learning is, and naming them is how you close them.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 45 min |
| 2 | 45 min |
| 3 | 45 min |
| 4 | 1 h 0 min |
| 5 | 1 h 0 min |
| 6 | 30 min |
| **Total** | **~4 h 45 min** |

---

## Rubric

Graded out of 100. A pass is 70.

| Criterion | Weight | What full marks looks like |
|---|---:|---|
| **Correctness of policy edits** | 30 | Every corrected policy is valid, least-privilege, and uses the right ARN granularity and condition keys. No `*` survives without justification. |
| **Proof discipline** | 25 | Every claim about what a policy allows/denies is backed by a real `simulate-*` run with the actual `EvalDecision` pasted, not asserted. |
| **Evaluation-logic explanations** | 20 | You can name *why* each bug is dangerous in terms of the evaluation flow (deny-wins, intersection, two-sided cross-account, attribute trust). |
| **Cross-account & trust correctness** | 15 | The Problem 3 trust + caller policies are both present and correct; the two-sided rule is explained. |
| **Reflection honesty & clarity** | 10 | The essay engages the questions specifically, names a real confusion, and the three-roles explanation would actually convince a skeptic. |

When you've finished all six, push your repo and open the [mini-project](./mini-project/README.md). The mini-project reuses the boundary from Problem 4's shape and the trust policy from Problem 3 — so do these first.
