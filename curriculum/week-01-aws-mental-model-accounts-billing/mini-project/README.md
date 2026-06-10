# Mini-Project — The Account & Billing Foundation

> Stand up the multi-account scaffold that every other week of C19 builds on: an AWS Organization with `dev` / `stage` / `prod` Organizational Units, a working Service Control Policy guardrail you have *proven* denies an action, an MFA-locked root user with a sealed-credential runbook, three Budgets that email you before the bill does, and a Cost & Usage Report flowing into S3 and queryable from Athena. No compute. No application. Just the foundation — done right, once.

This is the only week where the mini-project produces **no running application** and that is the entire point. Every later week's lab deploys *into* this scaffold, tags resources for the cost report you build here, and trusts the SCP guardrail and the Budgets you wire up now. If you cut a corner here, you pay for it in Week 5 when an EKS cluster racks up $72 and you have no idea, or in Week 13 when you discover your "prod" account was never actually isolated from "dev."

**This scaffold compounds.** The syllabus is explicit: *"This is the account-and-billing foundation every later week's lab and cost report builds upon."* Treat it as production infrastructure for your own learning, because it is.

**Estimated time:** ~7 hours (split across Thursday, Friday, Saturday, and a Sunday polish pass in the suggested schedule).

---

## What you will build

A single Git repository — `c19-week-01-foundation-<yourhandle>` — that contains the Infrastructure-as-Code and runbooks for a real, live account posture:

```
c19-week-01-foundation/
├── README.md                        # project overview + the cost number at the end
├── .gitignore                       # ignores *.tfstate, .env, cdk.out/, node_modules/, __pycache__/
├── runbook/
│   ├── root-lockdown.md             # the sealed-credential runbook (from Exercise 1)
│   ├── break-glass.md               # how to use root if everything else is locked out
│   └── account-inventory.md         # account ids, OU ids, the org tree, who-owns-what
├── org/                             # OpenTofu: the Organization, OUs, and SCPs
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── scp-deny-us-east-1.json
├── budgets/                         # AWS CDK (TypeScript): the three Budgets
│   ├── bin/budgets.ts
│   ├── lib/budgets-stack.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── cdk.json
├── billing/                         # the CUR → S3 → Athena pipeline
│   ├── athena-ddl.sql               # the external table with partition projection
│   ├── queries.sql                  # spend-by-service, spend-by-tag
│   └── REPORT.md                    # the actual numbers + interpretation
└── verify.sh                        # one script that proves every control is live
```

Everything in `org/`, `budgets/`, and `billing/` is real, applied infrastructure. Everything in `runbook/` is prose you will actually follow if you lock yourself out at 2am in Week 13.

---

## Rules

- **You operate as an SSO admin principal, never as root.** Finish the root lockdown first (Exercise 1), set up IAM Identity Center with an `AdministratorAccess` permission set for yourself, then `aws sso login`. Root is sealed in the runbook and used only for the handful of tasks that *require* it.
- **No long-lived IAM user keys for humans.** If you must bootstrap with an IAM user before Identity Center is ready, delete it before you submit.
- **Every control gets a proof.** A guardrail you have not tested is a guardrail you do not have. `verify.sh` must demonstrate each control is live — including attempting the SCP-blocked action and capturing the explicit deny.
- **Tag everything you create** with at least `team` and `environment`. The CUR breakdown is meaningless without tags, and you are establishing the tagging discipline the whole course depends on.
- **Region:** use `eu-west-1` as the home Region for the CUR bucket, Athena, and Budgets-adjacent resources, to match the course default. (Budgets and Organizations are global/`us-east-1`-anchored; that's expected and explained below.)
- **You may** read all AWS docs, the lecture notes, and the exercise files. **You may not** copy a classmate's `tfstate` or account ids.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c19-week-01-foundation-<yourhandle>` with the layout above.
- [ ] **Root is locked:** root has MFA enabled, **zero** access keys, and alternate billing/security/operations contacts are set. `runbook/root-lockdown.md` documents the sealed-envelope procedure and the break-glass procedure.
- [ ] **Organization is live:** an Organization exists in the management account with three OUs — `dev`, `stage`, `prod` — each containing at least the placeholder structure (a member account is ideal but a populated OU with the SCP attached is the minimum). `org/outputs.tf` emits the org id and the three OU ids.
- [ ] **SCP guardrail proven:** an SCP that denies all actions in `us-east-1` (except the global-service carve-outs) is attached to the `dev` OU. `verify.sh` runs an action in `us-east-1` from a principal in that OU and the output contains `with an explicit deny in a service control policy`.
- [ ] **Budgets live:** three monthly cost Budgets at `$5`, `$25`, and `$80`, each with `ACTUAL` and `FORECASTED` notifications wired to your email, deployed via `cdk deploy`. You have received and confirmed the SNS/email subscription (or the Budgets-native email).
- [ ] **CUR queryable:** a Cost & Usage Report (CUR 2.0 / Data Exports) delivers Parquet to your S3 bucket; an Athena external table reads it with partition projection; `billing/REPORT.md` contains the spend-by-service and spend-by-tag numbers (even if they are cents).
- [ ] **`verify.sh` is green:** running it prints a checklist where every line ends in `OK` (or the captured deny for the SCP check).
- [ ] **The cost number:** `README.md` ends with the actual figure from Cost Explorer for the week. It should round to **$0.00–$0.50**. If it is higher, explain why in one sentence (you forgot to tear something down, or a CUR backfill scanned more than expected).

---

## Suggested order of operations

Build incrementally. Each phase produces a commit and a working artifact.

### Phase 0 — Decide the topology (~20 min)

You have a choice for *how many real accounts* to create:

- **Minimum (free, recommended for the course):** one management account. Create the three OUs and attach the SCP to the `dev` OU. To *prove* the SCP, create one cheap member account under `dev` (new member accounts are free; you just need an email alias — `you+dev@domain` works with Gmail-style sub-addressing) and assume a role into it. SCPs do **not** apply to the management account, so you cannot prove a deny from the management account itself. You need at least one member account under the constrained OU.
- **Fuller (still free):** create three member accounts, one per OU (`dev`, `stage`, `prod`), each with an email alias. This is closer to what the capstone uses and what you will extend in Week 2.

Write your choice and the email-alias scheme into `runbook/account-inventory.md`. Commit: `Phase 0: topology decision + inventory`.

> **Why the management account can't prove the SCP.** Service Control Policies never restrict the management (payer) account — by design, so you can never lock yourself out of org administration. The corollary: do not run workloads in the management account. Ever. It exists to administer the org and pay the bill. This is the single most important governance rule in this lecture's worth of material.

### Phase 1 — Lock root (~45 min)

Bring `runbook/root-lockdown.md` over from Exercise 1 and *actually execute it* on this account:

1. Sign in as root, enable a virtual or hardware MFA device.
2. Delete any root access keys (there should be none on a fresh account — confirm).
3. Set the three alternate contacts (Billing, Operations, Security) under Account settings.
4. Note the break-glass procedure: where the MFA seed/recovery codes live, who can reach them, and the exact tasks that *require* root (closing the account, changing the root email, some Route 53 domain transfers, restoring an accidentally-deleted S3 bucket policy that locked everyone out).

Commit: `Phase 1: root locked + runbook`.

### Phase 2 — IAM Identity Center + admin profile (~45 min)

1. Enable **IAM Identity Center** (the management account, `eu-west-1` or your chosen Region).
2. Create a permission set `AdministratorAccess` (use the AWS-managed `AdministratorAccess` policy for now; Week 2 replaces this with least-privilege + a permission boundary).
3. Create a user for yourself in the Identity Center directory and assign the permission set to the management account (and to member accounts if you created them).
4. Configure the CLI:
   ```bash
   aws configure sso
   # SSO start URL: https://d-xxxxxxxxxx.awsapps.com/start
   # SSO region:    eu-west-1
   # Pick the account + AdministratorAccess role, name the profile: mgmt-admin
   aws sso login --profile mgmt-admin
   export AWS_PROFILE=mgmt-admin
   aws sts get-caller-identity
   ```
5. Confirm `get-caller-identity` shows an `assumed-role` ARN with `AWSReservedSSO_AdministratorAccess` in it — **not** a root or IAM-user ARN.

Commit: `Phase 2: Identity Center + mgmt-admin SSO profile`.

### Phase 3 — The Organization + OUs + SCP (OpenTofu) (~90 min)

Adapt Exercise 2 into the `org/` directory. The shape:

- `aws_organizations_organization` with `aws` feature set (`ALL`) and the `SERVICE_CONTROL_POLICY` policy type enabled.
- Three `aws_organizations_organizational_unit` resources: `dev`, `stage`, `prod`, all children of the org root.
- An `aws_organizations_policy` of type `SERVICE_CONTROL_POLICY` whose document is `scp-deny-us-east-1.json`.
- An `aws_organizations_policy_attachment` binding that SCP to the `dev` OU.
- (If you chose the fuller topology) `aws_organizations_account` resources moved into their OUs.

The SCP document — deny everything in `us-east-1` except the global services that *transit* `us-east-1` (IAM, Organizations, Route 53, CloudFront, Support, WAF-global) so you don't break global control planes:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUsEast1ExceptGlobal",
      "Effect": "Deny",
      "Action": "*",
      "Resource": "*",
      "Condition": {
        "StringEquals": { "aws:RequestedRegion": "us-east-1" },
        "ForAllValues:StringNotEquals": {
          "aws:PrincipalServiceName": [
            "iam.amazonaws.com",
            "organizations.amazonaws.com",
            "route53.amazonaws.com",
            "cloudfront.amazonaws.com",
            "support.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

> **Heads-up on the carve-out.** The cleanest, most reliable carve-out in practice is to deny on `aws:RequestedRegion = us-east-1` and add a `NotAction` list of the global service prefixes (`iam:*`, `organizations:*`, `route53:*`, `cloudfront:*`, `sts:*`, `support:*`, `account:*`, `cur:*`, `ce:*`, `budgets:*`) rather than relying on `aws:PrincipalServiceName`. Both approaches appear in the wild; the `NotAction` form is what most production orgs ship because it is easier to reason about. Pick one, document why in `org/main.tf` comments, and make sure your proof action (e.g. `ec2:RunInstances` or `s3:CreateBucket` in `us-east-1`) is genuinely blocked. The point is to *see the explicit deny*, then understand exactly which actions the carve-out still permits.

```bash
cd org
tofu init
tofu plan
tofu apply
tofu output            # capture org id + the three OU ids into runbook/account-inventory.md
```

Commit: `Phase 3: Organization, OUs, deny-us-east-1 SCP`.

### Phase 4 — Prove the SCP deny (~30 min)

From a principal **inside the constrained OU** (a role in a `dev` member account), attempt a `us-east-1` action:

```bash
aws sso login --profile dev-admin     # or assume a role into the dev member account
export AWS_PROFILE=dev-admin
aws sts get-caller-identity           # confirm you are in the DEV account, not mgmt

# This must FAIL with an explicit deny:
aws ec2 run-instances \
  --region us-east-1 \
  --image-id ami-00000000000000000 \
  --instance-type t3.micro \
  --count 1 2>&1 | tee billing/scp-proof.txt
```

The output must contain `with an explicit deny in a service control policy`. (The bogus AMI id is fine — the SCP denies the call before any AMI validation happens.) Then run the **same call in `eu-west-1`** and confirm it gets *past* the SCP (it will fail for a different reason — bad AMI — which proves the deny is Region-scoped, not blanket).

Capture both in `billing/scp-proof.txt`. Commit: `Phase 4: proof of SCP deny (and Region-scoping)`.

### Phase 5 — Budgets via CDK (~60 min)

Adapt Exercise 3 into `budgets/`. Three `aws-cdk-lib/aws-budgets` `CfnBudget` resources at `$5`, `$25`, `$80`, each with `ACTUAL` at 100% and `FORECASTED` at 100% notifications to your email.

```bash
cd budgets
npm install
npx cdk bootstrap aws://<MGMT_ACCOUNT_ID>/eu-west-1   # one-time per account/Region
npx cdk deploy
```

Confirm the email subscription (AWS sends a confirmation for SNS-backed notifications; Budgets-native email needs no confirmation but check it arrives by lowering one threshold to `$0.01` temporarily, then restoring it). Commit: `Phase 5: $5/$25/$80 Budgets via CDK`.

> **Budgets is global, anchored in `us-east-1`.** The Budgets API lives in `us-east-1` regardless of where you deploy. CDK handles this, but if you ever call the Budgets API directly, target `us-east-1`. This is one of the "global service" facts from Lecture 1 made concrete.

### Phase 6 — CUR → S3 → Athena (~90 min)

Complete the Challenge pipeline and bring the artifacts into `billing/`:

1. Create the CUR bucket in the management account (`cur-<account-id>-<year>`), Block Public Access on.
2. Configure a Standard data export (CUR 2.0) named `crunch-cur` → Parquet → daily → resource IDs on → the bucket's `cur/` prefix.
3. Activate `team` and `environment` as cost-allocation tags (Billing console). Tag the CUR bucket itself so a non-null row appears.
4. Register the Athena table with partition projection (`billing/athena-ddl.sql`).
5. Run the two queries (`billing/queries.sql`) and paste the real numbers into `billing/REPORT.md`.

The CUR's first delivery can take **up to 24 hours** — start this Thursday, not Saturday night. Commit: `Phase 6: CUR pipeline + REPORT`.

### Phase 7 — `verify.sh` + the cost number (~40 min)

Write `verify.sh` so a teammate (or future-you) can confirm the whole posture in one run:

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${AWS_PROFILE:?set AWS_PROFILE to your mgmt-admin profile}"

echo "== who am I =="
aws sts get-caller-identity --query 'Arn' --output text

echo "== root has no access keys (expect: account summary, AccountAccessKeysPresent = 0) =="
aws iam get-account-summary --query 'SummaryMap.AccountAccessKeysPresent' --output text

echo "== root MFA enabled (expect: 1) =="
aws iam get-account-summary --query 'SummaryMap.AccountMFAEnabled' --output text

echo "== organization exists =="
aws organizations describe-organization --query 'Organization.Id' --output text

echo "== three OUs present =="
ROOT_ID=$(aws organizations list-roots --query 'Roots[0].Id' --output text)
aws organizations list-organizational-units-for-parent --parent-id "$ROOT_ID" \
  --query 'OrganizationalUnits[].Name' --output text

echo "== SCP attached to dev OU =="
DEV_OU=$(aws organizations list-organizational-units-for-parent --parent-id "$ROOT_ID" \
  --query "OrganizationalUnits[?Name=='dev'].Id | [0]" --output text)
aws organizations list-policies-for-target --target-id "$DEV_OU" \
  --filter SERVICE_CONTROL_POLICY --query 'Policies[].Name' --output text

echo "== three budgets present =="
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws budgets describe-budgets --account-id "$ACCOUNT_ID" \
  --query 'Budgets[].BudgetLimit.Amount' --output text

echo "== CUR data is landing =="
aws s3 ls "s3://cur-${ACCOUNT_ID}-$(date +%Y)/cur/" --recursive | head -n 3

echo "ALL CHECKS RAN — review the values above; each should be non-empty/OK."
```

Then read Cost Explorer (or your Athena spend-by-service query) and write the actual dollar figure into the bottom of `README.md`. Commit: `Phase 7: verify.sh + cost number`.

---

## Example `README.md` ending

```md
## Cost for the week

| Source | Amount |
|--------|-------:|
| S3 (CUR storage) | $0.00 |
| Athena (query scans) | $0.01 |
| Everything else (Org, SCP, Budgets, Identity Center) | $0.00 |
| **Total** | **$0.01** |

Pulled from Cost Explorer on 2026-06-14. Organizations, OUs, SCPs, Budgets,
and Identity Center are free. The only spend is a single Athena query scan and
a few KB of Parquet in S3.
```

---

## Rubric

| Criterion | Weight | What "great" looks like |
|----------|-------:|-------------------------|
| Root lockdown + runbook | 15% | MFA on, zero keys, alternate contacts set; runbook is a procedure a stranger could follow at 2am |
| Organization + OUs | 15% | Org with three OUs, IaC in `org/`, outputs captured in the inventory |
| SCP proven | 20% | The explicit-deny output is captured *and* the Region-scoping is demonstrated (same call works in `eu-west-1`) |
| Budgets | 15% | Three Budgets at the right thresholds, email confirmed received, deployed via CDK not the console |
| CUR → Athena | 20% | Parquet landing, partition-projection table, both queries return real numbers, REPORT interprets them |
| `verify.sh` + cost number | 10% | One script proves the whole posture; the README ends with the real (tiny) dollar figure |
| Tagging + hygiene | 5% | Resources tagged `team`/`environment`; no committed state/secrets; SSO not root |

---

## What this prepares you for

- **Week 2 — IAM Done Right** extends this exact Organization with `identity`/`dev`/`prod` accounts, permission boundaries, and AssumeRole chains. Your Identity Center setup and `mgmt-admin` profile are the starting point.
- **Week 3 — CDK & CloudFormation** uses this account as the `cdk bootstrap` target. The `budgets/` CDK app you wrote here is your first real stack.
- **Every lab, weeks 4–14** deploys into the `dev` OU/account, inherits the SCP guardrail, trips (or doesn't) the Budgets you set, and shows up in the CUR you can now query. The cost report each week is run against *this* pipeline.
- **The capstone** is graded in part on a real dollar number with a tagged breakdown — produced by the CUR → Athena pipeline you just built. Week 14 dresses it up in QuickSight; the plumbing is yours from Week 1.

---

## Submission

1. Push `c19-week-01-foundation-<yourhandle>` to GitHub, public.
2. Confirm `verify.sh` runs clean against a freshly-`aws sso login`'d shell.
3. Make sure `billing/REPORT.md` has real numbers and `billing/scp-proof.txt` has the explicit-deny line.
4. Post the repo URL in your cohort tracker. This scaffold is the ground floor of everything that follows — show that the floor is solid.
