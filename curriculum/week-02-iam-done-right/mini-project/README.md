# Mini-Project — The Three-Account Identity Layer

> Deliver a working, code-defined identity foundation across three accounts: **IAM Identity Center** for humans, **`sts:AssumeRole` chains** into `dev` and `prod`, a **permission boundary** enforced on every developer role, and a **clean IAM Access Analyzer report**. This is not a toy. The identity layer you build here is reused *directly* in the C19 capstone's Identity requirements (Week 13+). Build it like you will live in it for three months, because you will.

This is the keystone deliverable of Phase 1. Weeks 1 (Organizations) and 2 (IAM) converge here into one artifact: the layer every later week assumes exists. When Week 4 deploys a VPC into `dev`, it assumes through the role you create here. When Week 7's pipeline deploys to `prod`, it assumes through the bounded role you create here. When Week 13's capstone needs "permission boundaries on all developer roles" and "IAM Identity Center for humans," it points at this repository.

**Estimated time:** ~8.5 hours (split across Thursday, Friday, Saturday in the suggested schedule).

---

## The topology you will build

Three accounts in one Organization:

```
                         AWS Organization (o-abc123def4)
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
 ┌──────────────┐            ┌──────────────┐             ┌──────────────┐
 │  identity    │            │     dev      │             │    prod      │
 │ 111111111111 │            │ 222222222222 │             │ 333333333333 │
 ├──────────────┤            ├──────────────┤             ├──────────────┤
 │ IAM Identity │            │ Developer    │             │ ReadOnly     │
 │ Center       │            │ role (bounded│             │ role (humans │
 │ (humans live │──assume──▶ │ by developer-│             │ assume; no   │
 │  here only)  │            │ boundary)    │  ──assume──▶ │ write path)  │
 │              │            │ Deploy role  │             │ Deploy role  │
 │ Permission   │            │ (bounded;    │             │ (bounded;    │
 │ set: Engineer│            │ assumed by   │             │ assumed only │
 │              │            │ CI only)     │             │ by CI)       │
 └──────────────┘            └──────────────┘             └──────────────┘
```

Rules of the topology:

- **Humans authenticate only in `identity`** via IAM Identity Center (`aws sso login`). No human has a long-lived access key anywhere. No human is an IAM user in `dev` or `prod`.
- **Humans reach `dev` with write access** by assuming a `Developer` role that is **bounded** by `developer-boundary` (no IAM writes, no KMS deletes, no `prod-*` S3).
- **Humans reach `prod` with read-only access** by assuming a `ReadOnly` role. There is *no* human write path to `prod` — production changes go through CI, which assumes a separate, bounded `Deploy` role.
- **Every role you create carries a permission boundary.** Not just the developer role — the deploy roles too. A role with no boundary is a finding in your own review.
- **Every trust policy enforces `aws:PrincipalOrgID`** so that only principals inside *your* Org can assume, even if an ARN leaks.
- **Access Analyzer runs in every account** and the report is clean (or every finding is triaged with a written justification).

---

## What you deliver

A public GitHub repo, `c19-week-02-identity-<yourhandle>`, containing a CDK (TypeScript) application plus a small Python verification tool, that provisions and proves the topology above. You provision per-account stacks (you will run `cdk deploy` against three profiles), and you ship a `verify/` tool that walks the whole topology and prints a green/red report.

### Repository layout

```
identity-layer/
├── README.md                       (architecture, setup, how to deploy each account, how to verify)
├── package.json
├── cdk.json
├── tsconfig.json
├── bin/
│   └── identity-layer.ts           (instantiates the per-account stacks)
├── lib/
│   ├── identity-center-stack.ts    (permission set + account assignments; deployed to mgmt/identity)
│   ├── dev-account-stack.ts        (Developer role + Deploy role, both bounded)
│   ├── prod-account-stack.ts       (ReadOnly role + Deploy role, both bounded)
│   ├── developer-boundary.ts       (the ManagedPolicy boundary, shared construct)
│   └── access-analyzer-stack.ts    (CfnAnalyzer: account + unused-access, per account)
├── verify/
│   ├── verify_topology.py          (assume the chain, prove each deny, list analyzer findings)
│   └── requirements.txt            (boto3)
├── tofu/                           (OPTIONAL stretch: the same boundary + roles in OpenTofu)
│   ├── main.tf
│   ├── variables.tf
│   └── boundary.tf
└── docs/
    ├── access-analyzer-report.md   (every finding, what it meant, how you resolved it)
    └── architecture.md             (the diagram above + the evaluation-flow walkthrough)
```

---

## Build it in phases

### Phase A — Identity Center for humans (≈2h)

You set up IAM Identity Center once, by hand, in the management account (it is largely a console/CLI bootstrap, not pure IaC in 2026 — the identity store is click-ops or SCIM, but permission sets and assignments *are* CDK-able via `aws-cdk-lib/aws-sso`).

1. Enable IAM Identity Center in the management account, region of your choice (it is regional; pick the one you will use all course).
2. Create one user in the Identity Center identity store (yourself), with MFA enforced.
3. In CDK, create **one permission set** named `Engineer` with a session duration of 1 hour and a relay state pointing at the console home. Attach a managed policy reference that grants the assume-role-into-member-accounts shape (see hints).
4. Create account assignments: assign your user the `Engineer` permission set in `dev` and in `prod`.
5. Verify: `aws sso login --profile engineer`, then `aws sts get-caller-identity --profile dev` returns an `assumed-role/AWSReservedSSO_Engineer_*` ARN in the `dev` account.

### Phase B — The cross-account roles (≈2.5h)

In `dev-account-stack.ts` and `prod-account-stack.ts`:

1. `Developer` role in `dev`: identity policy of `PowerUserAccess` (broad on purpose — the boundary is what makes it safe), trust policy that trusts the `Engineer` permission-set role *and* requires `aws:PrincipalOrgID == o-...` *and* `aws:MultiFactorAuthPresent == true`. Permission boundary: `developer-boundary`.
2. `ReadOnly` role in `prod`: identity policy of the AWS-managed `ReadOnlyAccess`, same trust shape (Org + MFA), boundary attached (a read-only boundary is still a boundary — defense in depth and a clean Analyzer report).
3. `Deploy` role in both `dev` and `prod`: trusted **only** by your CI's OIDC provider (or, if you have no CI yet, by a placeholder CI role ARN you note as "to be replaced in Week 7"), bounded, scoped to the resources the deploy actually touches. No human in the trust policy.
4. Apply the boundary to *every* role with `iam.PermissionsBoundary.of(this).apply(boundary)` at the stack level so you cannot forget one.

### Phase C — Prove the denies (≈1.5h)

`verify/verify_topology.py` (boto3) does the senior move — it does not trust the deploy, it *proves* it:

1. Assume `Developer` in `dev` (via the assumed SSO session), then call `iam simulate_principal_policy` for `iam:CreateUser`, `kms:ScheduleKeyDeletion`, `s3:GetObject` on a `prod-*` bucket — expect `explicitDeny` on the first three.
2. Assume `ReadOnly` in `prod`, attempt an `s3:PutObject` (expect `AccessDenied` at runtime *and* `implicitDeny`/`explicitDeny` in the simulator).
3. Confirm every role has a `PermissionsBoundary` set (`get_role` → assert the field is present).
4. Print a table: each check, expected decision, actual decision, PASS/FAIL. Exit non-zero if any FAIL.

### Phase D — Access Analyzer clean (≈1.5h)

1. `access-analyzer-stack.ts` creates an **account** analyzer (external-access) and an **unused-access** analyzer in each account (Analyzer is regional and per-type; the unused-access analyzer has a separate `type`).
2. After deploy, `list_findings` in each account. For **every** finding: either resolve it (tighten the policy) or, if it is intended (e.g. a deliberately Org-shared bucket), **archive it with a written justification** in `docs/access-analyzer-report.md`.
3. The report file has one entry per finding: the finding ID, the resource, what external access it flagged, what it *meant* in plain English, and your resolution (fixed / archived-with-reason).

---

## Acceptance criteria

- [ ] A public repo `c19-week-02-identity-<yourhandle>`.
- [ ] `cdk synth` succeeds for all stacks with **zero** errors.
- [ ] IAM Identity Center is enabled; one permission set (`Engineer`, 1-hour sessions) is assigned to your user in `dev` and `prod`. `aws sso login` then `aws sts get-caller-identity --profile dev` shows the SSO assumed-role ARN in the `dev` account.
- [ ] Every role created by the app — `Developer`, `ReadOnly`, both `Deploy` roles — has a permission boundary in its `PermissionsBoundary` slot. **Zero roles without a boundary.**
- [ ] Every cross-account trust policy enforces `aws:PrincipalOrgID` and (for human-assumable roles) `aws:MultiFactorAuthPresent: true`.
- [ ] `python verify/verify_topology.py` prints a table and **exits 0**, with these proven:
  - `Developer` → `iam:CreateUser` = `explicitDeny`
  - `Developer` → `kms:ScheduleKeyDeletion` = `explicitDeny`
  - `Developer` → `s3:GetObject` on `arn:aws:s3:::prod-*/*` = `explicitDeny`
  - `Developer` → `s3:GetObject` on a `dev` bucket = `allowed`
  - `ReadOnly` (prod) → `s3:PutObject` = denied
- [ ] `docs/access-analyzer-report.md` accounts for **every** finding in all three accounts: resolved or archived-with-justification. No untriaged findings.
- [ ] `docs/architecture.md` includes the topology diagram and a written walkthrough of the evaluation flow for one cross-account assume-role (SCP → trust policy → identity policy → boundary → session policy).
- [ ] `README.md` documents, for a fresh clone: prerequisites, the three CLI profiles, the exact `cdk deploy` command per account, and how to run `verify_topology.py`.
- [ ] **No long-lived access keys** anywhere in the deliverable. (`aws iam list-access-keys` across accounts returns none for any human.)
- [ ] Committed and pushed; `cdk synth` works on a fresh clone (no uncommitted local state, `.gitignore` excludes `cdk.out/` and `node_modules/`).

---

## Expected `verify_topology.py` output

```
Three-Account Identity Layer — Verification
account=dev (222222222222)  account=prod (333333333333)  org=o-abc123def4

CHECK                                                  EXPECTED      ACTUAL        RESULT
-----------------------------------------------------  ------------  ------------  ------
Developer role has permission boundary                 present       present       PASS
Developer -> iam:CreateUser                            explicitDeny  explicitDeny   PASS
Developer -> kms:ScheduleKeyDeletion                   explicitDeny  explicitDeny   PASS
Developer -> s3:GetObject  arn:...:prod-app/*          explicitDeny  explicitDeny   PASS
Developer -> s3:GetObject  arn:...:dev-app/*           allowed       allowed        PASS
ReadOnly  -> s3:PutObject  (prod)                      deny          deny           PASS
ReadOnly role has permission boundary                  present       present       PASS
Deploy(dev) role has permission boundary               present       present       PASS
Deploy(prod) role has permission boundary              present       present       PASS
Access Analyzer (dev)  untriaged findings              0             0              PASS
Access Analyzer (prod) untriaged findings              0             0              PASS

11 checks, 11 passed, 0 failed.
```

---

## Cost & teardown

This mini-project is **free**. IAM, IAM Identity Center, STS, and Access Analyzer have no per-resource charge. The unused-access analyzer has a per-resource-analyzed price in some regions — keep it on for the week (the cost on three near-empty accounts is cents) and **tear it down Sunday** with `cdk destroy AccessAnalyzer* --profile <each>`. Keep the roles and the boundary; Week 3's `cdk bootstrap` builds on them.

If you are running the $0 track on LocalStack: Identity Center and cross-account trust are real-AWS-only behaviors and will not fully emulate. You can still author and `cdk synth` everything, prove the boundary denies with `simulate-custom-policy` locally, and write the Access Analyzer report against the policy JSON by hand. Note in your journal which checks you could not run live.

---

## Reference snippets

You write the bulk of this yourself, but here are the load-bearing shapes so you spend your time on the architecture, not on guessing API surfaces.

### The cross-account trust policy (every human-assumable role)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_Engineer_*"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:PrincipalOrgID": "o-abc123def4" },
        "Bool": { "aws:MultiFactorAuthPresent": "true" }
      }
    }
  ]
}
```

### Forcing the boundary onto every role in a stack (CDK TypeScript)

```typescript
import { PermissionsBoundary } from 'aws-cdk-lib/aws-iam';

// At the top of your dev/prod stack constructor, after you create `boundary`:
PermissionsBoundary.of(this).apply(boundary);
// Now every iam.Role created in this stack inherits the boundary automatically.
// You cannot forget one — which is the entire point.
```

### Creating both analyzer types (CDK TypeScript)

```typescript
import { CfnAnalyzer } from 'aws-cdk-lib/aws-accessanalyzer';

new CfnAnalyzer(this, 'AccountAnalyzer', {
  type: 'ACCOUNT',
  analyzerName: 'external-access',
});

new CfnAnalyzer(this, 'UnusedAccessAnalyzer', {
  type: 'ACCOUNT_UNUSED_ACCESS',
  analyzerName: 'unused-access',
});
```

### The proof core (Python / boto3)

```python
import boto3

def simulate(session, role_arn, action, resource):
    iam = session.client("iam")
    result = iam.simulate_principal_policy(
        PolicySourceArn=role_arn,
        ActionNames=[action],
        ResourceArns=[resource],
    )
    return result["EvaluationResults"][0]["EvalDecision"]

# Expect "explicitDeny" for the three crown-jewel actions on the Developer role.
```

Wire `simulate_principal_policy` into a loop over your expected (action, resource, decision) tuples and you have the verification table the acceptance criteria ask for.

## What this feeds

| Later week | Uses this how |
|---|---|
| Week 3 (CDK bootstrap) | `cdk bootstrap` provisions deploy/file-publishing/exec roles that mirror your `Deploy` role; you will recognize every trust policy. |
| Week 4–11 (everything) | All deploys assume through the `Developer`/`Deploy` roles you created here. |
| Week 7 (CI/CD) | Replaces the placeholder CI trust on the `Deploy` roles with a real GitHub OIDC provider, and wires `simulate-principal-policy` + Analyzer custom-policy-checks into the pipeline. |
| Week 13–15 (capstone) | The capstone's Identity requirement ("IAM Identity Center for humans … permission boundaries on all developer roles") is *this artifact*, extended with Cognito for end users and IRSA on EKS. |

Do this one properly. It is the foundation you stand on for the rest of C19.
