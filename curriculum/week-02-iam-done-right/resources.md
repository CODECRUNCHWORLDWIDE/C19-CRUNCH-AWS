# Week 2 — Resources

Every resource on this page is **free**. The AWS documentation is free without an account. The open-source tools (Parliament, Cloudsplaining, the IAM policy validators, PMapper) are MIT/Apache-licensed and public on GitHub. The re:Invent and re:Inforce talks are free on YouTube with no account. No paywalled material is linked.

IAM is a *reading* discipline. The single highest-leverage thing you can do this week is read the policy-evaluation-logic reference until you can redraw the flowchart from memory. Everything else is application of that one document.

## Required reading (work it into your week)

- **IAM — Policy evaluation logic** (the flowchart; read it twice, redraw it once):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html>
- **IAM — Policies and permissions** (the field-by-field reference for the policy document):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html>
- **IAM — Identity-based vs resource-based policies**:
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_identity-vs-resource.html>
- **IAM — Permissions boundaries for IAM entities** (the delegation primitive — the most important page this week):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html>
- **IAM — Global condition context keys** (`aws:PrincipalOrgID`, `aws:SourceIp`, `aws:RequestedRegion`, `aws:SourceArn`, `aws:SourceAccount`, and the rest):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html>
- **IAM — How to use trust policies with IAM roles**:
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_terms-and-concepts.html>
- **The confused deputy problem** (the cross-account/cross-service gap and the `aws:SourceArn`/`externalId` fixes):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html>
- **STS — `AssumeRole` API reference** (session policies, duration, the chaining cap):
  <https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html>
- **IAM Access Analyzer — what it is** (external access, unused access, policy validation, policy generation):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html>
- **IAM Identity Center — getting started** (the human-access layer that replaces IAM users):
  <https://docs.aws.amazon.com/singlesignon/latest/userguide/getting-started.html>

## Authoritative deep dives

- **AWS — "IAM policy evaluation in detail"** (the official long-form walk through cross-account, boundaries, and session policies, with worked examples):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic-cross-account.html>
- **AWS Security Blog — "How to use permissions boundaries to delegate IAM"** (the canonical delegation pattern, the same one Lecture 2 builds):
  <https://aws.amazon.com/blogs/security/delegate-permission-management-to-developers-using-iam-permissions-boundaries/>
- **AWS Security Blog — "When and where to use IAM permissions boundaries"**:
  <https://aws.amazon.com/blogs/security/when-and-where-to-use-iam-permissions-boundaries/>
- **AWS Security Blog — "IAM makes it easier to apply the principle of least privilege with Access Analyzer policy generation"**:
  <https://aws.amazon.com/blogs/security/iam-access-analyzer-makes-it-easier-to-implement-least-privilege-permissions-by-generating-iam-policies-based-on-access-activity/>
- **AWS Security Blog — "How to prevent the confused deputy problem with `aws:SourceArn`"**:
  <https://aws.amazon.com/blogs/security/iam-role-trust-policy-best-practices/>
- **AWS — "Security best practices in IAM"** (the official least-privilege checklist; map your work against it):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html>
- **AWS — "IAM Access Analyzer custom policy checks"** (the `check-no-new-access` and `check-access-not-granted` CLI commands you can run in CI):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-custom-policy-checks.html>

## GitHub Actions OIDC into AWS (used heavily from Week 7 on, introduced here)

- **AWS — "Configuring OpenID Connect in Amazon Web Services"** (GitHub's own guide to the keyless `sts:AssumeRoleWithWebIdentity` pattern):
  <https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services>
- **AWS Security Blog — "Use IAM roles to connect GitHub Actions to actions in AWS"**:
  <https://aws.amazon.com/blogs/security/use-iam-roles-to-connect-github-actions-to-actions-in-aws/>
- **`aws-actions/configure-aws-credentials`** (the action; read the README's OIDC section and the `sub` claim condition trap):
  <https://github.com/aws-actions/configure-aws-credentials>

## CDK / IaC references

- **AWS CDK — `aws-cdk-lib/aws-iam` module reference** (`Role`, `PolicyStatement`, `Grant`, `PermissionsBoundary`, `ManagedPolicy`):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam-readme.html>
- **AWS CDK — "Permissions and the principle of least privilege"** (how `grant*` methods generate scoped policies):
  <https://docs.aws.amazon.com/cdk/v2/guide/permissions.html>
- **AWS CDK — Bootstrapping** (the three-role deploy model you will recognize from Lecture 2; full coverage is Week 3):
  <https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html>
- **OpenTofu / Terraform AWS provider — `aws_iam_policy_document` data source** (the idiomatic way to author policy JSON in HCL):
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document>
- **OpenTofu / Terraform AWS provider — `aws_iam_role`, `aws_iam_role_policy`, `aws_iam_role_policy_attachment`**:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role>
- **AWS — `cfn-policy-validator`** (validate IAM in CloudFormation/CDK output against Access Analyzer before deploy):
  <https://github.com/awslabs/aws-cloudformation-template-flip>

## Open-source tooling worth installing

- **Parliament** (Duo Security) — an IAM policy linter. Catches malformed ARNs, mismatched action/resource pairs, and missing conditions. Run it over everything you author this week:
  <https://github.com/duo-labs/parliament>
- **Cloudsplaining** (Salesforce/`salesforce/cloudsplaining`) — scans an account's IAM and reports privilege-escalation paths, resource-exposure, and credential-exposure risks. Run it once at the end of the mini-project:
  <https://github.com/salesforce/cloudsplaining>
- **PMapper (Principal Mapper)** (NCC Group) — builds a graph of your account's principals and computes who can escalate to whom. The definitive tool for "can this role become admin?" questions:
  <https://github.com/nccgroup/PMapper>
- **policy_sentry** (Salesforce) — generates least-privilege IAM policies from a CRUD-level description, so you never hand-write `Resource` ARNs again:
  <https://github.com/salesforce/policy_sentry>
- **`iam-policy-validator-for-terraform`** (awslabs) — runs Access Analyzer checks against a Terraform/OpenTofu plan in CI:
  <https://github.com/awslabs/terraform-iam-policy-validator>

## Official docs you will return to

- **IAM — Actions, resources, and condition keys for AWS services** (the SAR — the per-service table of every action, the resource types it acts on, and the conditions it supports. Bookmark this; you will open it constantly):
  <https://docs.aws.amazon.com/service-authorization/latest/reference/reference.html>
- **IAM — Policy variables** (`${aws:username}`, `${aws:PrincipalTag/team}`, and friends):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_variables.html>
- **IAM — `NotPrincipal`, `NotAction`, `NotResource`** (the three traps; read the warnings):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_notaction.html>
- **IAM — Service-linked roles**:
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/using-service-linked-roles.html>
- **STS — Managing AWS STS in a Region** (the regional-endpoint detail that bites cross-region AssumeRole):
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_enable-regions.html>
- **`aws iam simulate-principal-policy` CLI reference** (the policy-simulator API you script the boundary test against):
  <https://docs.aws.amazon.com/cli/latest/reference/iam/simulate-principal-policy.html>

## Talks worth watching (all free, no account)

- **AWS re:Inforce — "A least-privilege journey: AWS IAM policies and permissions"** — the canonical session on tightening policies with Access Analyzer; search YouTube for "re:Inforce least privilege IAM policies".
- **AWS re:Invent — "IAM policy evaluation deep dive"** (Brigid Johnson's series of these is the single best on-ramp to the evaluation engine; her "Become an IAM Policy Master in 60 Minutes or Less" is the classic) — search YouTube for "Brigid Johnson IAM policy master".
- **AWS re:Inforce — "Permission boundaries and delegated administration"** — search YouTube for "AWS permissions boundaries delegate".
- **AWS re:Inforce — "Provable security: automated reasoning at AWS"** — the formal-methods foundation under Access Analyzer; search YouTube for "AWS provable security automated reasoning".
- **AWS re:Invent — "Choosing the right mix of AWS IAM policies for scale"** — when to use SCPs vs boundaries vs identity policies; search YouTube for "AWS IAM policies for scale".

## How to use this resource list

The lectures cite specific URLs from this page at decision points. The links you should read end-to-end *this week*, in order, are:

1. **IAM — Policy evaluation logic** (Required reading). Read it twice. Redraw the flowchart. This is the spine of the whole week.
2. **IAM — Permissions boundaries for IAM entities** (Required reading). The delegation primitive Lecture 2 builds.
3. **The confused deputy problem** (Required reading). Decisive for the challenge and one homework problem.
4. **AWS Security Blog — "How to use permissions boundaries to delegate IAM"** (Deep dives). The exact pattern Exercise 2 implements.

The rest are reference material. The **Service Authorization Reference** (the per-service action/resource/condition table) and the **global condition context keys** page are the two you will keep open in a browser tab all week — treat them like the index of a manual, not a document to read front to back.

---

*Bookmarks decay. If a link rots, search the title — the AWS docs reorganize their URLs roughly yearly, but the page titles are stable and the security blog posts stay up.*
