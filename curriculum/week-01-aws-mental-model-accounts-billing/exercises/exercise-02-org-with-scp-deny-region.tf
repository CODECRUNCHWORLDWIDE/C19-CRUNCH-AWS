# Exercise 2 — An Organization with three OUs and an SCP that denies us-east-1
#
# Goal: Use OpenTofu to (1) create an AWS Organization with ALL features,
#       (2) create dev / stage / prod OUs, (3) author an SCP that denies
#       us-east-1, and (4) attach it to the dev OU. Then PROVE the deny by
#       attempting a blocked action and reading the explicit-deny error.
#
# Estimated time: 75 minutes.
#
# Cost: $0. Organizations, OUs, and SCPs are free.
#
# ---------------------------------------------------------------------------
# HOW TO USE THIS FILE
# ---------------------------------------------------------------------------
#
# 1. Install OpenTofu (`brew install opentofu`) and verify: `tofu version`.
#
# 2. Authenticate as an ADMIN principal in your MANAGEMENT account (the one
#    from Exercise 1). The simplest path is IAM Identity Center:
#
#        aws sso login --profile mgmt-admin
#        export AWS_PROFILE=mgmt-admin
#        aws sts get-caller-identity        # confirm: this is the mgmt account
#
# 3. Put this file in an empty directory as `main.tf`, then:
#
#        tofu init
#        tofu plan
#        tofu apply
#
#    NOTE: If your account already created an Organization in Exercise 1's
#    stretch (or via the console), import it instead of creating a duplicate:
#
#        tofu import aws_organizations_organization.this <org-id>
#
#    You cannot have two Organizations in one account; the apply will error if
#    one already exists and is not imported.
#
# 4. After apply, run the PROOF commands at the bottom of this file.
#
# ---------------------------------------------------------------------------
# ACCEPTANCE CRITERIA
# ---------------------------------------------------------------------------
#
#   [ ] `tofu apply` succeeds and creates the org (FeatureSet = ALL).
#   [ ] Three OUs exist: dev, stage, prod.
#   [ ] An SCP named "deny-us-east-1" is attached to the dev OU.
#   [ ] You attempted a us-east-1 action from a dev-OU principal and read
#       "explicit deny in a service control policy" in the error.
#   [ ] You can explain why the SCP does NOT block CloudFront/IAM (the carve-out).
#
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.6.0" # OpenTofu 1.6+ / Terraform 1.6+

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

provider "aws" {
  # Region here is just the API endpoint the provider talks to; Organizations
  # is a global service. Pick the Region you actually work in.
  region = "eu-west-1"
}

# ---------------------------------------------------------------------------
# 1. The Organization (ALL features — required for SCPs)
# ---------------------------------------------------------------------------

resource "aws_organizations_organization" "this" {
  feature_set = "ALL"

  # Enabling SCP policy type so we can attach guardrails.
  enabled_policy_types = ["SERVICE_CONTROL_POLICY"]

  # Service-linked roles AWS needs to operate org-integrated services later.
  aws_service_access_principals = [
    "cloudtrail.amazonaws.com",
    "config.amazonaws.com",
    "sso.amazonaws.com",
  ]
}

# ---------------------------------------------------------------------------
# 2. The OUs: dev / stage / prod, directly under the org root
# ---------------------------------------------------------------------------

locals {
  ou_names = ["dev", "stage", "prod"]
}

resource "aws_organizations_organizational_unit" "envs" {
  for_each = toset(local.ou_names)

  name      = each.value
  parent_id = aws_organizations_organization.this.roots[0].id
}

# ---------------------------------------------------------------------------
# 3. The SCP: deny everything in us-east-1, EXCEPT genuinely-global services
#    whose control plane lives there. The NotAction carve-out is the lesson:
#    a blanket us-east-1 deny breaks CloudFront/IAM/Route53/Organizations.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "deny_us_east_1" {
  statement {
    sid    = "DenyUsEast1ExceptGlobal"
    effect = "Deny"

    # NotActions: this Deny applies to every action EXCEPT these global ones.
    not_actions = [
      "cloudfront:*",
      "iam:*",
      "route53:*",
      "organizations:*",
      "support:*",
      "waf:*",
      "wafv2:*",
      "globalaccelerator:*",
      "sts:*",
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = ["us-east-1"]
    }
  }
}

resource "aws_organizations_policy" "deny_us_east_1" {
  name        = "deny-us-east-1"
  description = "Guardrail: block all non-global actions in us-east-1."
  type        = "SERVICE_CONTROL_POLICY"
  content     = data.aws_iam_policy_document.deny_us_east_1.json
}

# Attach the guardrail to the dev OU only (so you can compare dev vs stage/prod).
resource "aws_organizations_policy_attachment" "deny_us_east_1_dev" {
  policy_id = aws_organizations_policy.deny_us_east_1.id
  target_id = aws_organizations_organizational_unit.envs["dev"].id
}

# ---------------------------------------------------------------------------
# 4. Outputs — the ids you need for the proof step and for later weeks
# ---------------------------------------------------------------------------

output "organization_id" {
  value       = aws_organizations_organization.this.id
  description = "The Organization id (o-xxxxxxxxxx)."
}

output "management_account_id" {
  value       = aws_organizations_organization.this.master_account_id
  description = "The management account id."
}

output "ou_ids" {
  value = {
    for name, ou in aws_organizations_organizational_unit.envs : name => ou.id
  }
  description = "Map of OU name -> OU id (ou-xxxx-xxxxxxxx)."
}

output "scp_id" {
  value       = aws_organizations_policy.deny_us_east_1.id
  description = "The SCP id; attached to the dev OU."
}

# ---------------------------------------------------------------------------
# PROVE THE DENY  (run these AFTER `tofu apply`)
# ---------------------------------------------------------------------------
#
# The SCP is attached to the DEV OU. To feel its effect you must be a principal
# in an account UNDER the dev OU. If you have already vended a dev member
# account and can assume a role into it, run from there. If you are still
# operating from the management account, note that SCPs do NOT apply to the
# management account at all -- that is by design, and is itself worth knowing.
#
# From a principal in a dev-OU MEMBER account:
#
#     # This should be BLOCKED by the SCP:
#     aws ec2 describe-instances --region us-east-1
#
#   Expected (the string that proves the guardrail fired):
#
#     An error occurred (UnauthorizedOperation) when calling the
#     DescribeInstances operation: You are not authorized to perform this
#     operation ... with an explicit deny in a service control policy
#
#     # This should SUCCEED (different Region, not denied):
#     aws ec2 describe-instances --region eu-west-1
#
#     # This should SUCCEED even in us-east-1, because IAM is carved out:
#     aws iam list-account-aliases --region us-east-1
#
# If the EC2 call in us-east-1 is NOT denied, check: (a) the principal is in a
# member account under the dev OU, not the mgmt account; (b) the attachment
# applied; (c) you waited a few seconds for SCP propagation.
#
# ---------------------------------------------------------------------------
# CLEAN UP
# ---------------------------------------------------------------------------
#
#   tofu destroy
#
# This detaches the SCP, deletes the OUs and the policy. It will REFUSE to
# delete the Organization if member accounts still exist under it -- move or
# close those first. For the lab, destroying just the OUs + SCP is fine; you
# will keep the Organization for the mini-project and every later week.
#
# ---------------------------------------------------------------------------
# HINTS (read only if stuck >15 min)
# ---------------------------------------------------------------------------
#
# - "Organization already exists": import it.
#     tofu import aws_organizations_organization.this $(aws organizations \
#       describe-organization --query 'Organization.Id' --output text)
#
# - "AccessDenied creating organization": you are not in the account that owns
#   (or will own) the org, or your role lacks organizations:* . Re-check
#   `aws sts get-caller-identity` and your permission set.
#
# - SCPs require feature_set = "ALL". If an existing org is CONSOLIDATED_BILLING
#   only, enable all features in the console first; OpenTofu cannot flip it.
#
# - The SCP does nothing to the management account by design. To see the deny
#   you need a principal in a member account under the dev OU. If you have no
#   member account yet, the mini-project vends one; you can also create one
#   with aws_organizations_account and assume the OrganizationAccountAccessRole.
#
# ---------------------------------------------------------------------------
