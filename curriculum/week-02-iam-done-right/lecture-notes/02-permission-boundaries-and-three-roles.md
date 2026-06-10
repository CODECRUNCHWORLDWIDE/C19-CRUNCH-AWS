# Lecture 2 — Permission Boundaries: The Only Safe Way to Delegate, and Why Your CDK Deploy Needs Three Roles

> **Reading time:** ~90 minutes. **Hands-on time:** ~75 minutes (you author a boundary, attach it, and prove it blocks an over-privileged inline policy).

Lecture 1 ended on Policy 12: a CI role that could create roles, attach any policy, pass any role, and edit any policy version — an account takeover waiting for a leaked token. The fix is not "never delegate IAM." Real teams must let developers create execution roles for their own Lambda functions, create roles for their own ECS tasks, and create roles for their own pipelines. The question is how to do that *without* letting the delegation become privilege escalation. The answer — the only answer that actually holds — is a **permission boundary**. This lecture builds one end-to-end, proves it works, and then shows you the place every AWS engineer meets boundaries whether they mean to or not: the three roles that `cdk bootstrap` creates so that a single `cdk deploy` can run safely.

The mental model to hold the entire time: **a permission boundary is a ceiling, not a floor.** It grants nothing. It only caps. The effective permissions of a bounded principal are the *intersection* of (what its identity policies allow) and (what its boundary allows). If the identity policy says "do X" and the boundary does not include X, the principal cannot do X. If the boundary says "you may do Y" but no identity policy grants Y, the principal still cannot do Y. Both must agree. That intersection is the whole trick, and it is what makes safe delegation possible.

## 2.1 — Why the naive delegation fails

Suppose you want to let your developers manage their own Lambda execution roles. The naive grant:

```json
{
  "Sid": "LetDevsManageRoles",
  "Effect": "Allow",
  "Action": ["iam:CreateRole", "iam:AttachRolePolicy", "iam:PutRolePolicy", "iam:PassRole"],
  "Resource": "*"
}
```

Read it out loud (you have the habit now): "Allow developers to create roles, attach any managed policy, put any inline policy, and pass any role, on everything." A developer with this grant runs:

```bash
aws iam create-role --role-name pwn --assume-role-policy-document file://trust-self.json
aws iam attach-role-policy --role-name pwn \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
aws sts assume-role --role-arn arn:aws:iam::111122223333:role/pwn --role-session-name x
```

They are now admin. They did not need any IAM action you did not give them; you gave them `AttachRolePolicy` on `*` and `AdministratorAccess` is a policy. **The ability to create a role and attach a policy is the ability to grant yourself any permission that exists.** This is why "just give developers IAM and trust them" is not a security posture — a single compromised laptop or leaked token turns into account takeover.

The fix has to satisfy two constraints simultaneously: (1) developers really can create and manage roles, and (2) no role they ever create can exceed a cap you control. A permission boundary, plus a condition that *forces* the boundary onto every role they create, satisfies both.

## 2.2 — Anatomy of a permission boundary

A permission boundary is just a managed policy — the same JSON document as any other. What makes it a *boundary* is *how it is attached*: it goes on the `PermissionsBoundary` slot of an IAM user or role, not the `Policies` slot. AWS then intersects it with the identity policies at evaluation time.

Here is the boundary the week's exercises and mini-project ask for: developers can do anything *except* IAM writes, KMS deletes, and production S3 bucket access.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBroadServiceAccessAsCeiling",
      "Effect": "Allow",
      "Action": [
        "s3:*", "lambda:*", "dynamodb:*", "ec2:*", "ecs:*", "logs:*",
        "cloudwatch:*", "sqs:*", "sns:*", "states:*", "events:*",
        "apigateway:*", "secretsmanager:GetSecretValue", "kms:Encrypt",
        "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey",
        "sts:AssumeRole", "sts:GetCallerIdentity", "iam:GetRole",
        "iam:ListRoles", "iam:PassRole"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyAllIamWrites",
      "Effect": "Deny",
      "Action": [
        "iam:CreateUser", "iam:CreateRole", "iam:CreatePolicy",
        "iam:CreatePolicyVersion", "iam:AttachRolePolicy", "iam:AttachUserPolicy",
        "iam:PutRolePolicy", "iam:PutUserPolicy", "iam:DeleteRolePermissionsBoundary",
        "iam:UpdateAssumeRolePolicy", "iam:CreateAccessKey",
        "iam:UpdateRole", "iam:TagRole", "iam:TagUser"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyKmsDestruction",
      "Effect": "Deny",
      "Action": [
        "kms:ScheduleKeyDeletion", "kms:DisableKey",
        "kms:PutKeyPolicy", "kms:DeleteAlias", "kms:CreateGrant"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyProdS3",
      "Effect": "Deny",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::prod-*",
        "arn:aws:s3:::prod-*/*"
      ]
    }
  ]
}
```

Read it out loud, statement by statement, because a boundary is the one policy where you *want* the broad allow and the targeted denies:

- **Statement 1 (the ceiling):** "Allow a broad set of service actions on everything." This is the *maximum* any bounded role can do. It is intentionally generous — the boundary is a ceiling, and the actual grant comes from the role's own identity policies, which will be much narrower. Note it includes `iam:PassRole` (developers need to pass execution roles) but *not* any IAM write.
- **Statement 2 (no IAM writes):** "Deny all the IAM write actions, everywhere." This is what stops the escalation from 2.1. A developer can create roles only if their *own* policy grants `iam:CreateRole` — and even if it does, this boundary denies it. Wait — then how do they create roles at all? They do not, *directly*. The delegated `iam:CreateRole` lives on a separate, narrowly-scoped policy and is itself gated by the `iam:PermissionsBoundary` condition (2.3). The boundary on the *developer* denies IAM writes; the boundary is what gets *forced onto roles the developer creates*. Keep these two roles distinct in your head; we make it concrete in 2.3.
- **Statement 3 (no KMS destruction):** "Deny scheduling key deletion, disabling keys, rewriting key policies, deleting aliases, and creating grants, everywhere." Developers can *use* keys (encrypt/decrypt is in the ceiling) but cannot destroy them or escalate via grants.
- **Statement 4 (no prod S3):** "Deny every S3 action on buckets whose name starts with `prod-` (and their objects), everywhere." This is the production-data carve-out. Note it lists *both* `prod-*` (bucket) and `prod-*/*` (objects) — Policy 11's lesson from Lecture 1 applies here: a deny must match the right ARN granularity.

The deny statements are the load-bearing part. Because explicit deny wins, a bounded developer who somehow acquires `s3:DeleteObject` on a prod bucket through *any* identity policy is still denied — the boundary's deny overrides. That is the guarantee a boundary gives you: a *hard cap* that no future identity-policy mistake can exceed.

## 2.3 — Forcing the boundary onto delegated roles

Now the subtle, essential part. We want a *separate* role — call it the **delegation role** or the developer's role with IAM-management rights — that *can* create roles, but where every role it creates is *forced* to carry our boundary. This is done with the `iam:PermissionsBoundary` condition key on the `iam:CreateRole`/`iam:PutRolePolicy`/`iam:AttachRolePolicy` actions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CreateRolesOnlyWithBoundary",
      "Effect": "Allow",
      "Action": ["iam:CreateRole", "iam:PutRolePolicy", "iam:AttachRolePolicy"],
      "Resource": "arn:aws:iam::111122223333:role/dev/*",
      "Condition": {
        "StringEquals": {
          "iam:PermissionsBoundary": "arn:aws:iam::111122223333:policy/developer-boundary"
        }
      }
    },
    {
      "Sid": "ManageRolesUnderDevPathOnly",
      "Effect": "Allow",
      "Action": ["iam:DeleteRole", "iam:DeleteRolePolicy", "iam:DetachRolePolicy", "iam:TagRole"],
      "Resource": "arn:aws:iam::111122223333:role/dev/*"
    },
    {
      "Sid": "NeverTouchTheBoundaryItself",
      "Effect": "Deny",
      "Action": ["iam:DeleteRolePermissionsBoundary", "iam:CreatePolicyVersion", "iam:DeletePolicy", "iam:SetDefaultPolicyVersion"],
      "Resource": "arn:aws:iam::111122223333:policy/developer-boundary"
    }
  ]
}
```

Read it out loud:

- **Statement 1:** "Allow creating roles and attaching policies, but *only* under the `/dev/` path, and *only* if the `iam:PermissionsBoundary` being set equals our `developer-boundary` policy ARN." If a developer tries `aws iam create-role` without specifying `--permissions-boundary arn:...:policy/developer-boundary`, the request is **denied** — the condition is not satisfied. They *cannot* create an unbounded role. Every role they create inherits the cap.
- **Statement 2:** "Allow managing (delete, detach, tag) roles, but only under the `/dev/` path." A developer cannot touch roles outside their sandbox path.
- **Statement 3:** "Deny — explicitly and unconditionally — any action that would weaken the boundary policy itself." A developer cannot delete the boundary from a role, cannot publish a new (looser) version of the boundary policy, cannot delete it, cannot change its default version. The boundary is tamper-proof from the developer's side.

This is the *entire* delegation pattern: a generous-but-capped boundary policy, plus a delegation policy that (a) allows role creation only under a path, (b) *requires* the boundary on every created role via the `iam:PermissionsBoundary` condition, and (c) forbids tampering with the boundary. With these three statements, a developer can build all the Lambda execution roles they want and *none of them can ever exceed the boundary*, and the developer cannot remove the boundary to escape it. This is the AWS-documented, AWS-blessed delegation pattern, and it is the only one that actually holds.

### Why the path matters

The `/dev/` path (`role/dev/*`) is doing real work. IAM paths are a namespace inside the ARN. By scoping the delegation role's `iam:*` actions to `role/dev/*`, you guarantee a developer can only create, modify, and delete roles in *their* namespace — they cannot delete the `OrganizationAccountAccessRole`, cannot modify the CI deploy role, cannot touch the boundary. The path is your blast-radius wall. Always combine the boundary condition *with* a path scope; the boundary caps *what the created roles can do*, the path caps *which roles the delegate can touch*.

## 2.4 — Proving it: blocking an over-privileged inline policy

A boundary you have not tested is a hypothesis. Here is the proof, which Exercise 2 automates. A developer creates a bounded role and tries to give it admin via an inline policy:

```bash
# As the delegation role (developer), create a role WITH the required boundary.
aws iam create-role \
  --role-name dev/feature-x-fn \
  --permissions-boundary arn:aws:iam::111122223333:policy/developer-boundary \
  --assume-role-policy-document file://lambda-trust.json

# Now try to make it admin via an over-privileged inline policy.
aws iam put-role-policy \
  --role-name dev/feature-x-fn \
  --policy-name make-me-admin \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"*","Resource":"*"}]}'
# This put SUCCEEDS — putting the policy is allowed. The boundary acts at EVALUATION time.
```

The inline policy attaches. That surprises people: the boundary did not stop the `put`. The boundary stops the *use*. Verify with the simulator:

```bash
# The role's identity policy says Action:* Resource:*. Does the role actually have admin?
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/dev/feature-x-fn \
  --action-names iam:CreateUser s3:GetObject kms:ScheduleKeyDeletion \
  --resource-arns '*' \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' \
  --output table
```

Expected result:

```
------------------------------------------------
|          SimulatePrincipalPolicy             |
+--------------------------+-------------------+
|          Action          |     Decision      |
+--------------------------+-------------------+
|  iam:CreateUser          |  explicitDeny     |   <- boundary Statement 2 wins
|  s3:GetObject            |  allowed          |   <- ceiling allows; identity * allows
|  kms:ScheduleKeyDeletion |  explicitDeny     |   <- boundary Statement 3 wins
+--------------------------+-------------------+
```

The inline policy said `Action: "*"`, but the boundary's deny statements override. `iam:CreateUser` and `kms:ScheduleKeyDeletion` are `explicitDeny` because the boundary denies them; `s3:GetObject` is `allowed` because both the inline `*` and the boundary's ceiling permit it. The over-privileged inline policy was **neutralized by the boundary** for the dangerous actions while still working for the safe ones. That is the boundary doing exactly its job: capping, not granting, with explicit deny winning. *That* is the artifact you submit as proof in Exercise 2.

The `simulate-principal-policy` call uses the *live* role including its boundary, so it is the highest-fidelity test short of actually attempting the action. Wire it into CI and you have a regression test for your security posture.

## 2.5 — `sts:AssumeRole` chains and how humans actually get in

Now we turn from delegation to access. In a 2026 shop, humans do not have IAM users in each account. They authenticate once at **IAM Identity Center** (formerly AWS SSO), pick an account and a *permission set*, and Identity Center mints a short-lived role session in that account. Under the hood, a permission set is a role (named `AWSReservedSSO_<name>_<hash>`) provisioned into each assigned account, and "logging in" is `sts:AssumeRoleWithSAML` against it. The credentials expire (1–12 hours, you choose); there is nothing long-lived to leak.

From that first session, a human (or a tool) can **chain**: assume another role from the role they are already in. The exercises build exactly this — a human lands in `identity` via Identity Center, then assumes a `DeveloperAccess` role in `dev` and a separate `ReadOnly` role in `prod`:

```bash
# 1. Human logs in via Identity Center (sets up a profile that does AssumeRoleWithSAML).
aws sso login --profile identity-sso

# 2. From the identity-account session, assume the dev developer role (a chained AssumeRole).
aws sts assume-role \
  --role-arn arn:aws:iam::222233334444:role/CrossAccountDeveloper \
  --role-session-name jeanstephane-dev \
  --profile identity-sso \
  --duration-seconds 3600
```

Two rules bite here:

1. **Chained sessions are capped at one hour.** When you `AssumeRole` *using credentials that were themselves obtained via `AssumeRole`*, the resulting session cannot exceed `DurationSeconds: 3600`, regardless of the role's `MaxSessionDuration`. Ask for more and STS errors. This is a deliberate guard against indefinite chains. If you need longer, restructure so the chain is shorter, or use Identity Center session duration for the first hop.
2. **The session name is your audit trail.** `--role-session-name jeanstephane-dev` shows up in CloudTrail as `arn:aws:sts::222233334444:assumed-role/CrossAccountDeveloper/jeanstephane-dev`. Make session names identify the *human* (or the CI run), because the role ARN alone tells you nothing about *who* used it. In Identity Center, the session name is set to the user's identity automatically — one more reason to prefer it over hand-rolled assume-role.

The trust policy on `CrossAccountDeveloper` in `dev` is the other half — it must allow the `identity` account (or specifically the Identity Center permission-set roles) to assume it:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowIdentityAccountHumans",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::111111111111:root" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "aws:PrincipalOrgID": "o-abc123def4" },
        "Bool": { "aws:MultiFactorAuthPresent": "true" }
      }
    }
  ]
}
```

Read it out loud: "Allow principals in the `identity` account (`111111111111`) to assume this role, but only if they are in our Organization *and* they authenticated with MFA." The `aws:PrincipalOrgID` condition means that even though we trust the whole `:root` of the identity account, only principals that belong to *our* Organization can use it — a stolen role ARN from outside the Org is useless. The `aws:MultiFactorAuthPresent` condition means a session without MFA (e.g., a leaked non-MFA credential) cannot assume into `dev`. Two conditions, both load-bearing.

### Session policies — the third cap

When you `AssumeRole`, you can pass an inline **session policy** that *further restricts* the resulting session (it never expands it — same intersection rule as a boundary). This is how a tool that holds a powerful role can hand out a deliberately weaker session to a sub-process:

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::222233334444:role/CrossAccountDeveloper \
  --role-session-name readonly-audit \
  --policy '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetObject","s3:ListBucket"],"Resource":"*"}]}'
```

The resulting session can do *only* `s3:GetObject`/`s3:ListBucket` even though `CrossAccountDeveloper` can do far more — the session policy intersects down. Session policies are how you implement "give this short-lived job the least it needs" without creating a new role for every job. They are the fourth cap in the evaluation flow (after SCPs and the permission boundary) and the most ephemeral.

## 2.6 — Why your CDK deploy needs three roles

Now the payoff. When you run `cdk bootstrap`, AWS provisions a set of roles into the account so that `cdk deploy` can run safely. The three that matter:

1. **The deploy role (`cdk-<qualifier>-deploy-role`).** This is the role your *human or CI principal assumes* to start a deploy. It is trusted by your account (and, for cross-account deploys, the pipeline account). It can read/write the bootstrap S3 bucket and ECR repo, and — crucially — it can `sts:AssumeRole` into the *CloudFormation execution role* and the *file-publishing role*. It cannot, by itself, create your application's resources. Its job is orchestration.

2. **The file-publishing role (`cdk-<qualifier>-file-publishing-role`).** This role can write your synthesized assets (Lambda zips, Docker images, the template itself) to the bootstrap bucket and ECR. It has S3/ECR permissions and nothing else. Separating it means the credential that *uploads artifacts* is not the credential that *creates infrastructure* — a compromised asset-upload step cannot create an admin role.

3. **The CloudFormation execution role (`cdk-<qualifier>-cfn-exec-role`).** This is the role CloudFormation *itself* assumes to create your stack's resources. It is the powerful one — by default it has `AdministratorAccess`, because a stack can create anything. But — and this is the lecture's whole point — **this role is assumed only by the CloudFormation service, conditioned on `aws:SourceArn` being a stack in your account, and never held by a human or CI directly.** The deploy role passes it to CloudFormation; CloudFormation assumes it; the human never has its credentials.

Why three and not one? Because of Policy 12 from Lecture 1. A single role that can both *upload artifacts* and *create any resource* and is *held directly by CI* is the account-takeover policy. By splitting into three, with the most powerful one (CFN execution) only ever assumed by the CloudFormation *service* (not by the human, not by CI), you get separation of duties:

- A compromised CI token gets the **deploy role**, which can start deploys but cannot directly create resources — it can only ask CloudFormation to, and CloudFormation only does what the *template* says.
- A compromised artifact-upload step gets the **file-publishing role**, which can poison an asset but cannot create infrastructure.
- The **CFN execution role's** admin power is only wielded by AWS's CloudFormation service, gated by `aws:SourceArn` to your own stacks. There is no credential for an attacker to steal — the service holds it transiently.

This is the same delegation-with-boundaries idea from 2.2–2.4, expressed as *separation of roles by job*. You can (and in regulated shops, should) replace the default `AdministratorAccess` on the CFN execution role with a **permission boundary** of your own — `cdk bootstrap --custom-permissions-boundary <name>` does exactly this, so that even CloudFormation cannot create a resource outside your boundary. That single flag is the bridge between this lecture and Week 3: the boundary you author this week becomes the cap on what *any* CDK deploy can ever provision.

The trust policy on the CFN execution role, read out loud, is the cleanest example of the `aws:SourceArn` confused-deputy fix from Lecture 1's Policy 5:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "cloudformation.amazonaws.com" },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": { "aws:SourceAccount": "111122223333" },
      "ArnLike": { "aws:SourceArn": "arn:aws:cloudformation:*:111122223333:stack/*" }
    }
  }]
}
```

"Allow the CloudFormation service to assume this role, but only when the request originates from a CloudFormation stack in *my* account." Without the `aws:SourceArn`/`aws:SourceAccount` conditions, you would have Policy 5's confused-deputy bug on the most powerful role in your account. With them, the admin power is bound to your stacks and no one else's.

## 2.7 — The same model in three tools

You will express these constructs three ways this week. The model is identical; what differs is what the tool checks for you.

**CDK TypeScript** — boundaries are first-class:

```typescript
import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';

export class BoundaryStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const boundary = new iam.ManagedPolicy(this, 'DeveloperBoundary', {
      managedPolicyName: 'developer-boundary',
      statements: [
        new iam.PolicyStatement({
          sid: 'Ceiling',
          actions: ['s3:*', 'lambda:*', 'dynamodb:*', 'logs:*', 'sts:AssumeRole', 'iam:PassRole'],
          resources: ['*'],
        }),
        new iam.PolicyStatement({
          sid: 'DenyIamWrites',
          effect: iam.Effect.DENY,
          actions: ['iam:Create*', 'iam:Attach*', 'iam:Put*', 'iam:DeleteRolePermissionsBoundary'],
          resources: ['*'],
        }),
        new iam.PolicyStatement({
          sid: 'DenyProdS3',
          effect: iam.Effect.DENY,
          actions: ['s3:*'],
          resources: ['arn:aws:s3:::prod-*', 'arn:aws:s3:::prod-*/*'],
        }),
      ],
    });

    // Every role created in this app inherits the boundary:
    iam.PermissionsBoundary.of(this).apply(boundary);
  }
}
```

`iam.PermissionsBoundary.of(this).apply(boundary)` is the line that matters — it forces the boundary onto *every* role and user the CDK app creates in this scope. CDK checks the JSON is well-formed at synth; it does *not* check that your boundary actually denies what you think (only a simulator or Access Analyzer does that).

**CDK Python** — identical model:

```python
from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


class BoundaryStack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)

        boundary = iam.ManagedPolicy(
            self, "DeveloperBoundary",
            managed_policy_name="developer-boundary",
            statements=[
                iam.PolicyStatement(
                    sid="Ceiling",
                    actions=["s3:*", "lambda:*", "dynamodb:*", "logs:*",
                             "sts:AssumeRole", "iam:PassRole"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    sid="DenyIamWrites",
                    effect=iam.Effect.DENY,
                    actions=["iam:Create*", "iam:Attach*", "iam:Put*",
                             "iam:DeleteRolePermissionsBoundary"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    sid="DenyProdS3",
                    effect=iam.Effect.DENY,
                    actions=["s3:*"],
                    resources=["arn:aws:s3:::prod-*", "arn:aws:s3:::prod-*/*"],
                ),
            ],
        )
        iam.PermissionsBoundary.of(self).apply(boundary)
```

**OpenTofu** — the `aws_iam_policy_document` data source generates the JSON, and you wire it onto the role with `permissions_boundary`:

```hcl
data "aws_iam_policy_document" "developer_boundary" {
  statement {
    sid       = "Ceiling"
    effect    = "Allow"
    actions   = ["s3:*", "lambda:*", "dynamodb:*", "logs:*", "sts:AssumeRole", "iam:PassRole"]
    resources = ["*"]
  }
  statement {
    sid       = "DenyIamWrites"
    effect    = "Deny"
    actions   = ["iam:Create*", "iam:Attach*", "iam:Put*", "iam:DeleteRolePermissionsBoundary"]
    resources = ["*"]
  }
  statement {
    sid       = "DenyProdS3"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = ["arn:aws:s3:::prod-*", "arn:aws:s3:::prod-*/*"]
  }
}

resource "aws_iam_policy" "developer_boundary" {
  name   = "developer-boundary"
  policy = data.aws_iam_policy_document.developer_boundary.json
}

resource "aws_iam_role" "developer" {
  name                 = "developer"
  permissions_boundary = aws_iam_policy.developer_boundary.arn
  assume_role_policy    = data.aws_iam_policy_document.dev_trust.json
}
```

What each checks: CDK (both languages) validates JSON shape and catches some ARN-format errors at synth; OpenTofu's `aws_iam_policy_document` validates the document structure at `plan` and refuses to even generate a malformed statement, which is a real advantage — but none of the three tools tells you whether the *semantics* are right. "Does this boundary actually prevent escalation?" is answered only by the simulator, Access Analyzer, or a human reading it out loud. The tools generate; you verify. That division of labor is the entire point of this week.

## 2.8 — The checklist you carry forward

When you delegate IAM to anyone — a developer, a pipeline, another team — apply this checklist:

1. **Author a boundary** that caps the maximum (broad allow ceiling + targeted denies for the crown jewels: IAM writes, KMS destruction, prod data).
2. **Force the boundary** onto every role the delegate can create, via the `iam:PermissionsBoundary` condition on their `iam:CreateRole`/`iam:Put*`/`iam:Attach*`.
3. **Scope by path** (`role/dev/*`) so the delegate can only touch their own namespace.
4. **Forbid boundary tampering** with an explicit deny on `iam:DeleteRolePermissionsBoundary` and `iam:CreatePolicyVersion`/`iam:SetDefaultPolicyVersion` on the boundary policy.
5. **Separate roles by job** for anything as powerful as a deploy — orchestration, artifact-publishing, and resource-creation are three roles, not one, and the powerful one is assumed only by a service, gated on `aws:SourceArn`.
6. **Prove it** with `aws iam simulate-principal-policy` before you call it done, and let Access Analyzer watch it continuously after.

Steps 1–4 are Exercise 2. Step 5 is what `cdk bootstrap` does for you in Week 3. Step 6 is Exercise 3 and the mini-project's clean-report requirement. Everything in this week is one of these six things, and a senior engineer does all six without being asked.
