# Exercise 1 — A Three-Account Topology with IAM Identity Center

> **Estimated time:** ~3 hours. This is the foundation the rest of the week (and the capstone's Identity requirement) builds on. Take your time and read every trust policy out loud before you apply it.

## Goal

Stand up the human-access layer of a real AWS shop:

- An Organization (you have one from Week 1) with three member accounts: `identity`, `dev`, `prod`.
- **IAM Identity Center** enabled in the management/`identity` account, with **one** permission set (`DeveloperBaseline`).
- A human user in Identity Center who, after a single `aws sso login`, can:
  - **assume `CrossAccountDeveloper` in `dev`** (read/write the dev sandbox), and
  - **assume `CrossAccountReadOnly` in `prod`** (look but do not touch).
- Both target roles trust the `identity` account, scoped by `aws:PrincipalOrgID` and gated on MFA.

You will build the cross-account roles in CDK (so they are reproducible) and wire up Identity Center and the local profiles by CLI/console (Identity Center has limited CDK/CFN support and is genuinely easier to bootstrap by hand the first time).

## Prerequisites

- Week 1 Organization standing, with the org ID handy: `aws organizations describe-organization --query 'Organization.Id' --output text`.
- Three account IDs. If you only have one learner account, see **Single-account fallback** at the end — you simulate the topology with three roles in one account.
- CDK v2 CLI (`cdk --version` ≥ 2.160.0) and a bootstrapped `dev` and `prod` account (`cdk bootstrap` — Week 3 covers it in depth; for now `cdk bootstrap aws://222233334444/us-east-1 --profile dev` is enough).

## Step 1 — Confirm the accounts exist and you can reach them

```bash
aws organizations list-accounts \
  --query 'Accounts[].{Id:Id,Name:Name,Email:Email}' --output table
```

You should see `identity`, `dev`, `prod` (plus the management account if separate). If you created the OUs in Week 1 but not these accounts, create them now:

```bash
aws organizations create-account --account-name dev   --email aws-dev@yourdomain.example
aws organizations create-account --account-name prod  --email aws-prod@yourdomain.example
# 'identity' may be your management account, or a dedicated one. A dedicated identity
# account is the production-correct choice; the management account is acceptable for the lab.
```

Account creation is asynchronous — `create-account` returns a request ID; poll with `describe-create-account-status`.

## Step 2 — The cross-account roles, in CDK

Create a CDK app for the trust layer. This is the **starter**: it has the structure but leaves the trust conditions for you to fill in.

```bash
mkdir identity-layer && cd identity-layer
cdk init app --language typescript
npm install
```

Replace `lib/identity-layer-stack.ts` with this **starter**:

```typescript
import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';

interface TrustStackProps extends StackProps {
  readonly identityAccountId: string; // 111111111111
  readonly orgId: string;             // o-abc123def4
  readonly accessLevel: 'developer' | 'readonly';
}

export class CrossAccountRoleStack extends Stack {
  constructor(scope: Construct, id: string, props: TrustStackProps) {
    super(scope, id, props);

    // TODO 1 — Build the trust principal:
    //   Trust the identity account's :root, BUT condition on:
    //     - aws:PrincipalOrgID == props.orgId   (only our Org)
    //     - aws:MultiFactorAuthPresent == true  (only MFA sessions)
    //   Hint: new iam.AccountPrincipal(props.identityAccountId)
    //         .withConditions({ StringEquals: {...}, Bool: {...} })

    // TODO 2 — Create the role:
    //   roleName: props.accessLevel === 'developer'
    //     ? 'CrossAccountDeveloper' : 'CrossAccountReadOnly'
    //   maxSessionDuration: 1 hour (chained sessions cap at 1h anyway)
    //   assumedBy: the principal from TODO 1

    // TODO 3 — Attach permissions:
    //   developer -> a scoped set (NOT AdministratorAccess). Start with
    //     AWS managed 'PowerUserAccess' MINUS iam (we tighten with the
    //     boundary in Exercise 2). For now: PowerUserAccess is acceptable
    //     because Exercise 2 adds the boundary that caps it.
    //   readonly  -> AWS managed 'ReadOnlyAccess'
  }
}
```

And `bin/identity-layer.ts`:

```typescript
#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { CrossAccountRoleStack } from '../lib/identity-layer-stack';

const app = new cdk.App();
const orgId = app.node.tryGetContext('orgId') ?? 'o-REPLACE';
const identityAccountId = app.node.tryGetContext('identityAccountId') ?? '111111111111';

new CrossAccountRoleStack(app, 'DevAccess', {
  env: { account: '222233334444', region: 'us-east-1' },
  identityAccountId, orgId, accessLevel: 'developer',
});

new CrossAccountRoleStack(app, 'ProdAccess', {
  env: { account: '333344445555', region: 'us-east-1' },
  identityAccountId, orgId, accessLevel: 'readonly',
});
```

## Step 3 — Fill in the TODOs (solution)

Here is the completed `lib/identity-layer-stack.ts`. Try the starter first; check yourself against this.

```typescript
import { Stack, StackProps, Duration } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';

interface TrustStackProps extends StackProps {
  readonly identityAccountId: string;
  readonly orgId: string;
  readonly accessLevel: 'developer' | 'readonly';
}

export class CrossAccountRoleStack extends Stack {
  constructor(scope: Construct, id: string, props: TrustStackProps) {
    super(scope, id, props);

    // TODO 1 — trust the identity account, but only our Org, only with MFA.
    const trustedPrincipal = new iam.AccountPrincipal(props.identityAccountId)
      .withConditions({
        StringEquals: { 'aws:PrincipalOrgID': props.orgId },
        Bool: { 'aws:MultiFactorAuthPresent': 'true' },
      });

    // TODO 2 — the role.
    const role = new iam.Role(this, 'CrossAccountRole', {
      roleName:
        props.accessLevel === 'developer'
          ? 'CrossAccountDeveloper'
          : 'CrossAccountReadOnly',
      assumedBy: trustedPrincipal,
      maxSessionDuration: Duration.hours(1), // chained sessions cap at 1h regardless
      description: `Assumed from the identity account (${props.identityAccountId}) by Org humans with MFA`,
    });

    // TODO 3 — permissions.
    if (props.accessLevel === 'developer') {
      // PowerUserAccess = everything except IAM/Org. Exercise 2 adds the boundary
      // that further caps this (no KMS deletes, no prod S3). For now this is the
      // ceiling; the boundary is the real guard.
      role.addManagedPolicy(
        iam.ManagedPolicy.fromAwsManagedPolicyName('PowerUserAccess'),
      );
    } else {
      role.addManagedPolicy(
        iam.ManagedPolicy.fromAwsManagedPolicyName('ReadOnlyAccess'),
      );
    }
  }
}
```

Deploy:

```bash
cdk deploy DevAccess  --profile dev  --context orgId=o-abc123def4 --context identityAccountId=111111111111
cdk deploy ProdAccess --profile prod --context orgId=o-abc123def4 --context identityAccountId=111111111111
```

**Read the generated trust policy out loud before moving on:**

```bash
aws iam get-role --role-name CrossAccountDeveloper --profile dev \
  --query 'Role.AssumeRolePolicyDocument'
```

"Allow the identity account to assume this role, but only if the principal is in Org `o-abc123def4` and authenticated with MFA." If it does not say that, you have a bug — fix it before Step 4.

## Step 4 — Enable IAM Identity Center and create the permission set

Identity Center is enabled once per Organization, in the management account, in a region you choose. The first-time enable is a console action (Identity Center → Enable). After that:

```bash
# Find your Identity Center instance.
aws sso-admin list-instances \
  --query 'Instances[0].{InstanceArn:InstanceArn,IdentityStore:IdentityStoreId}' --output table
```

Create the single permission set, `DeveloperBaseline`. It is intentionally minimal — its only job is to land the human in the `identity` account with the right to *assume* the cross-account roles:

```bash
INSTANCE_ARN=$(aws sso-admin list-instances --query 'Instances[0].InstanceArn' --output text)

aws sso-admin create-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --name DeveloperBaseline \
  --description "Land in identity account; assume CrossAccount* roles in dev/prod" \
  --session-duration PT8H
```

Attach an inline policy to the permission set that allows assuming the two target roles and nothing else:

```bash
PS_ARN=$(aws sso-admin list-permission-sets --instance-arn "$INSTANCE_ARN" \
  --query 'PermissionSets[0]' --output text)

aws sso-admin put-inline-policy-to-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --permission-set-arn "$PS_ARN" \
  --inline-policy '{
    "Version": "2012-10-17",
    "Statement": [{
      "Sid": "AssumeDevAndProdRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::222233334444:role/CrossAccountDeveloper",
        "arn:aws:iam::333344445555:role/CrossAccountReadOnly"
      ]
    }]
  }'
```

Read it out loud: "Allow this permission set to assume exactly two roles — `CrossAccountDeveloper` in dev and `CrossAccountReadOnly` in prod — and nothing else." That is the entire blast radius of the permission set.

Create a user in the Identity Center identity store and assign the permission set to the `identity` account:

```bash
ID_STORE=$(aws sso-admin list-instances --query 'Instances[0].IdentityStoreId' --output text)

USER_ID=$(aws identitystore create-user \
  --identity-store-id "$ID_STORE" \
  --user-name jeanstephane \
  --display-name "Jean-Stephane" \
  --name 'FamilyName=Aloyd,GivenName=Jean-Stephane' \
  --emails 'Value=jeanstephane@aloyd.com,Type=work,Primary=true' \
  --query 'UserId' --output text)

aws sso-admin create-account-assignment \
  --instance-arn "$INSTANCE_ARN" \
  --target-id 111111111111 --target-type AWS_ACCOUNT \
  --permission-set-arn "$PS_ARN" \
  --principal-type USER --principal-id "$USER_ID"
```

## Step 5 — Configure local profiles for the chain

Add to `~/.aws/config`:

```ini
[sso-session crunch]
sso_start_url = https://your-org.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile identity-sso]
sso_session = crunch
sso_account_id = 111111111111
sso_role_name = DeveloperBaseline
region = us-east-1

[profile dev]
source_profile = identity-sso
role_arn = arn:aws:iam::222233334444:role/CrossAccountDeveloper
mfa_serial = arn:aws:iam::111111111111:mfa/jeanstephane
region = us-east-1

[profile prod]
source_profile = identity-sso
role_arn = arn:aws:iam::333344445555:role/CrossAccountReadOnly
region = us-east-1
```

The `dev` and `prod` profiles *chain*: they use the `identity-sso` SSO session as their source and assume the cross-account role on top of it.

## Step 6 — Prove the chain works

```bash
aws sso login --profile identity-sso

# Who am I in the identity account?
aws sts get-caller-identity --profile identity-sso
# Account: 111111111111, Arn: .../AWSReservedSSO_DeveloperBaseline_.../jeanstephane

# Assume into dev (the chain happens automatically because of source_profile):
aws sts get-caller-identity --profile dev
# Account: 222233334444, Arn: arn:aws:sts::222233334444:assumed-role/CrossAccountDeveloper/botocore-session-...

# Assume into prod:
aws sts get-caller-identity --profile prod
# Account: 333344445555, Arn: arn:aws:sts::333344445555:assumed-role/CrossAccountReadOnly/...
```

Now prove the read-only boundary on `prod`:

```bash
aws s3 ls --profile prod                       # works (read)
aws s3api create-bucket --bucket should-fail-$RANDOM --profile prod
# -> An error occurred (AccessDenied) ... explicit deny / not authorized
```

The `ReadOnlyAccess` managed policy has no write actions, so the create is an implicit deny. You have proven a human can look at prod but not change it.

## Acceptance criteria

- [ ] `aws organizations list-accounts` shows `identity`, `dev`, `prod`.
- [ ] `CrossAccountDeveloper` exists in `dev` and `CrossAccountReadOnly` exists in `prod`, both created by CDK.
- [ ] Both trust policies condition on `aws:PrincipalOrgID` (and the dev role on `aws:MultiFactorAuthPresent`). Verify with `get-role`.
- [ ] One Identity Center permission set (`DeveloperBaseline`) exists, whose inline policy allows `sts:AssumeRole` only on the two specific role ARNs.
- [ ] After `aws sso login --profile identity-sso`, `aws sts get-caller-identity --profile dev` returns an `assumed-role/CrossAccountDeveloper/...` ARN in account `222233334444`.
- [ ] `aws s3 ls --profile prod` succeeds; an `s3api create-bucket --profile prod` is denied.
- [ ] You can read every trust policy you created out loud and state what it allows and denies.

## Smoke output (target)

```
$ aws sts get-caller-identity --profile dev
{
    "UserId": "AROAEXAMPLEDEV:botocore-session-1718000000",
    "Account": "222233334444",
    "Arn": "arn:aws:sts::222233334444:assumed-role/CrossAccountDeveloper/botocore-session-1718000000"
}

$ aws s3api create-bucket --bucket should-fail-12345 --profile prod
An error occurred (AccessDenied) when calling the CreateBucket operation:
User: arn:aws:sts::333344445555:assumed-role/CrossAccountReadOnly/... is not authorized
to perform: s3:CreateBucket because no identity-based policy allows the s3:CreateBucket action
```

## Single-account fallback

If you have only one learner account, simulate the topology with three roles in that one account:

- Create `CrossAccountDeveloper` and `CrossAccountReadOnly` whose trust policy trusts your *own* account's `:root` (with `aws:MultiFactorAuthPresent` still required). You lose the true cross-account isolation and the `aws:PrincipalOrgID` enforcement (a single account is trivially in its own Org), but you keep the assume-role chain, the MFA condition, the read-only proof, and — most importantly — the boundary work in Exercise 2, which is account-local anyway. Note in your journal which behaviors you could not exercise.

## What you carry forward

The `CrossAccountDeveloper` role you just made has `PowerUserAccess` — broad. Exercise 2 attaches the `developer-boundary` permission boundary to it and proves the boundary caps it: no IAM writes, no KMS deletes, no prod S3, *even though* `PowerUserAccess` would otherwise allow them. Keep this CDK app; you will add one line to it.
