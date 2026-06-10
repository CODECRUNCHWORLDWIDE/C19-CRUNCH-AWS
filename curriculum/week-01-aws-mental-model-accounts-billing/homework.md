# Week 1 Homework

Six practice problems that reinforce the week's topics: the mental model, the account boundary, SCPs, billing observability, and CLI fluency. The full set should take about **5 hours**. Work in your Week 1 Git repository so each problem produces at least one commit you can point to later.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

A reminder before you start: **`aws sts get-caller-identity` before every account-touching command.** If you cannot say which account and principal you are, stop.

---

## Problem 1 — Place 12 services in their families

**Problem statement.** Create `notes/service-families.md`. For each of the twelve services below, state (a) which of the seven families it belongs to — Compute, Storage, Database, Networking & Content Delivery, Security & Identity, Integration & Messaging, or Management & Observability — and (b) one sentence on its blast radius: if it is misconfigured, what is the worst that happens, and is it Regional or global?

```
Lambda, S3, DynamoDB, CloudFront, IAM, SQS, EventBridge,
CloudWatch, VPC, KMS, Route 53, Aurora
```

Then add a one-paragraph answer: *which two of these are global (not Regional), and why does that matter for an SCP that denies a Region?*

**Acceptance criteria.**

- `notes/service-families.md` exists with a row per service: family, blast-radius sentence, Regional/global.
- The closing paragraph correctly identifies IAM and Route 53 (and CloudFront's edge layer) as global, and explains why a `aws:RequestedRegion` SCP cannot meaningfully restrict them.
- Committed.

**Hint.** Global services don't take a Region in their core API calls (IAM, Route 53, CloudFront, Organizations, WAF-classic global). That's exactly why a Region-deny SCP needs a carve-out for them — otherwise you break your own control plane. Aurora is a Database; VPC is Networking; KMS is Security & Identity; EventBridge and SQS are Integration & Messaging; CloudWatch is Management & Observability.

**Estimated time.** 30 minutes.

---

## Problem 2 — Choose a Region with reasons

**Problem statement.** In `notes/region-choice.md`, pick the Region you will use for the bulk of this course's *Regional* workloads (the lecture and course default is `eu-west-1`, but justify your own choice). Defend it on four axes, one short paragraph each:

1. **Latency** — where are you, and what is the round-trip you'd expect? (Use the AWS latency-test page or `cloudping`.)
2. **Cost** — is this Region in the cheaper or more expensive tier? (Compare its EC2/S3 price tier to `us-east-1`.)
3. **Service availability** — name one service that is *not* yet in your chosen Region but *is* in `us-east-1`. (Check the Region table.)
4. **Data residency / sovereignty** — does your (hypothetical) user data have a jurisdiction requirement that this Region satisfies?

Close with one sentence on why you would still keep your **billing/CUR/Budgets and Organizations** anchored to `us-east-1`-adjacent global endpoints regardless of your workload Region.

**Acceptance criteria.**

- `notes/region-choice.md` exists with the four labelled paragraphs and the closing sentence.
- The service-availability paragraph names a real, currently-lagging service (verified against the Region table, not guessed).
- Committed.

**Hint.** The AWS Region table (<https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/>) shows service-by-Region availability. Newer AI/ML and some analytics services land in `us-east-1` and a couple of others first. Global services (IAM, Organizations, Budgets, CUR/Data Exports control plane) are anchored regardless of your workload Region — that's why your management-account billing config lives where it lives.

**Estimated time.** 45 minutes.

---

## Problem 3 — Read an SCP out loud, then break it

**Problem statement.** You are handed the SCP below. In `notes/scp-readthrough.md`, (a) explain in plain English exactly what it allows and denies, (b) identify the **bug** that makes it more dangerous than intended, and (c) write a corrected version.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RegionLock",
      "Effect": "Deny",
      "NotAction": [ "iam:*", "organizations:*", "route53:*" ],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestedRegion": [ "eu-west-1", "us-east-1" ]
        }
      }
    }
  ]
}
```

**Acceptance criteria.**

- `notes/scp-readthrough.md` correctly states that this denies all non-IAM/Organizations/Route 53 actions outside `eu-west-1` and `us-east-1`.
- You identify the real subtlety: this is a **region allow-list expressed as a deny** (the safer, intended shape) — and you spot that `us-east-1` is in the allow-list, so it does **not** block `us-east-1` (which is often *not* what a team that wrote "RegionLock" intended if they meant to force everything into `eu-west-1`). You also note that SCPs grant nothing — this must sit over IAM allows.
- Your corrected version either (i) removes `us-east-1` from the allow-list if the intent was eu-only, *or* (ii) keeps it but documents why (global service control planes transit `us-east-1`), and you explain the trade-off.
- Committed.

**Hint.** An SCP is a *guardrail*, never a grant. The `Deny` + `StringNotEquals` + `NotAction` combination is the canonical "lock to these Regions but never touch my global control planes" pattern. The trap is forgetting that `us-east-1` in the allow-list keeps `us-east-1` fully open — which you want for global services but maybe not for everything. There is no single right answer; there is a defensible answer with a documented reason.

**Estimated time.** 45 minutes.

---

## Problem 4 — Apply the shared responsibility model to four services

**Problem statement.** Create `notes/shared-responsibility.md`. For each of **S3**, **EC2**, **RDS**, and **Lambda**, fill a two-column table: *AWS is responsible for* vs *You are responsible for*. Be concrete — name the actual things (patching the guest OS, encrypting objects, rotating database credentials, the VPC the function runs in, the IAM execution role, the physical disk, the hypervisor).

Then answer, in one paragraph: *as you move from EC2 → RDS → Lambda, which way does the responsibility line slide, and what does that buy you and cost you?*

**Acceptance criteria.**

- `notes/shared-responsibility.md` has four correctly-filled tables.
- For EC2 you correctly put **guest OS patching, instance firewall (SG) rules, and application code** on the *you* side; physical security, hypervisor, and network infrastructure on the *AWS* side.
- For Lambda you correctly note AWS owns the OS/runtime patching and scaling; you still own the code, the IAM role, the env-var secrets, and the data.
- The closing paragraph correctly observes the line slides *toward AWS* (less ops, less control) as you go serverless.
- Committed.

**Hint.** The canonical phrasing is "security **of** the cloud" (AWS: hardware, hypervisor, managed-service internals) vs "security **in** the cloud" (you: data, IAM, OS for IaaS, network config, app code). The shift from IaaS → managed → serverless moves the OS/runtime/scaling burden to AWS but never moves *your data*, *your IAM*, or *your application logic* — those are always yours.

**Estimated time.** 45 minutes.

---

## Problem 5 — CLI fluency: three profiles, one chain

**Problem statement.** Without checking in any secrets, configure and demonstrate three named profiles in `~/.aws/config`, then document the result in `notes/cli-profiles.md` (paste your **redacted** config — strip account ids and start URLs):

1. `mgmt-admin` — an `aws configure sso` profile into your management account with the admin permission set.
2. `dev-admin` — an SSO profile into your `dev` member account (or, if you only have the management account, a *role-chaining* profile that assumes a role: `role_arn` + `source_profile = mgmt-admin`).
3. A **default-region** difference: give `mgmt-admin` `region = us-east-1` (for billing APIs) and `dev-admin` `region = eu-west-1` (for workloads).

Demonstrate, with captured output in the notes file:

- `aws sts get-caller-identity --profile mgmt-admin` (shows the SSO admin role).
- `aws sts get-caller-identity --profile dev-admin` (shows a *different* account id).
- `aws budgets describe-budgets --account-id <id> --profile mgmt-admin` succeeds (Budgets is a `us-east-1` global API).

**Acceptance criteria.**

- `notes/cli-profiles.md` shows a redacted `~/.aws/config` with the three profiles and the explained `region` settings.
- The two `get-caller-identity` outputs show **different account ids** (or, for the chaining variant, the same account but a different assumed role).
- You explain in one sentence why long-lived keys in `~/.aws/credentials` are *not* used here.
- Committed (the notes file only — never commit `~/.aws/`).

**Hint.** SSO profiles live in `~/.aws/config` under `[profile name]` with `sso_session`, `sso_account_id`, `sso_role_name`. Role-chaining profiles use `role_arn` + `source_profile` + `mfa_serial`. `aws sso login` populates a short-lived token cache under `~/.aws/sso/cache/` — those expire, which is the whole point. Never paste `AKIA...` keys into a terminal in this course.

**Estimated time.** 1 hour.

---

## Problem 6 — Mini reflection essay

**Problem statement.** Write a 300–400 word reflection at `notes/week-01-reflection.md` answering:

1. Before this week, what was your mental model of "AWS"? How did the seven-families framing change (or not change) it?
2. The course insists you make the bill and the account boundary observable *before* any compute. Did that ordering feel right, or backwards? Why?
3. You proved an SCP deny by watching a command fail with `explicit deny in a service control policy`. Why does the course care so much about *proving* a control rather than just configuring it?
4. What is one thing about Organizations, SCPs, or billing you still find murky and want Week 2 (or later) to clear up?

**Acceptance criteria.**

- File exists, 300–400 words.
- Each numbered question is addressed in its own paragraph.
- Committed.

**Hint.** This is for *you*, not for a grade. Be honest about what was confusing — the account boundary vs IAM vs SCP distinction trips up almost everyone the first time. Future-you, reading this after the Week 13 security stack, will be glad you wrote down where you started.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 30 min |
| 2 | 45 min |
| 3 | 45 min |
| 4 | 45 min |
| 5 | 1 h 0 min |
| 6 | 30 min |
| **Total** | **~3 h 45 min** |

(The remaining ~1h 15m of the homework block goes to the engineering-journal entry and the cost-report check the README asks for at the end of the week.)

---

## Rubric

| Criterion | Weight | What "great" looks like |
|----------|-------:|-------------------------|
| Mental-model accuracy (P1, P4) | 25% | Services placed in the right families; global vs Regional correct; responsibility lines drawn correctly |
| Region reasoning (P2) | 15% | Four axes argued with real, verified facts — not vibes |
| SCP literacy (P3) | 25% | Reads the policy correctly, spots the allow-list-as-deny shape, corrects it with a documented reason |
| CLI fluency (P5) | 25% | Three working profiles, different identities proven, no secrets committed, SSO not keys |
| Reflection (P6) | 10% | Honest, specific, names a real point of confusion to carry into Week 2 |

---

When you've finished all six, push your repo and make sure your [mini-project](./mini-project/README.md) `verify.sh` still runs green. Week 2 — IAM Done Right — assumes everything you built and reasoned about this week.
