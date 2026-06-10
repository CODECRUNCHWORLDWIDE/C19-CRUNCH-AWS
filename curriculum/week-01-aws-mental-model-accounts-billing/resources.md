# Week 1 — Resources

Every resource on this page is **free**. The AWS documentation is free without an account. The whitepapers are public PDFs. The re:Invent talks are on YouTube. No paywalled books are linked — where a book is genuinely worth buying we say so and tell you which chapters matter.

All links checked current to **2026**. If one 404s, open an issue so we can replace it.

## Required reading (work it into your week)

- **AWS Organizations User Guide — terminology & concepts** — the canonical model of management account, member accounts, OUs, and SCPs:
  <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_getting-started_concepts.html>
- **Service Control Policies (SCPs)** — what they do, what they do *not* do (they never grant), and how evaluation works:
  <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html>
- **Root user best practices** — the lockdown checklist this week's Exercise 1 implements:
  <https://docs.aws.amazon.com/IAM/latest/UserGuide/root-user-best-practices.html>
- **AWS Free Tier** — the three kinds (12-month, always-free, trials) and how to track usage:
  <https://aws.amazon.com/free/>
- **AWS Budgets** — budget types, alert thresholds, and notifications:
  <https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html>
- **The Cost & Usage Report via Data Exports (CUR 2.0)** — the modern way to ship the CUR to S3:
  <https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html>

## The whitepapers (skim, don't memorize)

You will not read these cover to cover this week, but the first time a reviewer says "which line of the shared responsibility model is that?" you want the diagram in your head.

- **Shared Responsibility Model** — the "of the cloud / in the cloud" split, with the per-service nuance:
  <https://aws.amazon.com/compliance/shared-responsibility-model/>
- **AWS Well-Architected Framework** — six pillars; this week touches **Security** and **Cost Optimization**:
  <https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html>
- **Organizing Your AWS Environment Using Multiple Accounts** — the multi-account whitepaper your mini-project is a miniature of:
  <https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/organizing-your-aws-environment.html>
- **AWS Global Infrastructure** — the live map of Regions, AZs, and edge locations:
  <https://aws.amazon.com/about-aws/global-infrastructure/>

## Official AWS docs you will open this week

- **AWS CLI v2 User Guide**: <https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html>
- **Configuring the CLI to use IAM Identity Center (`aws configure sso`)**:
  <https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html>
- **Named profiles (`~/.aws/config`)**:
  <https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html>
- **AWS CloudShell** — a browser shell with credentials already wired:
  <https://docs.aws.amazon.com/cloudshell/latest/userguide/welcome.html>
- **Cost Explorer**: <https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html>
- **Athena — query CUR data, and partition projection**:
  <https://docs.aws.amazon.com/athena/latest/ug/partition-projection.html>
- **Regions and Availability Zones**:
  <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html>

## Infrastructure-as-code references (TS/Python/OpenTofu)

This week's exercises use three tools. You only need to be fluent in one by Friday; we show all three so you can see the same control expressed differently.

- **AWS CDK v2 — Developer Guide**: <https://docs.aws.amazon.com/cdk/v2/guide/home.html>
- **AWS CDK API Reference (`aws-cdk-lib`)** — look up `aws_budgets`, `aws_organizations` (L1), `aws_s3`:
  <https://docs.aws.amazon.com/cdk/api/v2/>
- **OpenTofu documentation** — the open-source Terraform fork we default to:
  <https://opentofu.org/docs/>
- **Terraform AWS provider — `aws_organizations_organization`, `_organizational_unit`, `_policy`**:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/organizations_organization>
- **CloudFormation — `AWS::Organizations::*` resource types**:
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/AWS_Organizations.html>

## Talks (free, on YouTube, no signup)

- **"AWS re:Invent — Best practices for organizing and operating multi-account environments"** — the org-design talk; search the AWS Events channel for the latest year's version:
  <https://www.youtube.com/@AWSEventsChannel>
- **"AWS re:Invent — A close look at AWS Free Tier and cost management"** — how to not get a surprise bill.
- **"AWS Well-Architected — the Cost Optimization pillar, in 30 minutes"** — the FinOps mindset compressed.

> Link rot is real on conference talks. If a specific URL dies, search the talk title on the **AWS Events** YouTube channel — they repost each year's version with a new code.

## Books (buy only if you want them; chapters that matter)

- **"AWS for Solutions Architects" (Packt)** — chapters on the global infrastructure and account structure are a solid second pass on this week's material.
- **"Cloud FinOps" (O'Reilly, Storment & Fuller)** — the canonical FinOps book. Chapters 1–4 are the mindset behind why we configure Budgets and the CUR in Week 1 rather than Week 14.
- **"The Good Parts of AWS" (Daniel Vassallo)** — short, opinionated, free-ish. Reinforces the "use a small number of services well" thesis this week opens with.

## Tools you'll use this week

- **AWS CLI v2** — install per the docs (`brew install awscli`, the macOS `.pkg`, or the Linux bundle). Verify with `aws --version` (expect `aws-cli/2.x`). v1 is end-of-life; do not use it.
  <https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html>
- **OpenTofu** — `brew install opentofu`, or the official installer. Verify with `tofu version`.
  <https://opentofu.org/docs/intro/install/>
- **Node.js 20+ and the AWS CDK** — `npm install -g aws-cdk`. Verify with `cdk --version` (expect `2.x`).
- **`jq`** — JSON on the command line. `brew install jq`. You will pipe CLI output through it constantly.
- **`session-manager-plugin`** (optional this week, needed later) — for `aws ssm start-session`.
- **AWS CloudShell** — zero-install fallback in the browser, with your console credentials pre-wired. Use it when your laptop CLI is misbehaving.

## Open repositories to read this week

You learn the org-and-billing patterns faster from one good reference implementation than from three tutorials.

- **`aws-samples/aws-organizations-baseline`** — reference Organization scaffolds:
  <https://github.com/aws-samples>
- **`aws-ia/terraform-aws-control_tower_account_factory` (AFT)** — how the big shops do account vending (read, don't deploy this week):
  <https://github.com/aws-ia/terraform-aws-control_tower_account_factory>
- **`awslabs/aws-cdk-examples`** — small CDK stacks; read the budget and S3 examples:
  <https://github.com/aws-samples/aws-cdk-examples>
- **`aws/aws-cli`** — the CLI itself, Python, readable:
  <https://github.com/aws/aws-cli>

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **Region** | A physical geographic area (e.g. `eu-west-1` = Ireland) containing multiple isolated AZs. The unit you choose for most resources. |
| **Availability Zone (AZ)** | One or more discrete data centers within a Region, isolated for power/network/fault. Multi-AZ = survives one data center failing. |
| **Edge location** | A CDN/POP site (CloudFront, Route 53) much more numerous than Regions; serves cached content close to users. |
| **`us-east-1`** | N. Virginia. The "first" Region. Some global services' control planes (IAM, CloudFront, Route 53, billing) live here. Special and often busy. |
| **Account** | The hard boundary for security and billing. A container for resources with its own root user and 12-digit ID. |
| **Organization** | A collection of AWS accounts managed centrally from one **management account**. |
| **OU (Organizational Unit)** | A folder in the org tree. You attach policies (like SCPs) to OUs; member accounts inherit them. |
| **SCP (Service Control Policy)** | An org-level *guardrail* that sets the maximum permissions for accounts in an OU. **It never grants — it only limits.** |
| **Root user** | The email-login owner of an account. Near-unlimited power. You lock it away and almost never use it. |
| **IAM Identity Center** | The successor to "AWS SSO." How humans log in across accounts. The `aws sso login` target. (Deep in Week 2.) |
| **CUR** | Cost & Usage Report — the most granular billing data AWS produces, delivered to S3. |
| **Free Tier** | Three flavors: 12-month free, always-free, and short trials. Easy to overrun if you don't watch it. |
| **Budget** | A spend or usage threshold that emails/alerts you when crossed (or forecast to cross). |
| **`aws:PrincipalOrgID`** | A condition key that matches any principal in your Organization — the backbone of org-wide trust policies. |

---

*If a link 404s, please open an issue so we can replace it.*
