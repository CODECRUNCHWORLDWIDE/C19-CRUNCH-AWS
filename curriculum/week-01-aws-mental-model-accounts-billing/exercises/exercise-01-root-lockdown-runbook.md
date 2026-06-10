# Exercise 1 — The Root-Lockdown Runbook

**Goal:** Create a fresh AWS account, lock down the root user to senior-engineer standard, and write a runbook that documents the break-glass recovery path. By the end, root has MFA, zero access keys, correct alternate contacts, and a sealed-credential procedure on paper.

**Estimated time:** 60 minutes.

**Cost:** $0. Account creation, MFA, and alternate contacts are free. AWS requires a payment method on file, but nothing here incurs charges.

---

## Why this is the first thing you ever do

The root user can close the account, change billing, and delete every admin. A leaked root credential is the worst single failure in AWS. So before you build *anything*, you make root safe and document how to recover it in an emergency. This is the literal "seal the credentials in an envelope" step from the syllabus — and yes, we mean it literally.

---

## Step 1 — Create the account

1. Go to <https://aws.amazon.com/> and choose **Create an AWS Account**.
2. Use a **role-based email**, not a personal one. For a team: `aws-management@yourco.com`. For solo learning, a dedicated alias like `you+aws-c19@gmail.com` works (Gmail's `+` aliasing routes to your inbox but is a distinct address).
3. Choose **Personal** (or Business) and complete the contact and payment details. AWS places a small temporary authorization (often ~$1, refunded) to validate the card.
4. Choose the **Basic support plan** (free).
5. Sign in to the console as **root** using that email and the password you set.

You are now signed in as the most powerful identity this account will ever have. We will neuter it in the next steps and then stop using it.

---

## Step 2 — Set a strong root password

If you have not already, set a long, unique, password-manager-generated password (20+ characters). Store it in your password manager. Never reuse it anywhere.

---

## Step 3 — Enable MFA on root (two devices)

This is the single highest-value control on the account.

1. In the console, top-right, click your account name → **Security credentials**.
2. Under **Multi-factor authentication (MFA)**, choose **Assign MFA device**.
3. Register your **primary** device:
   - **Best:** a FIDO2 hardware security key (YubiKey) or a passkey.
   - **Acceptable:** a virtual TOTP authenticator app (1Password, Authy, Google Authenticator).
4. Register a **second** MFA device. AWS allows multiple MFA devices on root — a backup means losing one device does not lock you out of the account. Register a second hardware key or a second TOTP entry stored in a different place.

Verify in the console that **two** MFA devices are listed.

---

## Step 4 — Confirm root has zero access keys

Root should have **no** programmatic access keys, ever.

1. On the same **Security credentials** page, find the **Access keys** section.
2. If any root access key exists, **delete it.** (A brand-new account usually has none — confirm.)

You can verify from the CLI later (as an admin principal, not root):

```bash
aws iam get-account-summary \
  --query 'SummaryMap.{RootMFA:AccountMFAEnabled, RootAccessKeys:AccountAccessKeysPresent}'
```

Target output:

```json
{
    "RootMFA": 1,
    "RootAccessKeys": 0
}
```

`RootMFA: 1` means MFA is on. `RootAccessKeys: 0` means root has no keys. Both are required.

---

## Step 5 — Set the alternate contacts

Billing alerts and security notices must reach a monitored inbox, not vanish.

1. Console → **Account** (top-right menu) → scroll to **Alternate contacts**.
2. Set the **Billing**, **Operations**, and **Security** contacts. For a team, use distribution lists (`billing@`, `security@`). For solo learning, use an address you actually read.

This matters because your Week-1 Budgets and AWS's own security notifications go here. A cost alert that lands in an abandoned inbox is no alert at all.

---

## Step 6 — Turn on IAM access to billing data

So that non-root admins (you, via SSO) can see Cost Explorer and the CUR:

1. Console → **Account** → **IAM user and role access to Billing Information** → **Activate**.

Without this, only root can see billing, which would force you to use root for cost work — exactly what we are trying to avoid.

---

## Step 7 — Write the runbook (the deliverable)

Create `runbooks/root-credentials.md` in your Week 1 Git repo. It must contain, at minimum, the following sections. **Do not commit actual secrets** — the runbook describes *where* recovery material lives, not the material itself.

```markdown
# Runbook — Root Credential Lockdown & Recovery

## Account
- Account ID: 1111-2222-3333          (your 12-digit id)
- Account name: crunch-aws-mgmt
- Root email: aws-management@example.com
- Created: 2026-06-09
- Purpose: Organization management account. No workloads run here.

## Current posture (verified 2026-06-09)
- [x] Root MFA: 2 devices registered (primary: YubiKey #A; backup: TOTP in 1Password vault "AWS-root")
- [x] Root access keys: 0
- [x] Alternate contacts set (billing/ops/security)
- [x] IAM access to billing activated

## Where recovery material lives (NO secrets in this file)
- Root password: 1Password vault "AWS-root", item "mgmt root login"
- Primary MFA (YubiKey #A): in the office safe, shelf 2
- Backup MFA (TOTP seed): 1Password vault "AWS-root", item "mgmt root TOTP backup"
- Sealed paper copy: envelope in the fire safe; opening it is an audited event (see below)

## Break-glass procedure (when do we use root?)
Root is used ONLY for actions that require it:
- Changing the account email or root password
- Closing the account
- Certain support-plan or billing changes
Daily work uses IAM Identity Center, never root.

## To open the sealed envelope
1. Page the account owner + one other authorized person (two-person rule).
2. Record who, when, and why in the incident log.
3. Reseal and re-store immediately after the action.

## If MFA is lost
- Use the backup MFA device.
- If both are lost: follow AWS's account recovery via the root email + phone
  (alternate contact). Reference: https://repost.aws/knowledge-center/reset-mfa-device
```

### The literal sealing step

Print the recovery summary (the *where* and the break-glass procedure — **not** the password itself unless your org's policy is to seal the password on paper in a safe). Put it in an envelope. Sign across the seal. Store it in a locked drawer or fire safe. Note in the runbook who is authorized to open it and that opening it is a logged event. This sounds theatrical; it is standard practice in regulated shops, and the discipline is the point: root is break-glass, with an audited recovery path, not a Tuesday login.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] You can sign in to the new account as root with MFA prompting you.
- [ ] **Two** MFA devices are registered on root.
- [ ] Root has **zero** access keys (`RootAccessKeys: 0`).
- [ ] Alternate contacts (billing/ops/security) are set.
- [ ] IAM access to billing is activated.
- [ ] `runbooks/root-credentials.md` exists, committed, with all sections above and **no real secrets** in it.
- [ ] You have physically sealed the recovery summary and noted where it lives.
- [ ] You can describe, in one sentence, the difference between the root user and an IAM Identity Center login.

---

## Stretch

- Set up **IAM Identity Center** now (mini-project Phase 1 walks you through it) and assign yourself an `AdministratorAccess` permission set. Then `aws sso login` and confirm `aws sts get-caller-identity` shows an assumed-role ARN, not the root ARN. From here on, never sign in as root again this week.
- Enable a **CloudWatch billing alarm** as a belt-and-suspenders alongside the Budgets you build in Exercise 3.
- Turn on **CloudTrail** in this account (a single-Region trail is free for management events) so every API call from minute one is audited.

---

## Hints

<details>
<summary>I can't find "Security credentials" for root</summary>

You must be signed in *as root* (with the account email), not as an IAM user. The menu is under your account name in the top-right. If you only see limited options, you are signed in as an IAM principal — sign out and sign in with the root email.

</details>

<details>
<summary>AWS won't let me register a second MFA device</summary>

Multiple MFA devices on root is a relatively recent capability. Make sure your console is current (it always is — it's a web app) and that you completed registration of the first device fully before adding the second. Each device needs a unique name.

</details>

<details>
<summary>Should the actual root password go in the sealed envelope?</summary>

Follow your org's policy. Common practice: the password lives in a password manager (encrypted, access-controlled), and the *sealed paper* holds the break-glass procedure plus the location of the backup MFA — enough to recover, but not a single sheet that hands an attacker everything. For solo learning, sealing a printed password in a genuine safe is acceptable; sealing it in a desk drawer is not.

</details>

---

When root is locked and the runbook is committed, move to [Exercise 2 — Organization + SCP](exercise-02-org-with-scp-deny-region.tf).
