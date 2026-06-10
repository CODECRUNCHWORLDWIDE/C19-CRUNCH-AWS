# Lecture 2 — Account-Level Posture: Organizations, OUs, SCPs, and Root-User Hygiene

> **Duration:** ~1.5 hours of reading + hands-on.
> **Outcome:** You can explain the account as the security and billing boundary, stand up an Organization with OUs, attach an SCP as a guardrail (and explain why an SCP grants nothing), lock down a root user to senior-engineer standard, and configure the CLI to authenticate via IAM Identity Center with `aws sso login`.

If you only remember one thing from this lecture, remember this:

> **The AWS account is the only hard boundary you get for free.** Everything inside one account is one IAM blast radius and one bill. The way you contain risk and observe cost at scale is by having *more than one account*, organized in a tree, with guardrails on the branches. SCPs do not grant permissions — they cap them. And the root user is a credential you lock in a drawer and almost never touch.

---

## 1. The account is the boundary

In Lecture 1 we said the account is the hard boundary for **security** and **billing**. Let's make that concrete, because the whole multi-account design follows from it.

- **Security blast radius.** Every IAM principal, every resource, every policy lives inside one account. A misconfigured IAM policy in account A cannot, by itself, touch a resource in account B — crossing the boundary requires an explicit cross-account trust relationship that *both* sides agree to. So if you put production in its own account and a developer fat-fingers a wildcard policy in the dev account, production is structurally untouched. The boundary did its job.

- **Billing rollup.** Each account produces its own bill. When accounts belong to an Organization, those bills **consolidate** to the management account, but they remain attributable per-account. This means "what did the dev environment cost last month?" is a question with a clean answer when dev is its own account — and a guessing game when dev, stage, and prod share one account and you're slicing by tags you hope everyone applied.

This is why the industry-standard pattern is **one account per environment per workload**, not one giant account with everything tagged. The number of accounts grows; that is fine, because Organizations exists to manage many accounts centrally. Our mini-project this week is the smallest honest version of this: a management account plus OUs that will hold `dev`, `stage`, and `prod` member accounts.

> **What we actually do this week.** Creating real member accounts requires giving AWS a unique email per account and waiting on account activation. For the lab we build the **org structure** — the management account, the OUs, and the SCPs attached to them — which is the part that teaches the model and that every later week reuses. The mini-project README tells you exactly which parts to make real and which to scaffold.

---

## 2. The vocabulary: Organization, management account, member account, OU

```
AWS Organization
│
├── Management account  (the one that created the org; holds billing; do NOT run workloads here)
│
└── Root  (the top of the OU tree — confusingly named, not the "root user")
    │
    ├── OU: Workloads
    │   ├── OU: dev    ──► member account(s)
    │   ├── OU: stage  ──► member account(s)
    │   └── OU: prod   ──► member account(s)
    │
    └── OU: Sandbox    ──► member account(s)
```

- **Organization** — the top-level container. Created once, from one account, which becomes the management account.
- **Management account** (formerly "master account") — the account that created the Organization. It pays the consolidated bill and is the only place you manage the org tree and SCPs. **You do not run workloads in it.** It is high-value and high-blast-radius; keep it nearly empty. This is non-negotiable senior practice.
- **Member account** — every other account in the org. This is where workloads live.
- **Root** (of the OU tree) — the top node of the tree. Confusing name: this is *not* the root *user*. It is the parent OU that every other OU and account descends from. SCPs attached here apply org-wide.
- **OU (Organizational Unit)** — a folder in the tree. You attach policies to OUs and member accounts inherit them. You can nest OUs. Our lab uses three: `dev`, `stage`, `prod`.

The condition key `aws:PrincipalOrgID` is the payoff of having an Organization: it lets you write a resource policy that says "trust any principal in *my* org" without listing every account ID. You'll lean on it constantly from Week 2 on.

---

## 3. Service Control Policies — guardrails, not grants

This is the concept engineers get wrong most often, so read it twice.

> **An SCP never grants a permission. It only sets the *maximum* permissions available to the accounts it applies to.** The effective permission of any principal is the **intersection** of (a) what its IAM policies allow and (b) what the SCPs above it permit. An SCP cannot give a developer `s3:PutObject`; only an IAM policy can do that. An SCP can only *take it away*, no matter what the IAM policy says.

Two mental models that make this click:

1. **SCP = the ceiling. IAM = the floor you build up to.** You can never get above the ceiling. If the SCP denies `ec2:*`, then even an `AdministratorAccess` IAM policy in that account cannot launch an instance. Explicit deny always wins (you'll formalize the full evaluation logic in Week 2).

2. **The default SCP is `FullAWSAccess` — a ceiling at the roof.** When you enable SCPs, AWS attaches a managed policy called `FullAWSAccess` that allows everything. So by default the ceiling is "anything," and IAM is the only thing limiting you. You lower the ceiling by attaching a *deny* SCP (or by replacing `FullAWSAccess` with a narrower allow-list — the deny approach is simpler and the one we use).

### The two SCP styles

- **Deny list** (what we use): keep `FullAWSAccess` attached, and add SCPs that `Deny` specific dangerous actions. "Allow everything except these." Easy to reason about, hard to lock yourself out.
- **Allow list**: detach `FullAWSAccess` and explicitly `Allow` only the services you sanction. "Deny everything except these." Tighter, but brittle — every new service you adopt needs an SCP edit, and it is very easy to break the org. Most shops use deny lists for guardrails and reserve allow lists for highly regulated OUs.

### The classic guardrail: deny a Region

Our lab's SCP denies all actions in `us-east-1` for one OU. The policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUsEast1",
      "Effect": "Deny",
      "Action": "*",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    }
  ]
}
```

Read it out loud: "Deny any action on any resource when the requested Region is `us-east-1`." Attach it to the `dev` OU, and every account under `dev` loses the ability to act in `us-east-1` — regardless of how permissive its IAM is.

**But there's a trap, and it's the lesson.** Several *global* services route their control plane through `us-east-1`: CloudFront, some IAM and Organizations operations, Route 53 in places, and ACM certificates destined for CloudFront. A blanket `aws:RequestedRegion == us-east-1` deny can therefore break legitimate global operations. The production-grade version carves those out with a `Condition` that excludes global service actions, e.g.:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUsEast1ExceptGlobal",
      "Effect": "Deny",
      "NotAction": [
        "cloudfront:*",
        "iam:*",
        "route53:*",
        "organizations:*",
        "support:*",
        "waf:*"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    }
  ]
}
```

`NotAction` means "this Deny applies to every action *except* these." So global operations that must run in `us-east-1` still work, while a developer trying to spin up EC2 or an S3 bucket in `us-east-1` is blocked. We start with the naive version in the exercise so you *see* the breakage, then refine to this one.

### Prove the deny — the non-negotiable step

A guardrail you have not tested is not a guardrail. After attaching the SCP, assume into an account under the constrained OU and attempt a blocked action:

```bash
# From a principal in a dev-OU account, try to act in the denied Region:
aws ec2 describe-instances --region us-east-1
```

You want to see, in the error, the phrase that proves the SCP fired:

```
An error occurred (UnauthorizedOperation) when calling the DescribeInstances
operation: You are not authorized to perform this operation ...
with an explicit deny in a service control policy
```

The exact error class varies by API (`AccessDenied`, `UnauthorizedOperation`), but **`explicit deny in a service control policy`** is the string that means "the SCP did its job." If you only ever read AWS's marketing about SCPs and never saw that line, you do not actually know your guardrail works. Make it fail on purpose.

---

## 4. Root-user hygiene — lock the drawer

Every AWS account has a **root user**: the identity tied to the email address used to create the account. It can do *anything* — close the account, change billing, remove other admins — and a handful of actions can *only* be done by root (e.g. changing the account's email, some support-plan changes, deleting the account). Because of that power, the rule is simple:

> **Use the root user to do the initial setup, then lock it away and never use it for daily work. Daily work happens through IAM Identity Center, not root.**

The senior-engineer lockdown checklist (this is Exercise 1, end to end):

1. **Set a long, unique, password-manager-generated password.** Never reuse it.
2. **Enable MFA on root.** Prefer a hardware key (FIDO2/YubiKey) or a virtual TOTP authenticator. As of recent AWS changes you can register **multiple** MFA devices on root — register two so losing one device does not lock you out. Do this first; it is the single highest-value control on the account.
3. **Delete any root access keys.** Root should have **zero** programmatic access keys. If `aws iam get-account-summary` shows `AccountAccessKeysPresent: 1` for root, delete them. Long-lived root keys are the worst credential in all of AWS.
4. **Set the alternate contacts**, especially the **billing** contact, so cost alerts and account-security notices reach a monitored inbox/distribution list, not one person's personal email.
5. **Do not create IAM users for humans.** Humans get access through **IAM Identity Center** (SSO) with short-lived credentials. IAM users with long-lived keys are a legacy pattern; we avoid them. (Service principals use roles, not users — Week 2.)
6. **Write the runbook and seal the credentials.** Document, in a runbook, exactly how to recover root access in an emergency: where the password lives, where the MFA backup device is, who the alternate contacts are. The literal "sealed envelope" is a real practice — print the recovery info, seal it, store it in a safe, and log who can open it. The point is that root is a *break-glass* credential with an audited recovery path, not a login you use on Tuesdays.

Verify the posture from the CLI (run as an admin principal, not root):

```bash
# Root should have MFA enabled and zero access keys.
aws iam get-account-summary \
  --query 'SummaryMap.{RootMFA:AccountMFAEnabled, RootAccessKeys:AccountAccessKeysPresent}'
```

You want `RootMFA: 1` and `RootAccessKeys: 0`. Anything else is a finding.

---

## 5. How humans actually log in: IAM Identity Center + `aws sso login`

You will not paste a long-lived access key into your shell in this course. That pattern leaks keys into shell history, dotfiles, and CI logs, and it is how breaches happen. Instead, humans authenticate through **IAM Identity Center** and the CLI exchanges that session for **short-lived** credentials automatically.

The flow, once your org admin has set up Identity Center and assigned you a permission set:

```bash
# One-time: configure a profile interactively against your SSO start URL.
aws configure sso
# It prompts for:
#   SSO start URL:      https://d-xxxxxxxxxx.awsapps.com/start
#   SSO region:         eu-west-1
#   ...then lets you pick an account + role, and names the profile.
```

This writes a profile to `~/.aws/config` (note: SSO config goes in `config`, not `credentials`). It looks like:

```ini
[profile dev-admin]
sso_session = crunch-sso
sso_account_id = 222233334444
sso_role_name = AdministratorAccess
region = eu-west-1
output = json

[sso-session crunch-sso]
sso_start_url = https://d-xxxxxxxxxx.awsapps.com/start
sso_region = eu-west-1
sso_registration_scopes = sso:account:access
```

Then, daily:

```bash
# Opens a browser, you approve, and the CLI caches a short-lived session.
aws sso login --profile dev-admin

# Use the profile per-command...
aws s3 ls --profile dev-admin

# ...or set it for the shell session:
export AWS_PROFILE=dev-admin
aws sts get-caller-identity
```

`aws sts get-caller-identity` is the "who am I right now?" command — run it constantly to confirm which account and role you are operating as before you do anything destructive. The credentials it returns are temporary (typically an assumed-role session) and expire; you re-run `aws sso login` when they do. **No long-lived secret ever lands on disk.**

> **`~/.aws/config` vs `~/.aws/credentials`.** The `credentials` file holds long-lived `aws_access_key_id` / `aws_secret_access_key` pairs — the old way, and the thing we are avoiding. The `config` file holds profiles, Regions, output formats, and SSO sessions. In a modern setup `credentials` is often empty or absent entirely, and that is good.

### CloudShell — the zero-install escape hatch

When your laptop CLI is misconfigured, open **CloudShell** from the AWS console. It is a browser-based shell already authenticated as your console identity, with the CLI, `git`, `python`, and `jq` preinstalled. Useful for "I just need to run one command as this role right now" and for following along before your local CLI is set up.

---

## 6. Putting it together — the day-one sequence

The order matters. This is the literal sequence a senior engineer runs on a brand-new account:

1. **Create the account** with a role-based email (e.g. `aws-management@yourco.com`), not a personal one.
2. **Lock the root user**: MFA (two devices), delete keys, set alternate contacts, write + seal the runbook.
3. **Enable the Organization** from this account (it becomes the management account).
4. **Create the OUs** (`dev`, `stage`, `prod`) and **enable SCPs** (the `FullAWSAccess` default appears).
5. **Attach guardrail SCPs** (deny the Region, etc.) and **prove a deny**.
6. **Set up IAM Identity Center**, create a permission set, assign yourself — so you never use root or IAM users for daily work.
7. **Configure Budgets** (`$5`/`$25`/`$80`) and the **CUR → S3 → Athena** pipeline so cost is observable before any compute exists.
8. **Turn on CloudTrail** org-wide so every API call is audited from the first minute (we wire this up properly in Week 13; turning it on early is cheap insurance).

Steps 1–2 are Exercise 1. Steps 3–5 are Exercise 2. Step 7 is Exercise 3 and the Challenge. The whole sequence is the mini-project. By Friday you will have run all of it.

---

## 7. Hands-on — inspect the org from the CLI

Once your Organization exists (Exercise 2), interrogate it:

```bash
# Describe the org and find the management account + root id.
aws organizations describe-organization \
  --query 'Organization.{Id:Id, MgmtAccount:MasterAccountId, FeatureSet:FeatureSet}'

# List the OUs under the org root (first get the root id).
ROOT_ID=$(aws organizations list-roots --query 'Roots[0].Id' --output text)
aws organizations list-organizational-units-for-parent \
  --parent-id "$ROOT_ID" \
  --query 'OrganizationalUnits[].{Name:Name, Id:Id}' \
  --output table

# List the SCPs attached to the dev OU (substitute its id).
aws organizations list-policies-for-target \
  --target-id ou-xxxx-xxxxxxxx \
  --filter SERVICE_CONTROL_POLICY \
  --query 'Policies[].{Name:Name, Id:Id}' \
  --output table
```

`FeatureSet` should read `ALL` — that is what enables SCPs. If it says `CONSOLIDATED_BILLING`, you only have the billing half of Organizations and SCPs are not available; you'd enable all features.

---

## 8. Why this is Week 1 and not Week 13

A reasonable person asks: "isn't governance an advanced topic? Why not learn it after I can deploy something?" The answer is the C19 thesis: **the account boundary and the bill are the two things that are most expensive to retrofit and cheapest to get right on day one.**

- Retrofitting multi-account isolation onto a single account that already holds dev, stage, and prod is a migration project measured in weeks.
- Discovering you have no cost observability *after* a runaway resource has cost you $4,000 is a worse day than spending 30 minutes on Budgets now.
- Discovering your root user had an access key *after* it leaked is a breach.

So we front-load it. Every later week deploys *into* this scaffold and ends with a cost report this scaffold makes possible. You are not learning governance for its own sake; you are building the surface you will stand on for fourteen more weeks.

---

## 9. What this lecture deliberately skips

- **IAM policy authoring in depth** — Week 2. Here you only read an SCP and a deny.
- **IAM Identity Center setup in depth** — we show the *consumer* side (`aws sso login`); the full Identity Center build (permission sets, attribute-based access) is Week 2.
- **CloudTrail, Config, GuardDuty** — security tooling is Week 13. We turn CloudTrail on early but do not analyze it yet.
- **Cross-account roles and `sts:AssumeRole` chains** — Week 2.

---

## 10. Recap

You should now be able to:

- Explain the account as the hard security and billing boundary, and why "one account per environment" is the baseline.
- Name the parts of an Organization: management account, member account, OU, the tree root, and `aws:PrincipalOrgID`.
- State the central SCP truth — **SCPs cap, they never grant** — and write a deny-Region SCP with a global-service carve-out.
- Prove a deny by reading `explicit deny in a service control policy` in an error.
- Lock a root user to senior standard: MFA (×2), no access keys, alternate contacts, sealed runbook.
- Authenticate the CLI with `aws configure sso` / `aws sso login` and confirm identity with `aws sts get-caller-identity` — no long-lived keys on disk.

Next: the exercises. Start with [Exercise 1 — the root-lockdown runbook](../exercises/exercise-01-root-lockdown-runbook.md).

---

## References

- *AWS Organizations concepts*: <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_getting-started_concepts.html>
- *Service Control Policies*: <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html>
- *SCP evaluation & examples*: <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_examples.html>
- *Root user best practices*: <https://docs.aws.amazon.com/IAM/latest/UserGuide/root-user-best-practices.html>
- *Configure the CLI for IAM Identity Center*: <https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html>
- *`aws:RequestedRegion` condition key*: <https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html>
