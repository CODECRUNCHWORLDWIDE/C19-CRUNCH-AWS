# Mini-Project — The Network Foundation

> Deliver the production VPC topology — three AZs, public/private/isolated subnets, **one** NAT Gateway, endpoint-first egress so AWS-service traffic never touches NAT — and front it with **Route 53 → CloudFront → WAF** terminating ACM-managed TLS. This is the network every compute, data, and capstone lab from Week 5 onward sits inside. You build it once, correctly, and you stop thinking about it.

This is the most important deliverable of Phase 2 and one of the few artifacts in C19 you are explicitly told to **keep deployable for the rest of the course**. Week 5 lands EKS and Fargate in this VPC's private tier. Week 6 mounts EFS into it. Week 8 puts Aurora in the isolated tier. Week 13 wraps it in GuardDuty and Flow Logs. The capstone reuses the exact stack outputs you export here. Get the names and the exports right now and your future self stops re-plumbing networks every week.

**Estimated time:** ~11.5 hours (split across Friday and Saturday in the suggested schedule).

---

## What you will build

A CDK app — TypeScript primary, **one stack re-implemented in OpenTofu** as the cross-tool check — that deploys, from zero, the following with a single `cdk deploy --all`:

```
                         Route 53 hosted zone (app.<your-domain>)
                                      │  A / AAAA alias
                                      ▼
                         CloudFront distribution  ──── ACM cert (us-east-1, DNS-validated)
                          │                        ──── WAF web ACL (CLOUDFRONT scope)
                          │                                ├─ rate-based rule: 500 / 5-min / IP → BLOCK
                          │                                ├─ AWSManagedRulesCommonRuleSet
                          │                                └─ AWSManagedRulesAmazonIpReputationList
                          │ origin (HTTPS, custom header secret)
                          ▼
        ┌──────────────────────────── VPC 10.0.0.0/16, 3 AZs ───────────────────────────┐
        │                                                                                │
        │  PUBLIC  /20 × 3        ──►  Internet Gateway        ┌── ALB (internet-facing) │
        │                                                      │   listener 443, ACM     │
        │  PRIVATE /20 × 3        ──►  NAT Gateway (×1)         └── target: hello service │
        │                                                                                │
        │  ISOLATED /20 × 3       ──►  (no default route — local only)                   │
        │                                                                                │
        │  Gateway endpoints:   S3, DynamoDB            (free, route-table based)         │
        │  Interface endpoints: STS, KMS, SSM, SSMMESSAGES, EC2MESSAGES, ECR_API, ECR_DKR │
        │                       CLOUDWATCH_LOGS, SECRETS_MANAGER  (PrivateLink ENIs)      │
        └────────────────────────────────────────────────────────────────────────────────┘
```

By the end you will have a public GitHub repo of ~500–700 lines of CDK plus an OpenTofu module, a one-page cost report, and a teardown drill you can run in your sleep.

---

## Why these exact pieces (the design review answers)

You will be asked to defend every choice. The defensible answers:

- **`10.0.0.0/16` per VPC, `/20` subnets.** A `/16` is 65,536 addresses; a `/20` is 4,096. Nine `/20`s fit comfortably with room to add a tenth tier later. The `/16` is one slot in a planned estate (`10.0/16` dev, `10.1/16` stage, `10.2/16` prod, …) so nothing overlaps when Transit Gateway joins them in a later course.
- **Three AZs, not two.** Quorum services (etcd, Aurora, Kafka) want three. Two AZs survive one failure but cannot form a majority on recovery. Three is the production default; you pay for it in subnet count, not dollars.
- **One NAT Gateway, not three.** Three NAT Gateways cost ~$98/month in hourly charges *before a single byte of data*. One costs ~$33/month. The trade-off is that an AZ outage takes private-tier egress with it — acceptable in dev/stage, a deliberate decision in prod. You document the trade-off; you do not pretend it doesn't exist. (Lecture 1, §1.4.)
- **Isolated tier with no NAT route.** Databases and the proof host live here. If something in the isolated tier needs S3 or ECR, it goes through an endpoint or it does not go at all. That is the strongest possible enforcement of "no surprise egress."
- **Endpoint-first egress.** S3 and DynamoDB get **gateway** endpoints (free). Everything the platform actually needs to phone home to — STS, KMS, SSM, ECR, CloudWatch Logs, Secrets Manager — gets an **interface** endpoint so it never crosses NAT. This is the whole point of the week: AWS-service traffic is cheaper *and* more private through endpoints. (Lecture 1, §1.5–1.7.)
- **CloudFront in front of the ALB.** TLS terminates at the edge with an ACM cert in `us-east-1`. WAF attaches at CloudFront scope. The ALB only ever talks to CloudFront, gated by a secret custom header so nobody bypasses the edge by hitting the ALB DNS name directly. (Lecture 2, §2.4–2.6.)

---

## Repo layout

```
crunch-week04-network/
├── README.md                       # your write-up (see deliverables)
├── package.json
├── tsconfig.json
├── cdk.json
├── bin/
│   └── crunch-network.ts           # app entry: wires all four stacks with explicit env
├── lib/
│   ├── network-stack.ts            # VPC, subnets, NAT×1, IGW  (from exercise 1)
│   ├── endpoints-stack.ts          # gateway + interface endpoints  (from exercise 2)
│   ├── edge-stack.ts               # ALB + CloudFront + ACM + Route 53 + WAF
│   └── exports.ts                  # the cross-stack export contract (read this section)
├── tofu/
│   ├── main.tf                     # OpenTofu re-implementation of network-stack
│   ├── variables.tf
│   └── outputs.tf
├── test/
│   └── network.test.ts            # fine-grained assertions on the synth
├── cost-report.md                  # your tagged cost breakdown
└── .gitignore
```

---

## The export contract (do not skip this)

Every later week imports this network by **CloudFormation export name**, not by hardcoded id. Define them once, in `lib/exports.ts`, and never rename them:

```typescript
// lib/exports.ts — the stable contract later weeks depend on.
export const EXPORTS = {
  vpcId: 'crunch:network:vpcId',
  privateSubnetIds: 'crunch:network:privateSubnetIds',
  isolatedSubnetIds: 'crunch:network:isolatedSubnetIds',
  publicSubnetIds: 'crunch:network:publicSubnetIds',
  appSecurityGroupId: 'crunch:network:appSgId',
  cloudfrontDomain: 'crunch:edge:cloudfrontDomain',
} as const;
```

In `network-stack.ts`, export with those names:

```typescript
import { CfnOutput } from 'aws-cdk-lib';
import { EXPORTS } from './exports';

new CfnOutput(this, 'VpcIdExport', {
  value: this.vpc.vpcId,
  exportName: EXPORTS.vpcId,
});
new CfnOutput(this, 'PrivateSubnetIdsExport', {
  value: this.vpc.privateSubnets.map((s) => s.subnetId).join(','),
  exportName: EXPORTS.privateSubnetIds,
});
new CfnOutput(this, 'IsolatedSubnetIdsExport', {
  value: this.vpc.isolatedSubnets.map((s) => s.subnetId).join(','),
  exportName: EXPORTS.isolatedSubnetIds,
});
```

A later stack consumes them with `Fn.importValue(EXPORTS.vpcId)` — or, better, re-hydrates the VPC with `ec2.Vpc.fromLookup`. Document which you chose and why in your README.

---

## OpenTofu cross-check (the starter the main README promised)

Drop this into `tofu/main.tf`. It builds the same three-AZ, single-NAT VPC the CDK `network-stack` does. The point is not to ship it — it is to `tofu plan` and compare the resource graph against what `cdk synth` emitted, so you understand what the L2 construct hid.

```hcl
# tofu/main.tf — minimal three-AZ, single-NAT VPC to mirror the CDK stack.
terraform {
  required_version = ">= 1.8.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

provider "aws" {
  region = var.region
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 3)
  # /20 carve-outs inside 10.0.0.0/16, interleaved per AZ and tier.
  public_cidrs   = ["10.0.0.0/20", "10.0.16.0/20", "10.0.32.0/20"]
  private_cidrs  = ["10.0.48.0/20", "10.0.64.0/20", "10.0.80.0/20"]
  isolated_cidrs = ["10.0.96.0/20", "10.0.112.0/20", "10.0.128.0/20"]
}

resource "aws_vpc" "this" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Project = "crunch-week04", ManagedBy = "opentofu" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "crunch-igw" }
}

resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "public-${local.azs[count.index]}", Tier = "public" }
}

resource "aws_subnet" "private" {
  count             = 3
  vpc_id            = aws_vpc.this.id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = local.azs[count.index]
  tags              = { Name = "private-${local.azs[count.index]}", Tier = "private" }
}

resource "aws_subnet" "isolated" {
  count             = 3
  vpc_id            = aws_vpc.this.id
  cidr_block        = local.isolated_cidrs[count.index]
  availability_zone = local.azs[count.index]
  tags              = { Name = "isolated-${local.azs[count.index]}", Tier = "isolated" }
}

# ONE NAT Gateway, in the first public subnet. The cost decision, in HCL.
resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "crunch-nat-eip" }
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.this]
  tags          = { Name = "crunch-nat" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "public-rt" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this.id
  }
  tags = { Name = "private-rt" }
}

# Isolated tier deliberately has NO default route — local only.
resource "aws_route_table" "isolated" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "isolated-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 3
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 3
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "isolated" {
  count          = 3
  subnet_id      = aws_subnet.isolated[count.index].id
  route_table_id = aws_route_table.isolated.id
}

# Gateway endpoint for S3 — free, attaches to the private + isolated route tables.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = concat(
    [aws_route_table.private.id],
    [aws_route_table.isolated.id],
  )
  tags = { Name = "s3-gateway-endpoint" }
}
```

```hcl
# tofu/variables.tf
variable "region" {
  type    = string
  default = "us-east-1"
}
```

```hcl
# tofu/outputs.tf
output "vpc_id" {
  value = aws_vpc.this.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "isolated_subnet_ids" {
  value = aws_subnet.isolated[*].id
}

output "nat_gateway_id" {
  value = aws_nat_gateway.this.id
}
```

Run the comparison:

```bash
cd tofu
tofu init
tofu plan -out=plan.tfplan
tofu show -json plan.tfplan | jq '[.resource_changes[].type] | group_by(.) | map({type: .[0], count: length})'
```

Now count the same resource types in the CDK synth and write one paragraph in your README on the differences. (CDK's `ec2.Vpc` adds a few resources the bare HCL above does not — notice which, and why.) **Do not `tofu apply` and `cdk deploy` the same CIDR into the same account at the same time** — they will collide on the `10.0.0.0/16` allocation. Plan one, apply the other.

---

## Acceptance criteria

- [ ] A new public GitHub repo named `c19-week-04-network-<yourhandle>`.
- [ ] `cdk deploy --all` from a fresh clone deploys all stacks with zero manual console steps.
- [ ] **VPC:** 9 subnets (3 AZs × {public, private, isolated}), each `/20`; exactly **1** NAT Gateway; 1 IGW. Proven with the `aws ec2 describe-*` commands from Exercise 1.
- [ ] **Route tables:** public → IGW, private → NAT, isolated → local-only (no default route). Each private/isolated table carries the S3 gateway-endpoint prefix-list route.
- [ ] **Endpoints:** S3 + DynamoDB gateway endpoints; interface endpoints for STS, KMS, SSM, SSMMESSAGES, EC2MESSAGES, ECR_API, ECR_DKR, CLOUDWATCH_LOGS, SECRETS_MANAGER. Each interface endpoint has `privateDnsEnabled: true` and an SG allowing 443 from the VPC CIDR only.
- [ ] **Zero-NAT proof:** a private/isolated host reads an S3 object and pulls an ECR image while `NatGateway BytesOutToDestination` stays flat. Before/after CloudWatch numbers committed (re-uses Exercise 3).
- [ ] **Edge:** an internet-facing ALB serving a `200` "hello" response; a CloudFront distribution fronting it with `REDIRECT_TO_HTTPS`; an ACM cert in `us-east-1`; a Route 53 alias `app.<your-domain>` → CloudFront. (If you don't own a domain, use the assigned `*.cloudfront.net` name and note the substitution — same as the challenge.)
- [ ] **Origin protection:** the ALB only accepts traffic carrying CloudFront's secret custom header (a WAF rule on a regional web ACL on the ALB, or a header check). A direct `curl` to the ALB DNS name returns `403`; a `curl` through CloudFront returns `200`. Prove both.
- [ ] **WAF:** a CloudFront-scope web ACL with a rate-based rule (500 req / 5-min / IP → BLOCK) plus the two managed rule groups. `BlockedRequests` goes non-zero under load and you capture the figure.
- [ ] **Exports:** the six exports from the contract above are present (`aws cloudformation list-exports | grep crunch:`).
- [ ] **OpenTofu cross-check:** `tofu plan` succeeds and your README has the resource-count comparison paragraph.
- [ ] **Tagging:** every resource carries `Project=crunch-week04`, `Environment`, and `ManagedBy` tags. Used for the cost report.
- [ ] `test/network.test.ts` has **at least 8** fine-grained assertions (e.g. "exactly one NAT Gateway", "isolated route table has no `0.0.0.0/0`", "rate rule limit is 500"). `npm test` passes.
- [ ] `cdk destroy --all` removes everything. You run it. CloudFront takes ~15 min — wait for it.

---

## A fine-grained test to start you off

```typescript
// test/network.test.ts
import { App } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { NetworkStack } from '../lib/network-stack';

test('exactly one NAT Gateway — the cost guardrail', () => {
  const app = new App();
  const stack = new NetworkStack(app, 'Test', {
    env: { account: '111111111111', region: 'us-east-1' },
  });
  const template = Template.fromStack(stack);
  template.resourceCountIs('AWS::EC2::NatGateway', 1);
});

test('nine subnets across three tiers', () => {
  const app = new App();
  const stack = new NetworkStack(app, 'Test', {
    env: { account: '111111111111', region: 'us-east-1' },
  });
  Template.fromStack(stack).resourceCountIs('AWS::EC2::Subnet', 9);
});

test('isolated route tables carry no default route', () => {
  const app = new App();
  const stack = new NetworkStack(app, 'Test', {
    env: { account: '111111111111', region: 'us-east-1' },
  });
  const template = Template.fromStack(stack);
  // No route to 0.0.0.0/0 should target a NAT or IGW from an isolated table.
  // We assert the count of internet-bound routes equals public(3 via IGW
  // collapse to 1 shared) + private(3) only — never isolated.
  template.hasResourceProperties('AWS::EC2::Route', Match.objectLike({
    DestinationCidrBlock: '0.0.0.0/0',
  }));
});
```

Expand from there until you have eight assertions that would each catch a real regression.

---

## Cost report

Write `cost-report.md`. Compute the **steady-state monthly** cost of this foundation, with per-hour and per-GB components shown separately. At minimum:

| Component | Quantity | Unit | Monthly |
|-----------|---------:|------|--------:|
| NAT Gateway hours | 1 × 730 h | $0.045/h | $32.85 |
| NAT data processed | est. GB | $0.045/GB | varies |
| Interface endpoints (hours) | 9 × 3 AZ × 730 h | $0.01/h | $197.10 |
| Interface endpoint data | est. GB | $0.01/GB | varies |
| Gateway endpoints (S3, DDB) | 2 | $0 | $0.00 |
| ALB hours | 730 h | $0.0225/h | $16.43 |
| CloudFront requests + transfer | est. | tiered | varies |
| Route 53 hosted zone | 1 | $0.50/mo | $0.50 |
| WAF web ACL + rule + requests | 1 ACL, 3 rules | $5 + $1×3 + req | ~$8+ |

Then answer in prose: **the interface-endpoint hourly bill is larger than the single NAT Gateway's.** Is endpoint-first egress still worth it? (Yes — but you must say *why*: the data-processing savings at scale, the security posture, and the AZ-independence of gateway endpoints. Defend the number, don't recite it. This is the FinOps muscle Week 14 builds on.)

> Note the trap from Lecture 1: at low data volumes, nine interface endpoints across three AZs can cost *more* than the NAT they replace. The win is at scale and in posture, not at a toy workload. A senior engineer states the break-even, not a slogan.

---

## Deliverables

1. **The CDK monorepo** — `cdk deploy --all` works from a fresh clone; `npm test` passes; `cdk destroy --all` cleans up.
2. **The OpenTofu module** under `tofu/` with the `tofu plan` resource-count comparison written up.
3. **`cost-report.md`** — the table above filled with real numbers from your region, plus the break-even paragraph.
4. **Proof artifacts** committed under `proofs/`: the `describe-subnets` table, the `describe-route-tables` JSON, the before/after NAT `BytesOutToDestination` numbers, the direct-ALB `403` vs CloudFront `200` capture, and the WAF `BlockedRequests` figure under load.
5. **`README.md`** with: the architecture sketch, one-command deploy/destroy instructions from a fresh clone, the import-value-vs-lookup decision, and a short "what I'd change for production" paragraph (hint: a second NAT for prod, Flow Logs on, endpoint policies tightened).

---

## Grading rubric

Total **100 points**. A pass is 70. A distinction (used in the Week-8 design exam seeding) is 90+.

| Criterion | Points | What earns full marks |
|-----------|-------:|-----------------------|
| **VPC topology** | 15 | 9 `/20` subnets, 3 tiers, 3 AZs, exactly 1 NAT, proven by CLI not console. |
| **Route-table correctness** | 15 | Public→IGW, private→NAT, isolated→local-only; S3 prefix-list route present on private/isolated. |
| **Endpoint coverage** | 15 | All required gateway + interface endpoints; private DNS on; SG scoped to VPC CIDR/443. |
| **Zero-NAT proof** | 15 | Flat `BytesOutToDestination` during S3 + ECR access; numbers committed; explanation names the ECR→S3 dependency. |
| **Edge wiring** | 15 | CloudFront + ACM (us-east-1) + Route 53 alias + WAF rate rule; HTTPS works; rate rule trips under load. |
| **Origin protection** | 5 | Direct-ALB `403`, through-CloudFront `200`, both proven. |
| **Exports + reuse** | 5 | Six stable exports present; import strategy documented. |
| **OpenTofu cross-check** | 5 | `tofu plan` clean; resource-count comparison paragraph written. |
| **Cost report** | 5 | Split per-hour/per-GB; honest break-even paragraph. |
| **Tests + hygiene** | 5 | ≥8 fine-grained assertions; clean commits; no account IDs leaked. |

**Automatic deductions.**

- −15 if any NAT Gateway, interface endpoint, ALB, or CloudFront distribution is still billing 24 hours after submission (the `NatGateway-Hours` and `CloudFront` lines in Cost Explorer are the tell).
- −10 if a real account ID, access key, ACM private key, or internal hosted-zone name is committed in plaintext.
- −5 if `cdk synth` or `npm test` fails on a fresh clone.

---

## Why this compounds

The syllabus is explicit: **this network foundation is reused by every compute, data, and capstone lab from here on.** Concretely:

- **Week 5** deploys EKS managed node groups and Fargate tasks into the *private* tier and pulls every image through the ECR endpoints you built — no NAT, no public image registry round-trips.
- **Week 6** mounts EFS and attaches gp3 volumes to instances in this VPC.
- **Week 8** places Aurora writer + readers in the *isolated* tier, reachable only from the private tier via a Security Group reference (the SG-to-SG pattern from this week's homework).
- **Week 13** turns on VPC Flow Logs, GuardDuty (which reads those Flow Logs), and tightens the endpoint policies you stubbed here.
- **The capstone** imports the six exports verbatim. If you rename them now, you rename them in five places later.

Build it like you mean to keep it. You do.

---

## Up next

**Week 5 — Compute Spectrum: EC2 → ECS Fargate → EKS.** Keep this stack deployed (or be ready to `cdk deploy --all` it in three minutes) — Week 5's first lab lands a container in the private tier of *this* VPC. Push the mini-project to GitHub before you start.
