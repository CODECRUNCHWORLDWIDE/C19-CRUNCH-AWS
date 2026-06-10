// Exercise 2 — A Permission Boundary That Caps a Developer Role, Proven
//
// Goal: Author the `developer-boundary` managed policy from Lecture 2, attach
//       it to the CrossAccountDeveloper role you built in Exercise 1, and then
//       PROVE — with aws iam simulate-principal-policy — that the boundary
//       neutralizes an over-privileged inline policy. The boundary caps; it
//       never grants. Explicit deny wins.
//
// Estimated time: ~3 hours (most of it is reading the simulator output and
//                 reconciling it with the evaluation flow, not typing).
//
// -----------------------------------------------------------------------------
// HOW TO USE THIS FILE
// -----------------------------------------------------------------------------
//
// 1. Reuse the `identity-layer` CDK app from Exercise 1, OR scaffold a fresh one:
//
//      mkdir boundary-lab && cd boundary-lab
//      cdk init app --language typescript
//      npm install
//
//    Replace `lib/<app>-stack.ts` with the contents of THIS FILE, and point
//    `bin/<app>.ts` at the BoundaryStack export (see the bottom of this file
//    for the exact bin/ wiring).
//
// 2. Deploy to the dev account from Exercise 1:
//
//      cdk deploy DeveloperBoundary --profile dev \
//        --context accountId=222233334444
//
// 3. Run the proof. The deploy prints the boundary ARN as an output; feed it
//    to the `prove.sh` snippet at the bottom of this file. You MUST see
//    explicitDeny for iam:CreateUser and kms:ScheduleKeyDeletion and `allowed`
//    for s3:GetObject — that is the whole exercise.
//
// -----------------------------------------------------------------------------
// ACCEPTANCE CRITERIA
// -----------------------------------------------------------------------------
//
//   [ ] `cdk synth` emits a ManagedPolicy named `developer-boundary` with a
//       broad Allow ceiling and three Deny statements (IAM writes, KMS deletes,
//       prod S3).
//   [ ] The CrossAccountDeveloper role carries the boundary in its
//       PermissionsBoundary slot (verify: aws iam get-role ... PermissionsBoundary).
//   [ ] After putting an over-privileged inline policy (Action:* Resource:*) on
//       the role, simulate-principal-policy returns:
//          iam:CreateUser           -> explicitDeny
//          kms:ScheduleKeyDeletion  -> explicitDeny
//          s3:GetObject             -> allowed
//   [ ] Every `resources: ['*']` in your code carries a one-line comment
//       justifying the wildcard (the week's rule).
//   [ ] You can read the boundary out loud, statement by statement.
//
// -----------------------------------------------------------------------------

import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';

export interface BoundaryStackProps extends StackProps {
  /** The dev account ID — e.g. '222233334444'. */
  readonly accountId: string;
  /**
   * The name of the role created in Exercise 1 that we attach the boundary to.
   * Defaults to the role Exercise 1 created.
   */
  readonly developerRoleName?: string;
}

export class BoundaryStack extends Stack {
  constructor(scope: Construct, id: string, props: BoundaryStackProps) {
    super(scope, id, props);

    const account = props.accountId;
    const roleName = props.developerRoleName ?? 'CrossAccountDeveloper';

    // -------------------------------------------------------------------------
    // The boundary: a broad Allow CEILING + targeted DENIES for the crown jewels.
    // Read it out loud, statement by statement. A boundary is the one policy
    // where the broad Allow ceiling is correct, because it only CAPS — the role
    // still needs its own identity policy to actually do anything.
    // -------------------------------------------------------------------------
    const boundary = new iam.ManagedPolicy(this, 'DeveloperBoundary', {
      managedPolicyName: 'developer-boundary',
      description:
        'Developers may do anything EXCEPT IAM writes, KMS destruction, and prod S3. ' +
        'Attached as a PermissionsBoundary; caps, never grants.',
      statements: [
        // Statement 1 — the ceiling. The MAXIMUM a bounded role can ever do.
        // Intentionally generous: the role's own identity policy is the real,
        // narrow grant. Note: includes iam:PassRole (devs pass exec roles) but
        // NO iam write action.
        new iam.PolicyStatement({
          sid: 'AllowBroadServiceAccessAsCeiling',
          effect: iam.Effect.ALLOW,
          actions: [
            's3:*',
            'lambda:*',
            'dynamodb:*',
            'ec2:*',
            'ecs:*',
            'logs:*',
            'cloudwatch:*',
            'sqs:*',
            'sns:*',
            'states:*',
            'events:*',
            'apigateway:*',
            'secretsmanager:GetSecretValue',
            'kms:Encrypt',
            'kms:Decrypt',
            'kms:GenerateDataKey',
            'kms:DescribeKey',
            'sts:AssumeRole',
            'sts:GetCallerIdentity',
            'iam:GetRole',
            'iam:ListRoles',
            'iam:PassRole',
          ],
          // Wildcard justified: this is a permission-boundary CEILING. It grants
          // nothing on its own; the role's identity policy does the granting and
          // is narrowly scoped. The deny statements below are the load-bearing part.
          resources: ['*'],
        }),

        // Statement 2 — no IAM writes, anywhere. This is what stops privilege
        // escalation (Lecture 1, Policy 12 / Lecture 2, section 2.1).
        new iam.PolicyStatement({
          sid: 'DenyAllIamWrites',
          effect: iam.Effect.DENY,
          actions: [
            'iam:CreateUser',
            'iam:CreateRole',
            'iam:CreatePolicy',
            'iam:CreatePolicyVersion',
            'iam:AttachRolePolicy',
            'iam:AttachUserPolicy',
            'iam:PutRolePolicy',
            'iam:PutUserPolicy',
            'iam:DeleteRolePermissionsBoundary',
            'iam:UpdateAssumeRolePolicy',
            'iam:CreateAccessKey',
            'iam:UpdateRole',
            'iam:TagRole',
            'iam:TagUser',
          ],
          // Wildcard justified: a deny on IAM writes must apply to ALL principals
          // and policies; scoping it would leave escalation paths open.
          resources: ['*'],
        }),

        // Statement 3 — no KMS destruction or grant-based escalation. Devs may
        // USE keys (encrypt/decrypt are in the ceiling) but not destroy them.
        new iam.PolicyStatement({
          sid: 'DenyKmsDestruction',
          effect: iam.Effect.DENY,
          actions: [
            'kms:ScheduleKeyDeletion',
            'kms:DisableKey',
            'kms:PutKeyPolicy',
            'kms:DeleteAlias',
            'kms:CreateGrant',
          ],
          // Wildcard justified: key destruction must be denied on EVERY key; a
          // per-key list would silently miss keys created later.
          resources: ['*'],
        }),

        // Statement 4 — no production S3. Lists BOTH the bucket ARN and the
        // object ARN (Lecture 1, Policy 11: a deny must match ARN granularity).
        new iam.PolicyStatement({
          sid: 'DenyProdS3',
          effect: iam.Effect.DENY,
          actions: ['s3:*'],
          resources: [
            'arn:aws:s3:::prod-*', // the bucket itself (ListBucket, DeleteBucket, ...)
            'arn:aws:s3:::prod-*/*', // the objects (GetObject, PutObject, ...)
          ],
        }),
      ],
    });

    // -------------------------------------------------------------------------
    // Attach the boundary to the existing CrossAccountDeveloper role.
    //
    // We import the role by name (it was created by Exercise 1's stack) and set
    // its PermissionsBoundary. In a single CDK app you would instead use
    // iam.PermissionsBoundary.of(this).apply(boundary) to force it on every role
    // the app creates — see Lecture 2, section 2.7. Here we attach to the one
    // pre-existing role so the proof in Exercise 1 + 2 chains together.
    //
    // NOTE: CDK cannot mutate the PermissionsBoundary of a role it did not
    // create. So this stack EMITS the boundary; you attach it with one CLI call
    // (printed as an output below) OR, if you fold this into the Exercise 1 app,
    // add `permissionsBoundary: boundary` to the Role props directly.
    // -------------------------------------------------------------------------

    new CfnOutput(this, 'BoundaryArn', {
      value: boundary.managedPolicyArn,
      description: 'Attach this to CrossAccountDeveloper with put-role-permissions-boundary',
    });

    new CfnOutput(this, 'AttachCommand', {
      value: [
        'aws iam put-role-permissions-boundary',
        `--role-name ${roleName}`,
        `--permissions-boundary ${boundary.managedPolicyArn}`,
        '--profile dev',
      ].join(' '),
      description: 'Run this to bind the boundary to the Exercise 1 developer role',
    });

    new CfnOutput(this, 'RoleArn', {
      value: `arn:aws:iam::${account}:role/${roleName}`,
      description: 'Feed this to simulate-principal-policy in the proof step',
    });
  }
}

// -----------------------------------------------------------------------------
// bin/ WIRING (put this in bin/<app>.ts)
// -----------------------------------------------------------------------------
//
//   #!/usr/bin/env node
//   import * as cdk from 'aws-cdk-lib';
//   import { BoundaryStack } from '../lib/boundary-lab-stack';
//
//   const app = new cdk.App();
//   const accountId = app.node.tryGetContext('accountId') ?? '222233334444';
//
//   new BoundaryStack(app, 'DeveloperBoundary', {
//     env: { account: accountId, region: 'us-east-1' },
//     accountId,
//   });
//
// -----------------------------------------------------------------------------
// THE PROOF (prove.sh) — run AFTER cdk deploy + the AttachCommand output
// -----------------------------------------------------------------------------
//
//   #!/usr/bin/env bash
//   set -euo pipefail
//   ROLE_ARN="arn:aws:iam::222233334444:role/CrossAccountDeveloper"
//   PROFILE="dev"
//
//   # 1. Put an over-privileged inline policy on the bounded role. The PUT
//   #    succeeds — the boundary acts at EVALUATION time, not at put time.
//   aws iam put-role-policy \
//     --role-name CrossAccountDeveloper \
//     --policy-name make-me-admin \
//     --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"*","Resource":"*"}]}' \
//     --profile "$PROFILE"
//
//   # 2. Ask the engine what the role can ACTUALLY do. The boundary's denies win.
//   aws iam simulate-principal-policy \
//     --policy-source-arn "$ROLE_ARN" \
//     --action-names iam:CreateUser s3:GetObject kms:ScheduleKeyDeletion \
//     --resource-arns '*' \
//     --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' \
//     --output table \
//     --profile "$PROFILE"
//
//   # Expected:
//   #   iam:CreateUser           explicitDeny   <- boundary Statement 2
//   #   kms:ScheduleKeyDeletion  explicitDeny   <- boundary Statement 3
//   #   s3:GetObject             allowed        <- ceiling + inline * both allow
//
//   # 3. Clean up the over-privileged inline policy (do not leave it behind).
//   aws iam delete-role-policy \
//     --role-name CrossAccountDeveloper \
//     --policy-name make-me-admin \
//     --profile "$PROFILE"
//
// -----------------------------------------------------------------------------
// HINTS (don't peek until you've tried for 15 minutes)
// -----------------------------------------------------------------------------
//
//   - If simulate-principal-policy returns `allowed` for iam:CreateUser, the
//     boundary is NOT attached. Re-run the AttachCommand output and confirm with
//     `aws iam get-role --role-name CrossAccountDeveloper --query
//     'Role.PermissionsBoundary'`.
//   - If s3:GetObject is denied, your ceiling is missing s3:* OR the inline
//     policy did not attach — check `aws iam list-role-policies`.
//   - simulate-principal-policy evaluates the LIVE role including its boundary,
//     which is why it is the highest-fidelity offline test. Wire it into CI as a
//     regression test for your security posture.
