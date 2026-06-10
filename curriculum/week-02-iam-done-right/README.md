# Week 2 — IAM Done Right

Welcome to **C19 · Crunch AWS**, Week 2. Week 1 gave you the mental model, an Organization with three OUs, an SCP you proved by getting denied, and a billing alert that emails you before the invoice does. This week we do the single most important thing in the entire course: we learn IAM the way a production shop actually uses it. Not "I copy-pasted a policy from a Stack Overflow answer and it worked." Not "I attached `AdministratorAccess` because the deploy kept failing." We learn to read a policy out loud, predict exactly what it allows and denies before we ever run it, find the bug a junior engineer left in it, and delegate permissions to other humans and other roles *without* handing them the keys to the whole account.

If you take nothing else from C19, take this week. Every breach postmortem you will ever read — Capital One, the endless S3-bucket-left-public stories, the confused-deputy cross-account data exfiltration writeups — comes back to an IAM mistake that someone could have caught by reading the policy out loud. AWS gives you a deny-by-default, explicit-deny-wins evaluation engine that is genuinely sound. The failures are never the engine. The failures are humans writing `"Resource": "*"` because it made the error go away, humans forgetting the `aws:PrincipalOrgID` condition on a resource policy, humans granting `iam:PassRole` on `*` and never thinking about it again. By Friday you will be the person on the team who catches those in review.

The first thing to internalize is that **IAM is an evaluation engine, not a pile of JSON, and the engine has exactly one set of rules**. When a principal makes a request, AWS gathers every policy that could apply — identity-based policies on the principal, resource-based policies on the target, permission boundaries, session policies, and Service Control Policies from the Organization — and runs them through a fixed decision flow. An explicit `Deny` anywhere wins, always, no exceptions. Absent a `Deny`, the request needs an explicit `Allow` from the identity-based or resource-based policies, *and* it must survive every boundary that applies (SCP, permission boundary, session policy). Default is deny. If you can recite that flow from memory and apply it to a concrete request, you can debug 90% of "why is this `AccessDenied`" tickets without opening the console. Lecture 1 makes you fluent in the flow by walking through twelve real policies and finding the bug in each.

The second thing to internalize is that **roles are the unit of trust on AWS, and long-lived IAM users are a smell**. A role has two policies that matter: a *trust policy* (who is allowed to assume it — the `sts:AssumeRole` principal) and one or more *permission policies* (what the role can do once assumed). Humans authenticate once at IAM Identity Center and assume roles into accounts; CI assumes a role via GitHub OIDC with no stored credentials at all; one service assumes a role in another account to read a bucket. Almost nothing in a well-run 2026 AWS shop uses a long-lived `AKIA...` access key. Lecture 1 covers the principal types; Lecture 2 covers the AssumeRole chains and why your CDK deploy needs three of these roles, not one.

The third thing to internalize is that **permission boundaries are the only safe way to let one engineer grant permissions to another**. This is the subtle one, and it is the reason Week 2 exists. The naive way to let a developer create roles for their Lambda functions is to grant them `iam:CreateRole` and `iam:AttachRolePolicy`. The instant you do that, the developer can create a role with `AdministratorAccess` and assume it — they have just escalated to admin, and your least-privilege model is fiction. The fix is a permission boundary: a managed policy that sets the *maximum* permissions any role the developer creates can ever have, enforced by a condition (`iam:PermissionsBoundary`) on the developer's own `iam:CreateRole` permission. The developer can create roles all day; none of those roles can exceed the boundary. Lecture 2 builds this end-to-end and proves it blocks an over-privileged inline policy.

The fourth thing to internalize is that **you do not have to find IAM bugs by hand — IAM Access Analyzer finds them for you, and you should run it continuously**. Access Analyzer uses automated reasoning (the same provable-security tech behind AWS's formal-methods group) to tell you which of your resources are reachable from outside your account or Organization, to validate policies against a few hundred checks, and — the 2026 feature you will lean on hardest — to generate a least-privilege policy from your actual CloudTrail access history. The exercises run it across all three accounts and make you resolve every finding with a written explanation of what it meant.

This week is heavier on prose and lighter on volume of code than a typical week, by design. IAM is a *reading* skill before it is a *writing* skill. You will write CDK (TypeScript primary, with one Python stack and one OpenTofu module so you see the same model expressed three ways), you will run a lot of `aws` CLI, and you will read more policy JSON than you write. That is correct. The senior engineer's superpower here is not authoring — it is review.

## Learning objectives

By the end of this week, you will be able to:

- **Recite** the IAM policy evaluation flow from memory — gather all applicable policies, explicit `Deny` wins, then require an `Allow` that survives SCPs, permission boundaries, and session policies — and apply it to a concrete request to predict `Allow` or `Deny` before running it.
- **Distinguish** IAM users, groups, roles, identity-based policies, resource-based policies, permission boundaries, session policies, and SCPs, and state which one is the right tool for a given delegation problem.
- **Read** an IAM policy out loud, statement by statement, and identify the bug — over-broad `Resource`, missing condition key, `iam:PassRole` on `*`, a confused-deputy gap, a `NotAction` trap, a `Principal` wildcard on a resource policy — and explain *why* the evaluation engine makes that bug dangerous.
- **Write** least-privilege identity-based policies that scope `Resource` to ARNs and gate `Action` with condition keys (`aws:PrincipalOrgID`, `aws:SourceIp`, `aws:RequestedRegion`, `aws:SourceArn`, `aws:ResourceTag/*`).
- **Author** a permission boundary that caps what a delegated role can do, and enforce it with the `iam:PermissionsBoundary` condition on the delegator's `iam:CreateRole`/`iam:PutRolePolicy` actions, then prove it blocks an over-privileged inline policy.
- **Build** a three-account topology (`identity`, `dev`, `prod`) with IAM Identity Center, a single permission set, and human users who assume roles into `dev` and `prod` — in CDK and CLI.
- **Configure** `sts:AssumeRole` chains and cross-account trust, including the external-ID pattern for third parties and the `aws:SourceArn`/`aws:SourceAccount` pattern that closes the confused-deputy hole on service-linked trust.
- **Run** IAM Access Analyzer (external-access *and* unused-access analyzers) across multiple accounts, triage every finding, archive the intended ones with a written justification, and remediate the rest.
- **Express** the same IAM constructs three ways — CDK TypeScript, CDK Python, and OpenTofu — and explain what each tool does and does not check for you at synth/plan time.

## Prerequisites

- **Week 1 of C19 complete.** You have an AWS Organization with `dev`, `stage`, `prod` OUs (we will add an `identity` account this week), at least one SCP you have proven, MFA on root, and a working `~/.aws/config` with named profiles and `aws sso login`. If your Week 1 Organization is not standing, stand it before Tuesday — this week builds directly on it.
- **CLI fluency from Week 1.** You can run `aws sts get-caller-identity`, switch profiles with `--profile`, and read JSON output without flinching. We add `aws sts assume-role`, `aws iam simulate-principal-policy`, and `aws accessanalyzer` this week.
- **Node 20+ and Python 3.12+ on PATH**, plus the AWS CDK v2 CLI (`npm i -g aws-cdk`, target `aws-cdk-lib` 2.160.0 or later) and OpenTofu 1.8+ (`tofu version`). We do not deploy compute this week, so the bill is near zero; IAM, Identity Center, and Access Analyzer are all free.
- **Three account IDs you control or can create within your Organization.** If you are on a single learner account, the exercises include a single-account fallback that uses IAM roles within one account to simulate the cross-account trust — you lose the Organization-boundary behaviors (`aws:PrincipalOrgID` enforcement, true cross-account isolation) but keep everything else.
- **A text editor with JSON folding.** You will read a lot of policy JSON. Being able to collapse a `Statement` array to scan the `Sid`s is worth more than it sounds.

## Topics covered

- **The principals.** IAM users vs groups vs roles. Why long-lived users are a 2026 smell, when they are still unavoidable (a few legacy break-glass cases), and how roles plus IAM Identity Center replace them for everything else. Trust policies vs permission policies on a role.
- **The policy document.** `Version`, `Statement`, `Sid`, `Effect`, `Action`/`NotAction`, `Resource`/`NotResource`, `Principal`/`NotPrincipal`, `Condition`. What each field means, and the three of them (`NotAction`, `NotPrincipal`, `NotResource`) that are traps in 90% of uses.
- **Policy evaluation logic.** The full decision flow: explicit `Deny` wins; then within an account an `Allow` from *either* identity-based or resource-based policy suffices; across accounts you need an `Allow` on *both* sides; then SCPs, permission boundaries, and session policies each independently cap the result.
- **Identity-based vs resource-based policies.** Where each lives, when you need both, the cross-account "both sides must allow" rule, and the small set of services with resource policies you will actually touch (S3, KMS, SQS, SNS, Lambda, ECR, Secrets Manager, the resource-based variants of IAM role trust).
- **Condition keys.** Global keys (`aws:PrincipalOrgID`, `aws:SourceIp`, `aws:RequestedRegion`, `aws:SourceArn`, `aws:SourceAccount`, `aws:PrincipalTag/*`, `aws:ResourceTag/*`, `aws:SecureTransport`, `aws:MultiFactorAuthPresent`) and service-specific keys. Condition operators (`StringEquals`, `StringLike`, `ArnLike`, `IpAddress`, `Bool`, `Null`) and the `...IfExists` and set-operator (`ForAllValues`/`ForAnyValue`) modifiers.
- **Permission boundaries.** What they cap, what they do *not* cap (they never grant), the `iam:PermissionsBoundary` condition that makes delegation safe, and the three-role CDK-deploy story.
- **`sts:AssumeRole` and chains.** Role chaining, the one-hour chained-session cap, `aws:assumed-role` ARNs, session names for CloudTrail attribution, `sts:AssumeRoleWithWebIdentity` for OIDC (GitHub Actions), and session policies passed inline at assume time.
- **Cross-account trust and the confused deputy.** The external-ID pattern for third-party SaaS, the `aws:SourceArn`/`aws:SourceAccount` pattern for service-linked trust, and why `"Principal": {"AWS": "*"}` on a trust policy with only an external-ID is still wrong.
- **Service-linked roles.** What they are, why you do not author their trust policies, and the `iam:CreateServiceLinkedRole` permission that several services need.
- **IAM Access Analyzer.** External-access analyzers (what is reachable from outside your zone of trust), unused-access analyzers (roles, users, and permissions nobody has used in N days), policy validation, and policy generation from CloudTrail history.
- **IAM as code, three ways.** CDK TS (`aws-iam` L2 constructs, `Grant` objects, `PolicyStatement`), CDK Python (the same model in another language), and OpenTofu (`aws_iam_policy_document` data sources and the `aws_iam_role` resource). What each checks at synth/plan and what only fails at deploy.

## Weekly schedule

The schedule adds up to approximately **36 hours**. Treat it as a target, not a contract. The reading blocks this week are real work — IAM is learned by reading policies, so the "read" column is heavier than usual.

| Day       | Focus                                                       | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-------------------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Evaluation logic; read 12 policies out loud (Lecture 1)     |    3h    |    1h     |     0h     |    1h     |   0.5h   |     0h       |    0.5h    |     6h      |
| Tuesday   | Principals, trust, AssumeRole chains, boundaries (Lecture 2)|    3h    |    1.5h   |     0h     |    0.5h   |   0.5h   |     0h       |    0.5h    |     6h      |
| Wednesday | Exercise 1 — three-account topology + Identity Center       |    0h    |    3h     |     0h     |    0.5h   |   1h     |     1h       |    0.5h    |     6h      |
| Thursday  | Exercise 2 — permission boundary; Exercise 3 — Access Analyzer |  0h    |    3h     |     0h     |    0.5h   |   1h     |     1h       |    0.5h    |     6h      |
| Friday    | Challenge — find the bug in 12 seeded policies               |   0h    |    0h     |     3.5h   |    0.5h   |   1h     |     0.5h     |    0.5h    |     6h      |
| Saturday  | Mini-project deep work — identity layer end-to-end          |    0h    |    0h     |     0h     |    0h     |   0h     |     5h       |    0h      |     5h      |
| Sunday    | Quiz, peer IAM review, engineering journal                  |    0h    |    0h     |     0h     |    1h     |   0h     |     0h       |    0h      |     1h      |
| **Total** |                                                             | **9h**   | **9h**    | **6.5h**   | **4.5h**  | **4h**   | **8.5h**     | **3h**     | **36h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | The AWS IAM docs that are actually worth reading, the policy-evaluation reference, Access Analyzer docs, the re:Inforce IAM talks, and the two open-source tools (Parliament, IAM Access Analyzer's CLI) we use |
| [lecture-notes/01-read-this-policy-out-loud.md](./lecture-notes/01-read-this-policy-out-loud.md) | The evaluation engine end-to-end, then twelve real-world policies with the bug found and explained in each |
| [lecture-notes/02-permission-boundaries-and-three-roles.md](./lecture-notes/02-permission-boundaries-and-three-roles.md) | Permission boundaries as the only safe delegation, AssumeRole chains, cross-account trust, and why your CDK deploy needs three roles |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-three-account-identity-center.md](./exercises/exercise-01-three-account-identity-center.md) | Build the `identity`/`dev`/`prod` topology, stand up Identity Center with a single permission set, and assume roles into `dev` and `prod` |
| [exercises/exercise-02-permission-boundary.ts](./exercises/exercise-02-permission-boundary.ts) | A CDK TypeScript stack that defines a developer permission boundary and a developer role bound by it, plus a test that proves an over-privileged inline policy is blocked |
| [exercises/exercise-03-access-analyzer.py](./exercises/exercise-03-access-analyzer.py) | A Python (boto3) script that enables external-access and unused-access analyzers, lists findings, and prints a triage report |
| [challenges/README.md](./challenges/README.md) | Index of the challenge |
| [challenges/challenge-01-twelve-broken-policies.md](./challenges/challenge-01-twelve-broken-policies.md) | Twelve seeded policies; find and fix the flaw in each and explain the evaluation logic that makes it dangerous |
| [mini-project/README.md](./mini-project/README.md) | "The Identity Layer" — deliver a working three-account identity foundation reused directly in the capstone |
| [quiz.md](./quiz.md) | 14 questions on evaluation logic, boundaries, trust, conditions, and Access Analyzer |
| [homework.md](./homework.md) | Six practice problems for the week |

## The "read it out loud" promise

Week 1 gave you the `aws sts get-caller-identity` reflex — always know who you are before you act. Week 2 adds a second reflex: **before you attach a policy, read it out loud, statement by statement, in plain English, and say what it allows and what it denies.** "Statement one: allow `s3:GetObject` on any object in the `app-data` bucket, but only if the request comes from inside our Organization. Statement two: deny all `kms:ScheduleKeyDeletion` everywhere, no condition." If you cannot say that sentence about every statement in a policy, you do not understand the policy, and you must not attach it. This is the habit the lecture drills, the challenge tests, and the peer review on Sunday grades.

We add a second contract: **every `"Resource": "*"` and every `"Principal": {"AWS": "*"}` in anything you submit this week must carry a one-line comment justifying it, or it is a finding.** Wildcards are not banned — a few actions genuinely require `Resource: "*"` because they have no resource (`sts:GetCallerIdentity`, `iam:ListRoles`, some `ec2:Describe*`). But an unjustified wildcard is the single most common real-world IAM bug, and this week you stop shipping them by reflex.

## A note on what's not here

Week 2 is deep on identity but deliberately does **not** cover:

- **KMS key policies in depth.** A KMS key has a resource policy (the key policy) and you will read one this week, but the full KMS model — grants, multi-region keys, envelope encryption, the key-policy-vs-IAM interaction — is Week 13 (the security stack). We touch KMS only as one more resource policy to read.
- **Cognito and end-user identity.** Identity Center is for *humans on your team*. Cognito user pools are for *your application's end users*. They are different products solving different problems. Cognito lands in the compute and capstone weeks.
- **CDK pipelines and `cdk bootstrap` internals.** The chicken-and-egg IAM problem of bootstrapping CDK (the bootstrap stack creates the very roles CDK assumes to deploy) is Week 3 material. This week we use roles we author by hand so the trust is fully visible; Week 3 shows you the managed version.
- **GuardDuty, Security Hub, Macie, Inspector.** The detective security stack is Week 13. Access Analyzer is the one detective tool we pull forward, because it is pure IAM reasoning and it belongs with the IAM week.
- **ABAC at scale.** We use tag-based conditions (`aws:PrincipalTag`, `aws:ResourceTag`) this week as a tool, but full attribute-based access control as an organizing principle — the "tag everything and grant on tags" design — is a stretch goal here and a recurring theme later.

## Stretch goals

If you finish the regular work early and want to push further:

- Install **Parliament** (`pip install parliament`), the open-source IAM policy linter from Duo Security, and run it over every policy you wrote this week. Reconcile its findings with Access Analyzer's policy validation — they overlap but each catches things the other misses: <https://github.com/duo-labs/parliament>.
- Read the **AWS IAM policy evaluation logic** reference end-to-end, including the flowchart, and redraw the flowchart from memory: <https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html>.
- Use **`aws iam simulate-principal-policy`** to script a test harness that asserts your developer role *can* do the things it should and *cannot* do the things the boundary forbids, then wire it into a CI check.
- Turn on **Access Analyzer unused-access analysis** with a 90-day window across the Organization and write the cleanup PR that removes the dead roles it finds.
- Read the **`aws-samples/iam-policy-validator-for-terraform`** and **`cfn-policy-validator`** tools and run one of them against your Week 3 CDK output to catch IAM findings *before* deploy: <https://github.com/awslabs/aws-cloudformation-templates>.

## Up next

Continue to **Week 3 — CDK, CloudFormation & Local Tooling** once you have shipped this week's mini-project with a clean Access Analyzer report. Week 3 takes the IAM you now understand by hand and shows you how CDK bootstrap creates and assumes the three roles you built manually here — the deploy role, the file-publishing role, and the CloudFormation execution role. The "three roles for one deploy" idea from Lecture 2 is exactly what `cdk bootstrap` provisions, and you will recognize every trust policy it generates because you will have written the same ones yourself this week.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
