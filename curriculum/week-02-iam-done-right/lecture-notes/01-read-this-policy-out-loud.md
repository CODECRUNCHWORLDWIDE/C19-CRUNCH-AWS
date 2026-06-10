# Lecture 1 — Read This Policy Out Loud. Now Break It.

> **Reading time:** ~90 minutes. **Hands-on time:** ~60 minutes (you run the evaluation flow against real requests with `aws iam simulate-principal-policy`).

This is the lecture that turns you into the person on the team who catches the IAM bug in review. We do it the only way that works: we learn the evaluation engine's rules cold, then we read twelve real-world policies out loud — the way you would read them to a colleague across a desk — and in each one we find the bug, name it, and explain *why the engine makes that bug dangerous*. Memorizing rules is not enough; the skill is application. By the end you will hear yourself doing it automatically: "Statement one allows `s3:GetObject` on the whole bucket with no condition — that is the bug, because the bucket holds another tenant's data and there is nothing scoping this principal to its own prefix."

The policies in this lecture are composites of real bugs I have seen ship, lightly anonymized. None of them is a strawman. Every one of them passed a `cdk deploy` or a `tofu apply` and sat in a production account until something — an audit, an Access Analyzer finding, or an incident — surfaced it. That is the point. IAM bugs do not announce themselves. The policy is syntactically valid, the deploy succeeds, the application works, and the hole sits open for months. The only defense is a human who reads the policy out loud and asks "wait — what does this actually allow?"

## 1.1 — The evaluation engine, in one diagram you must memorize

Every authorization decision on AWS runs through the same flow. A principal (a user, a role session, a federated identity) makes a request (an action like `s3:GetObject` against a resource like `arn:aws:s3:::app-data/tenant-7/report.pdf`). AWS gathers **every** policy that could apply and runs them through this decision flow:

1. **Is there an explicit `Deny` in any applicable policy?** If yes, the request is denied. Full stop. No `Allow` anywhere can override it. This is the single most important rule in IAM: **explicit deny always wins.** Applicable policies here means: SCPs from the Organization, the principal's identity-based policies, the resource's resource-based policy, the permission boundary, and any session policy. A `Deny` in any of them ends the decision.

2. **Do the Organization SCPs allow the action?** SCPs are a *filter*, not a grant. If an SCP does not allow the action (every SCP is an allow-list that defaults to denying what it does not mention, modulo the `FullAWSAccess` default), the request is denied even if an identity policy allows it. SCPs cap the account; they never grant.

3. **Is there an `Allow`?** Now the engine looks for a grant. Within a single account, an `Allow` from **either** the identity-based policy **or** the resource-based policy is sufficient. Across accounts, you need an `Allow` on **both** sides — the identity policy in the calling account *and* the resource policy in the resource's account must both allow it. (Role trust policies are the resource policy of the role for `sts:AssumeRole`, which is why cross-account assume-role needs both an `Allow` to call `sts:AssumeRole` on the caller and a trust-policy `Allow` on the target.)

4. **Does the permission boundary allow it?** If the principal has a permission boundary attached, the effective permissions are the *intersection* of the boundary and the identity policy. The boundary never grants; it only caps. An action allowed by the identity policy but not by the boundary is denied.

5. **Does the session policy allow it?** If the credentials were obtained via `AssumeRole` with an inline session policy, the effective permissions are further intersected with that session policy. Same rule: it caps, never grants.

If the request survives all five — no explicit deny, allowed by SCPs, allowed by an identity-or-resource policy (both, cross-account), allowed by the boundary, allowed by the session policy — it is permitted. Otherwise it is denied. **The default is deny.** Absence of any matching `Allow` is a deny.

Say it as a sentence you can recite: *"Explicit deny wins. Then SCPs cap. Then I need an allow — one side within an account, both sides across accounts. Then the boundary caps. Then the session policy caps. Default is deny."* Write it on a sticky note. You will use it every day.

### The structure of a statement

A policy is a `Version` and a list of `Statement`s. Each statement has:

```json
{
  "Sid": "AllowReadOwnTenantObjects",
  "Effect": "Allow",
  "Action": ["s3:GetObject"],
  "Resource": "arn:aws:s3:::app-data/${aws:PrincipalTag/tenant}/*",
  "Condition": {
    "StringEquals": { "aws:PrincipalOrgID": "o-abc123def4" }
  }
}
```

- **`Sid`** — a human label. Optional, but always set it; it shows up in `simulate-principal-policy` output and makes review possible.
- **`Effect`** — `Allow` or `Deny`. Nothing else.
- **`Action`** — the API actions (`service:Operation`). `NotAction` is the inverse and a trap (more below).
- **`Resource`** — the ARNs the statement applies to. `NotResource` is the inverse and a trap.
- **`Principal`** — *only on resource-based policies* (and trust policies). Who the statement is about. `NotPrincipal` is the inverse and a near-always-wrong trap.
- **`Condition`** — context keys that must be satisfied for the statement to apply. This is where least privilege lives.

### The three traps: `NotAction`, `NotResource`, `NotPrincipal`

These exist, they are valid, and they are wrong in roughly 90% of the policies that use them. The reason is that humans read `NotAction` as "deny these" but it means "this statement applies to *everything except* these." Combine `"Effect": "Allow"` with `"NotAction": ["iam:*"]` and you have written "allow every action in AWS except IAM" — which is `AdministratorAccess`-minus-IAM, almost certainly not what you meant. When you see `NotAction`/`NotResource`/`NotPrincipal` in a policy under review, your default assumption should be "this is a bug until proven otherwise," and you make the author prove it.

## 1.2 — How to read a policy out loud (the method)

For every statement, in order, say four things:

1. **Effect:** allow or deny.
2. **What:** the actions, in plain English (not the API names — "read objects," not "`s3:GetObject`").
3. **Where:** the resources, scoped or wildcard. If wildcard, say "on *everything*" and pause.
4. **When:** the conditions. If none, say "with *no* condition" and pause.

The pauses are deliberate. "On everything" and "with no condition" are the two phrases that should make you stop and ask whether that is intended. A wildcard resource with no condition is the default shape of an IAM bug.

Then ask the killer questions:

- **Can this `Resource` be narrower?** Almost always yes.
- **Is there a missing condition?** Should this be scoped to the Organization (`aws:PrincipalOrgID`), to a source (`aws:SourceArn`/`aws:SourceAccount`), to TLS (`aws:SecureTransport`), to MFA (`aws:MultiFactorAuthPresent`)?
- **Does this grant a privilege-escalation primitive?** `iam:*`, `iam:PassRole`, `iam:CreatePolicyVersion`, `iam:AttachRolePolicy`, `sts:AssumeRole` on a broad target, `lambda:UpdateFunctionCode` on a privileged function, `kms:*` on a shared key — these let the principal acquire *more* than the policy literally lists.
- **Is this a resource policy with a `Principal` wildcard?** If so, what condition closes it?

Now we apply the method to twelve policies.

## 1.3 — The twelve policies

For each: the policy, then the read-out-loud, then the bug, then the fix, then the evaluation-logic lesson.

### Policy 1 — The "it worked so I shipped it" S3 reader

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadAppData",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "*"
    }
  ]
}
```

**Out loud:** "Allow reading any object in *any bucket in the account*, with *no* condition."

**The bug:** `"Resource": "*"` on `s3:GetObject`. The author wanted to read objects in one bucket (`app-data`) and used `*` because typing the ARN was annoying. This principal can now read every object in every bucket the account owns — the Terraform state bucket, the CloudTrail log bucket, the backups bucket, all of it.

**The fix:** scope to the bucket and, if multi-tenant, to the prefix.

```json
{
  "Sid": "ReadAppData",
  "Effect": "Allow",
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::app-data/*"
}
```

**The lesson:** `s3:GetObject` acts on *objects*, whose ARN is `arn:aws:s3:::bucket/key`. `s3:ListBucket` acts on the *bucket* (`arn:aws:s3:::bucket`). Mixing them up is the #2 S3 IAM bug; the #1 is this — a bare `*`. The evaluation engine has no idea you "meant" one bucket. It grants exactly what you wrote.

### Policy 2 — The `iam:PassRole` time bomb

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DeployLambda",
      "Effect": "Allow",
      "Action": ["lambda:CreateFunction", "lambda:UpdateFunctionCode", "iam:PassRole"],
      "Resource": "*"
    }
  ]
}
```

**Out loud:** "Allow creating and updating Lambda functions on everything, and *passing any role to any service* on everything, with no condition."

**The bug:** `iam:PassRole` on `Resource: "*"`. `PassRole` is the permission to hand a role to a service so the service can assume it. With `lambda:CreateFunction` plus `iam:PassRole` on `*`, this principal can create a Lambda function with the `AdministratorAccess`-bearing `OrganizationAccountAccessRole` as its execution role, then invoke it. They have escalated to admin. `iam:PassRole` on `*` is one of the most dangerous grants in AWS and it appears in thousands of real policies.

**The fix:** scope `PassRole` to exactly the execution role(s) Lambda is allowed to assume, and add the `iam:PassedToService` condition so the role can only be passed *to Lambda*.

```json
{
  "Sid": "DeployLambda",
  "Effect": "Allow",
  "Action": ["lambda:CreateFunction", "lambda:UpdateFunctionCode"],
  "Resource": "arn:aws:lambda:*:111122223333:function:app-*"
},
{
  "Sid": "PassExecutionRoleToLambdaOnly",
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": "arn:aws:iam::111122223333:role/app-lambda-exec-*",
  "Condition": {
    "StringEquals": { "iam:PassedToService": "lambda.amazonaws.com" }
  }
}
```

**The lesson:** `PassRole` is a privilege-escalation primitive. Always scope its `Resource` to specific roles and always pin `iam:PassedToService`. The action that grants a role is at least as dangerous as the role.

### Policy 3 — The `NotAction` admin

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DevsCanDoStuff",
      "Effect": "Allow",
      "NotAction": ["iam:*", "organizations:*", "account:*"],
      "Resource": "*"
    }
  ]
}
```

**Out loud:** "Allow *every action in AWS except* IAM, Organizations, and Account actions, on *everything*, with no condition."

**The bug:** the author thought they were *denying* IAM/Org/Account and allowing nothing else. They wrote the opposite. `Allow` + `NotAction` = "allow everything not in this list." This is `AdministratorAccess` minus three namespaces — the principal can spin up any EC2 instance, read any S3 bucket, delete any database, in any region. And it does not even block escalation: with `ec2:*` they can launch an instance with an admin instance profile (no IAM action needed by them — the instance assumes the role).

**The fix:** never use `NotAction` to express "deny these." Use an explicit allow-list of the services developers actually need, or — if you genuinely want "everything except some dangerous things" — express the dangerous things as an explicit `Deny` statement (which wins) on top of a scoped `Allow`. That is exactly what a permission boundary does (Lecture 2).

**The lesson:** `Allow` + `NotAction` is almost always a bug. The mental model "NotAction means deny" is wrong. `NotAction` only changes *which actions the statement's `Effect` applies to*; the `Effect` is still `Allow`.

### Policy 4 — The resource policy open to the world

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowGets",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::public-reports/*"
    }
  ]
}
```

**Out loud (this is a bucket policy):** "Allow *anyone on the internet* — any AWS principal and any anonymous request — to read any object in `public-reports`, with no condition."

**The bug:** `"Principal": "*"` with no condition makes the bucket world-readable. Sometimes that is intended (a genuinely public static site). Usually it is not — the bucket name says "reports," and "public" was aspirational. This is the literal shape of every "company leaves S3 bucket exposed" headline.

**The fix:** if it must be reachable but only from your Org, condition on `aws:PrincipalOrgID`. If it is genuinely public, keep `Principal: "*"` but add `aws:SecureTransport: true` so it is at least TLS-only, and *write a comment in the IaC saying it is intentionally public* (per the week's wildcard rule).

```json
{
  "Sid": "AllowGetsFromOrgOverTLS",
  "Effect": "Allow",
  "Principal": "*",
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::public-reports/*",
  "Condition": {
    "StringEquals": { "aws:PrincipalOrgID": "o-abc123def4" },
    "Bool": { "aws:SecureTransport": "true" }
  }
}
```

**The lesson:** on a *resource* policy, `Principal: "*"` plus no condition equals "the public internet." Cross-account/anonymous access is governed by the resource policy's `Principal`; the condition keys are what re-narrow it. (Block Public Access at the account level is your backstop, but never rely on the backstop instead of the policy.)

### Policy 5 — The missing confused-deputy guard on a service trust

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustCloudWatchToAssume",
      "Effect": "Allow",
      "Principal": { "Service": "monitoring.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**Out loud (this is a role trust policy):** "Allow the CloudWatch service principal to assume this role, with no condition on *which* CloudWatch resource is doing the assuming."

**The bug:** the **confused deputy.** A service principal like `monitoring.amazonaws.com` is shared across *all* AWS customers. If this role grants powerful permissions and trusts the bare service principal, another customer who can get CloudWatch in *their* account to assume a role can potentially point it at *your* role's ARN (if they learn it). The service is the "deputy"; it can be confused into acting on the wrong customer's behalf.

**The fix:** pin `aws:SourceArn` (the specific resource in *your* account that legitimately triggers the assume) and `aws:SourceAccount`.

```json
{
  "Sid": "TrustCloudWatchToAssume",
  "Effect": "Allow",
  "Principal": { "Service": "monitoring.amazonaws.com" },
  "Action": "sts:AssumeRole",
  "Condition": {
    "StringEquals": { "aws:SourceAccount": "111122223333" },
    "ArnLike": { "aws:SourceArn": "arn:aws:cloudwatch:us-east-1:111122223333:alarm:*" }
  }
}
```

**The lesson:** whenever a *service* assumes a role on your behalf, add `aws:SourceAccount` and `aws:SourceArn`. This is the single most under-applied condition pair in AWS, and it is the difference between "this role works for my account" and "this role works for my account *and only* my account."

### Policy 6 — The third-party role with no external ID

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustVendor",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::999988887777:root" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**Out loud:** "Allow *any principal* in the vendor's account `999988887777` to assume this role, with no external ID."

**The bug:** `"Principal": {"AWS": "...:root"}` trusts the entire other account — every user and role in it — and there is no `sts:ExternalId` condition. The vendor is a SaaS monitoring tool that serves thousands of customers from that one account. Without an external ID, the vendor's software could be tricked (by another of *their* customers) into assuming *your* role. The external ID is the per-customer secret that prevents this; it is the confused-deputy fix for the third-party-SaaS case.

**The fix:** require the external ID the vendor assigned you.

```json
{
  "Sid": "TrustVendor",
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::999988887777:role/vendor-assumer" },
  "Action": "sts:AssumeRole",
  "Condition": {
    "StringEquals": { "sts:ExternalId": "acme-customer-7f3a9c21" }
  }
}
```

Note we also narrowed `Principal` from `:root` to the vendor's specific assumer role — defense in depth.

**The lesson:** third-party cross-account trust *requires* `sts:ExternalId`. If a vendor asks you to set up a role and does not give you an external ID, that is a finding — push back. AWS's own docs say the external ID is mandatory for the third-party pattern.

### Policy 7 — The condition that does nothing

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadSecrets",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:us-east-1:111122223333:secret:prod/*",
      "Condition": {
        "StringEquals": { "aws:username": "deploy-bot" }
      }
    }
  ]
}
```

**Out loud:** "Allow reading prod secrets, but only when `aws:username` equals `deploy-bot`."

**The bug:** `aws:username` is **only populated for IAM *user* principals.** When the caller is a *role session* — which is how `deploy-bot` actually authenticates in 2026 (it is a CI role assumed via OIDC, not an IAM user) — `aws:username` is *absent*, the `StringEquals` does not match, and the statement does not apply. The intent was a guard; the effect is that the policy *never grants* in production (or, if there happens to be a leftover IAM user named `deploy-bot`, it grants to the wrong principal). This is the subtle kind of bug: it can fail *closed* (nobody gets access, you get paged) or fail *open* (a stray user matches).

**The fix:** condition on `aws:PrincipalTag` or the role ARN via `aws:PrincipalArn`, which are populated for role sessions.

```json
"Condition": {
  "ArnEquals": {
    "aws:PrincipalArn": "arn:aws:iam::111122223333:role/ci-deploy"
  }
}
```

**The lesson:** know which condition keys are populated for which principal types. `aws:username` and `aws:userid` behave differently for users vs assumed-role sessions. The Service Authorization Reference and the global-condition-keys page document the availability of each key — check before you rely on one.

### Policy 8 — The KMS key policy that locks you out (or doesn't lock anyone out)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowUseOfKey",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::111122223333:root" },
      "Action": "kms:*",
      "Resource": "*"
    }
  ]
}
```

**Out loud (this is a KMS key policy):** "Allow the entire account `111122223333` to perform *every* KMS action — including scheduling key deletion and changing the key policy — on this key."

**The bug:** `kms:*` to `:root` means *every IAM principal in the account that also has a matching IAM permission* can do *anything* to this key, including `kms:ScheduleKeyDeletion` (which can destroy the ability to decrypt everything the key protects) and `kms:PutKeyPolicy` (which lets them rewrite this very policy). It is over-broad in the dangerous direction. The `:root` here means "delegate authorization to IAM policies in this account," which is fine for *use* but reckless for *administration*.

**The fix:** split key *administration* (a small admin role, with `PutKeyPolicy`, `ScheduleKeyDeletion`, etc.) from key *use* (the application roles, with only `Encrypt`/`Decrypt`/`GenerateDataKey`/`DescribeKey`). The deletion and policy-change actions go to administrators only.

```json
[
  {
    "Sid": "KeyAdmins",
    "Effect": "Allow",
    "Principal": { "AWS": "arn:aws:iam::111122223333:role/kms-admin" },
    "Action": ["kms:Create*","kms:Describe*","kms:Enable*","kms:List*","kms:Put*","kms:Update*","kms:Revoke*","kms:Disable*","kms:Get*","kms:Delete*","kms:ScheduleKeyDeletion","kms:CancelKeyDeletion"],
    "Resource": "*"
  },
  {
    "Sid": "KeyUsers",
    "Effect": "Allow",
    "Principal": { "AWS": "arn:aws:iam::111122223333:role/app-runtime" },
    "Action": ["kms:Encrypt","kms:Decrypt","kms:ReEncrypt*","kms:GenerateDataKey*","kms:DescribeKey"],
    "Resource": "*"
  }
]
```

**The lesson:** `Resource: "*"` is *correct* in a KMS key policy (the policy is already scoped to one key — that is what a key policy is). The bug here is the `Action: "kms:*"` to a broad principal. Separate administration from use; never give the application role the deletion or policy-edit actions.

### Policy 9 — The region condition that locks out global services

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OnlyOurRegion",
      "Effect": "Deny",
      "NotAction": [],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": { "aws:RequestedRegion": "eu-west-1" }
      }
    }
  ]
}
```

**Out loud:** "Deny *all actions* on everything whenever the requested region is not `eu-west-1`."

**The bug:** this looks like a reasonable "stay in our region" guardrail, but it denies *global* services too. IAM, Organizations, CloudFront, Route 53, WAF (global scope), and STS's global endpoint all report a region of `us-east-1` (or `aws-global`) in `aws:RequestedRegion`. This `Deny` will block IAM calls, break CloudFront, and stop `sts:AssumeRole` against the global endpoint — locking the account out of administration. People discover this when they can no longer log in or run `aws iam`.

**The fix:** exempt the global services from the region deny.

```json
{
  "Sid": "OnlyOurRegion",
  "Effect": "Deny",
  "Action": "*",
  "Resource": "*",
  "Condition": {
    "StringNotEquals": {
      "aws:RequestedRegion": ["eu-west-1", "us-east-1"]
    },
    "ForAllValues:StringNotEquals": {
      "aws:CalledVia": ["cloudfront.amazonaws.com"]
    },
    "BoolIfExists": { "aws:ViaAWSService": "false" }
  }
}
```

(The exact exemption list depends on which global services you use; the AWS docs maintain the canonical list of services that must be allowed in `us-east-1`. The point is: a region deny must carve out global services or it bricks the account.)

**The lesson:** `aws:RequestedRegion` is powerful for region-restriction SCPs, but global services do not respect regional boundaries. Every region-deny needs a global-service carve-out. Also note `"NotAction": []` is nonsense — an empty `NotAction` means "every action," which the author stumbled into by accident; use `"Action": "*"` and say what you mean.

### Policy 10 — The wildcard principal "fixed" with a tag that the principal controls

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TagScopedAdmin",
      "Effect": "Allow",
      "Action": "*",
      "Resource": "*",
      "Condition": {
        "StringEquals": { "aws:PrincipalTag/role": "admin" }
      }
    }
  ]
}
```

**Out loud:** "Allow *every action on everything* for any principal tagged `role=admin`."

**The bug:** this is full admin gated on a principal tag — but who can *set* that tag? If developers have `iam:TagRole` or `iam:TagUser` (very common, because tagging feels harmless), they can tag *themselves* (or any role they control) with `role=admin` and instantly become admin. The condition is real but the attribute it keys on is attacker-controllable. ABAC is only safe when the tags are controlled by a separate, trusted authority (Identity Center session tags, or an SCP that denies self-tagging of the privileged tag).

**The fix:** either drop the all-powerful grant entirely (no policy should be `Action: "*"` gated only on a self-settable tag), or use **session tags** set by the identity provider (which the principal cannot change), and add an SCP that denies `iam:TagRole`/`iam:TagUser` on the `role` tag key for everyone except the identity-administration role.

**The lesson:** a condition is only as strong as the trustworthiness of the attribute it reads. `aws:PrincipalTag` is trustworthy only if the principal cannot set its own tags. Always ask "who controls this attribute?" before you trust a tag-based condition.

### Policy 11 — The DenyAll that an Allow quietly defeats (it doesn't — and that's the lesson)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Allow",
      "Effect": "Allow",
      "Action": "s3:*",
      "Resource": "*"
    },
    {
      "Sid": "DenyDeletes",
      "Effect": "Deny",
      "Action": ["s3:DeleteObject", "s3:DeleteBucket"],
      "Resource": "arn:aws:s3:::audit-logs/*"
    }
  ]
}
```

**Out loud:** "Allow every S3 action on every bucket. Then deny deleting objects in the `audit-logs` bucket — but the deny `Resource` is `audit-logs/*`, which matches *objects*, not the bucket itself."

**The bug:** subtle and real. `s3:DeleteBucket` acts on the *bucket* ARN `arn:aws:s3:::audit-logs`, **not** on `arn:aws:s3:::audit-logs/*` (which is objects). The `Deny` statement's `Resource` is `audit-logs/*`, so the `s3:DeleteBucket` deny *never matches the bucket* — it only "denies" `DeleteBucket` on objects, which is meaningless. The first statement's `Allow s3:*` therefore still permits `s3:DeleteBucket` on `arn:aws:s3:::audit-logs`. Someone can delete the entire audit-log bucket despite the apparent guard. (`DeleteObject` is correctly denied, because that *does* act on objects — so the bug is half-invisible: deletes of individual log objects are blocked, but the whole bucket can be nuked.)

**The fix:** the deny must list both ARN forms.

```json
{
  "Sid": "DenyDeletes",
  "Effect": "Deny",
  "Action": ["s3:DeleteObject", "s3:DeleteBucket"],
  "Resource": [
    "arn:aws:s3:::audit-logs",
    "arn:aws:s3:::audit-logs/*"
  ]
}
```

**The lesson:** explicit deny does win — but only over the *resources it actually matches*. A deny with the wrong ARN granularity is a deny that never fires. The S3 bucket-vs-object ARN distinction is the most common place this goes wrong. Always include both `arn:...:bucket` and `arn:...:bucket/*` when a statement should cover both bucket-level and object-level actions.

### Policy 12 — The CI role that can rewrite its own permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CdkDeploy",
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:PutRolePolicy",
        "iam:CreatePolicy",
        "iam:CreatePolicyVersion",
        "iam:PassRole",
        "s3:*",
        "lambda:*",
        "ec2:*"
      ],
      "Resource": "*"
    }
  ]
}
```

**Out loud:** "Allow this CI role to do all of CloudFormation, create and edit IAM roles and policies, create new versions of any policy, pass any role, and do all of S3, Lambda, and EC2 — on *everything*, with no condition and no permission boundary."

**The bug:** this is the policy that makes the lecture's tagline ("your pipeline role is more dangerous than your prod role," which we expand in Week 7) literally true. With `iam:CreatePolicyVersion` on `*`, the CI role can edit the policy attached to *any* role — including the most privileged role in the account — and set it as the default version, granting itself or anyone else admin. With `iam:AttachRolePolicy` + `iam:PassRole` on `*`, it can attach `AdministratorAccess` to a role and pass it. There is no permission boundary capping any of the roles it creates, so every role it makes can also be admin. This single policy is an account takeover waiting for a compromised CI token.

**The fix:** this is exactly the three-roles-and-a-boundary problem Lecture 2 solves. Briefly: scope the IAM actions to a path (`arn:aws:iam::111122223333:role/cdk-*`), *require* a permission boundary on every role the CI role creates (`iam:PermissionsBoundary` condition), scope `PassRole` with `iam:PassedToService`, and split the dangerous CloudFormation-execution permissions into a separate role the CI role does not control. We build the whole thing in Lecture 2.

**The lesson:** the permissions to *manage* permissions (`iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, `iam:CreatePolicyVersion`, `iam:PassRole`) are the crown jewels. A role that holds them without a permission-boundary constraint can become admin, full stop. The only safe way to grant them is bounded — which is the entire subject of the next lecture.

## 1.4 — Verifying your reading with the policy simulator

You do not have to attach a policy to a live principal to test your reading of it. The IAM policy simulator (`aws iam simulate-principal-policy` / `simulate-custom-policy`) runs the same evaluation engine offline. Test Policy 11's bug:

```bash
# Simulate: can the principal delete the audit-logs BUCKET?
aws iam simulate-custom-policy \
  --policy-input-list file://policy-11.json \
  --action-names s3:DeleteBucket \
  --resource-arns arn:aws:s3:::audit-logs \
  --query 'EvaluationResults[0].EvalDecision' \
  --output text
# -> allowed     (the bug: the deny didn't match the bucket ARN)

# And the object delete, which the deny DOES match:
aws iam simulate-custom-policy \
  --policy-input-list file://policy-11.json \
  --action-names s3:DeleteObject \
  --resource-arns arn:aws:s3:::audit-logs/2026-01-01.log \
  --query 'EvaluationResults[0].EvalDecision' \
  --output text
# -> explicitDeny
```

The simulator returns `allowed`, `explicitDeny`, or `implicitDeny`, and — critically — `MatchedStatements`, which tells you *which* statement produced the decision. When you cannot explain a simulator result, you have found a gap in your understanding of the evaluation flow; close it before you ship the policy. In the Friday challenge you will use the simulator to *prove* every bug you find.

For policies that depend on conditions, pass the context with `--context-entries`:

```bash
aws iam simulate-custom-policy \
  --policy-input-list file://policy-7.json \
  --action-names secretsmanager:GetSecretValue \
  --resource-arns arn:aws:secretsmanager:us-east-1:111122223333:secret:prod/db-AbCdEf \
  --context-entries ContextKeyName=aws:PrincipalArn,ContextKeyType=string,ContextKeyValues=arn:aws:iam::111122223333:role/ci-deploy \
  --query 'EvaluationResults[0].EvalDecision' --output text
```

This is the senior move: when someone says "I think this policy allows X," you do not argue — you simulate it and read the `MatchedStatements`. The engine is the source of truth.

## 1.5 — The pattern behind all twelve bugs

Step back and the twelve bugs collapse into five families:

1. **Over-broad `Resource` (`*` when an ARN would do).** Policies 1, 2, 12. The fix is always "scope to the ARN."
2. **Missing condition.** Policies 4 (`aws:PrincipalOrgID`), 5 (`aws:SourceArn`/`aws:SourceAccount`), 6 (`sts:ExternalId`). The fix is always "add the condition that re-narrows the grant."
3. **Wrong condition / wrong attribute.** Policies 7 (`aws:username` not populated for roles), 10 (self-settable tag). The fix is "use an attribute the principal cannot control and that is populated for this principal type."
4. **`Not*` traps and empty-set mistakes.** Policies 3 (`Allow` + `NotAction`), 9 (`NotAction: []`). The fix is "express the allow-list positively, or use an explicit `Deny`."
5. **ARN-granularity and privilege-escalation primitives.** Policies 8 (`kms:*` admin to use-role), 11 (bucket-vs-object ARN), 12 (`iam:*` self-management). The fix is "separate administration from use, match ARN granularity exactly, and bound the permission-management actions."

Every IAM bug you will ever review is one of these five, or a combination. When you read a policy out loud and something feels off, classify the feeling into one of the five families and you will find the bug. That is the muscle Friday's challenge builds and Sunday's peer review grades.

## 1.6 — What to take into Lecture 2

You now understand the engine and can find the five bug families by reading. The open problem from Policy 12 — a role that can manage permissions is a role that can become admin — is the bridge to Lecture 2. The fix is not "never grant IAM-management actions"; teams genuinely need to let developers create roles for their own functions. The fix is to *bound* those actions with a permission boundary, so that no matter what a delegated principal creates, it can never exceed a cap you control. That, plus the three-role CDK-deploy model that uses it, is the whole of the next lecture. Bring your read-it-out-loud habit; we are going to read the boundary policy out loud too, and it is the trickiest one of all because it has to be wrong in *exactly the right ways*.
