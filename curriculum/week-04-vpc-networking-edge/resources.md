# Week 4 — Resources

Everything on this page is **free to read or watch**. AWS documentation needs no account. The Well-Architected pillars are public PDFs and web pages. re:Invent talks live free on YouTube. No paywalled books are linked. Prices quoted are us-east-1 list as of early 2026 — always confirm against the live pricing page for your region.

## Required reading (work it into Monday)

- **VPC User Guide — "How Amazon VPC works"** — the canonical mental model for VPCs, subnets, route tables, and gateways:
  <https://docs.aws.amazon.com/vpc/latest/userguide/how-it-works.html>
- **AWS Well-Architected — Reliability Pillar, "Plan your network topology"** — the design questions you should be able to answer before you provision anything:
  <https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/plan-your-network-topology.html>
- **VPC endpoints overview** — gateway vs interface, the single most cost-relevant page this week:
  <https://docs.aws.amazon.com/vpc/latest/privatelink/concepts.html>
- **NAT gateways** — how they work, what they cost, and the "one per AZ for HA" tradeoff:
  <https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html>
- **Route 53 routing policies** — read the one-paragraph summary of each policy before Lecture 2:
  <https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html>

## VPC core docs

- **CIDR blocks for your VPC** — the `/16`–`/28` rules and the five reserved IPs per subnet:
  <https://docs.aws.amazon.com/vpc/latest/userguide/vpc-cidr-blocks.html>
- **Subnets for your VPC** — public/private/VPN-only and how the route table defines the tier:
  <https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html>
- **Route tables** — main vs custom, propagation, longest-prefix match:
  <https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Route_Tables.html>
- **Security groups** — stateful, allow-only, instance-scoped:
  <https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html>
- **Network ACLs** — stateless, allow+deny, subnet-scoped, and the ephemeral-port rule:
  <https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html>
- **Compare security groups and network ACLs** — the side-by-side table to memorize:
  <https://docs.aws.amazon.com/vpc/latest/userguide/infrastructure-security.html>
- **Egress-only internet gateways** — IPv6 outbound-only:
  <https://docs.aws.amazon.com/vpc/latest/userguide/egress-only-internet-gateway.html>

## PrivateLink, Transit Gateway, peering

- **AWS PrivateLink concepts** — endpoint services, interface endpoints, NLB-backed providers:
  <https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-share-your-services.html>
- **Transit Gateway** — hub-and-spoke at scale, attachments, route tables:
  <https://docs.aws.amazon.com/vpc/latest/tgw/what-is-transit-gateway.html>
- **VPC peering** — non-transitive one-to-one connections and when to prefer them:
  <https://docs.aws.amazon.com/vpc/latest/peering/what-is-vpc-peering.html>
- **"Building a Scalable and Secure Multi-VPC AWS Network Infrastructure"** — AWS whitepaper, the reference for choosing between peering and TGW:
  <https://docs.aws.amazon.com/whitepapers/latest/building-scalable-secure-multi-vpc-network-infrastructure/welcome.html>

## Edge: Route 53, CloudFront, ACM, WAF, Shield

- **Route 53 — choosing a routing policy**:
  <https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-types.html>
- **Route 53 — alias records** (and why you alias to AWS resources instead of CNAME):
  <https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html>
- **CloudFront — restrict access with Origin Access Control (OAC)** (OAI is legacy):
  <https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html>
- **ACM — request a public certificate** (DNS validation, the `us-east-1` rule for CloudFront):
  <https://docs.aws.amazon.com/acm/latest/userguide/gs-acm-request-public.html>
- **AWS WAF — rate-based rule statements**:
  <https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html>
- **AWS WAF — managed rule groups** (the AWS baseline you turn on by default):
  <https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-list.html>
- **AWS Shield — Standard vs Advanced**:
  <https://docs.aws.amazon.com/waf/latest/developerguide/ddos-overview.html>

## CDK references

- **AWS CDK v2 API — `aws-cdk-lib/aws-ec2`** (`Vpc`, `SubnetType`, `GatewayVpcEndpoint`, `InterfaceVpcEndpoint`):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2-readme.html>
- **CDK `Vpc` construct deep-dive** — `subnetConfiguration`, `natGateways`, `maxAzs`:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.Vpc.html>
- **CDK `aws-cloudfront` and `aws-cloudfront-origins`**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudfront-readme.html>
- **CDK `aws-route53` and `aws-route53-targets`** (alias targets):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53_targets-readme.html>
- **CDK `aws-wafv2`** (L1 only — WAF has no L2 yet; read the CfnWebACL props):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_wafv2.CfnWebACL.html>

## OpenTofu / Terraform AWS provider

- **`aws_vpc`, `aws_subnet`, `aws_route_table` resources**:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc>
- **`aws_vpc_endpoint` (gateway + interface)**:
  <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_endpoint>
- **`terraform-aws-modules/vpc`** — the de-facto community VPC module; read it even if you don't use it:
  <https://github.com/terraform-aws-modules/terraform-aws-vpc>
- **OpenTofu docs** (the open-source Terraform fork this course standardizes on):
  <https://opentofu.org/docs/>

## Pricing pages (bookmark; check before every lab)

- **VPC pricing** (NAT Gateway hourly + per-GB, interface endpoint hourly + per-GB):
  <https://aws.amazon.com/vpc/pricing/>
- **CloudFront pricing** (data out + requests; the always-free tier):
  <https://aws.amazon.com/cloudfront/pricing/>
- **Route 53 pricing** ($0.50/hosted zone/mo, query pricing, health checks):
  <https://aws.amazon.com/route53/pricing/>
- **AWS WAF pricing** (per web ACL, per rule, per million requests):
  <https://aws.amazon.com/waf/pricing/>

## re:Invent and AWS talks (free, no signup)

- **"Advanced VPC design and new capabilities for amazon VPC" (NET302/NET305 lineage)** — the perennial deep VPC-design talk; search the latest year on the AWS Events channel:
  <https://www.youtube.com/@AWSEventsChannel>
- **"A deep dive into AWS PrivateLink"** — how interface endpoints and endpoint services actually route:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Amazon CloudFront and edge services"** — distributions, OAC, cache behaviors, functions:
  <https://www.youtube.com/@AWSEventsChannel>
- **AWS re:Post — Networking & Content Delivery** — real questions, real answers, when docs aren't enough:
  <https://repost.aws/tags/networking-content-delivery>

## Tools you'll use this week

- **AWS CLI v2** — `aws ec2 describe-vpcs`, `aws ec2 describe-route-tables`, `aws cloudwatch get-metric-statistics`. Verify with `aws --version` (expect `2.x`).
- **AWS CDK v2 CLI** — `npm i -g aws-cdk`; verify with `cdk --version`.
- **OpenTofu 1.8+** — `tofu version`.
- **Session Manager plugin** — to `aws ssm start-session` into the private EC2 instance without a bastion or SSH key:
  <https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html>
- **`dig`** — to prove your Route 53 alias resolves to CloudFront edge IPs. Preinstalled on macOS/Linux.
- **`hey`** or **`wrk`** — HTTP load generators to trip the WAF rate-limit rule. `brew install hey` or `go install github.com/rakyll/hey@latest`.

## Open-source infrastructure to read

You learn network design faster from one good Terraform module than from three blog posts. Pick one and read it top to bottom:

- **`terraform-aws-modules/terraform-aws-vpc`** — how a battle-tested module names subnets, tiers NAT, and wires endpoints.
- **AWS CDK `aws-ec2` source** (`Vpc` L2) — read how `subnetConfiguration` becomes CloudFormation: <https://github.com/aws/aws-cdk/tree/main/packages/aws-cdk-lib/aws-ec2/lib>
- **`cloudposse/terraform-aws-dynamic-subnets`** — an opinionated take on multi-tier subnetting worth contrasting with the official module.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **CIDR** | An IP range written as `address/prefix`, e.g. `10.0.0.0/16` = 65,536 addresses. |
| **VPC** | Your private virtual network in one region. Defined by one or more CIDR blocks. |
| **AZ** | Availability Zone — an isolated datacenter cluster within a region. Use three. |
| **Subnet** | A CIDR slice pinned to one AZ. Its route table decides its tier. |
| **IGW** | Internet Gateway — the free, scaled door between a VPC and the public internet. |
| **NAT Gateway** | Managed outbound NAT for private subnets. ~$0.045/hr + ~$0.045/GB. The silent budget killer. |
| **Egress-only IGW** | IPv6-only outbound gateway. Free. The IPv6 analogue to NAT. |
| **Route table** | Rules mapping destination CIDRs to targets (IGW, NAT, endpoint, peering). |
| **Security Group** | Stateful, allow-only firewall attached to ENIs. Return traffic is automatic. |
| **NACL** | Stateless, allow+deny firewall on a subnet. You must allow return traffic explicitly. |
| **Gateway endpoint** | Free route-table entry for S3/DynamoDB traffic. No ENI, no hourly charge. |
| **Interface endpoint** | A PrivateLink ENI in your subnet for a service. ~$0.01/hr each + data. |
| **PrivateLink** | Private connectivity to a service via an ENI, no internet, no NAT. |
| **Transit Gateway** | A regional router that connects many VPCs hub-and-spoke. Hourly + per-GB. |
| **OAC** | Origin Access Control — how CloudFront authenticates to a private S3 origin (replaces OAI). |
| **ACM** | AWS Certificate Manager — free public TLS certs. CloudFront needs them in `us-east-1`. |
| **WAF** | Web Application Firewall — web ACLs of rules attached to CloudFront/ALB/API Gateway. |
| **Shield Standard** | Free, automatic L3/L4 DDoS protection on all AWS accounts. |

---

*If a link 404s, please open an issue so we can replace it.*
