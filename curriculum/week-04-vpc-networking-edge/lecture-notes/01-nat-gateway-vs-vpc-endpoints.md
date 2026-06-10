# Lecture 1 — Three NAT Gateways Will Cost You More Than Your Laptop. Here's the VPC Endpoint Trick.

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can design a multi-AZ VPC with the right subnet tiers, quantify exactly what a NAT Gateway costs, and route AWS-service traffic through gateway and interface endpoints so it never touches NAT — proving it with a flat CloudWatch metric.

If you only remember one thing from this lecture, remember this:

> **A NAT Gateway is a metered toll booth, not a piece of infrastructure you "just need."** It costs you whether or not a single packet flows, and then it charges you again per gigabyte. Most of the traffic a private subnet sends to the internet is actually traffic to *AWS services* — S3, ECR, SSM, STS, KMS. That traffic does not need NAT. It needs an endpoint. Learn to tell the difference and your network bill drops by an order of magnitude.

---

## 1. The bill that started it

Here is a real cost shape we see in student accounts every cohort. Someone follows the "VPC with public and private subnets" wizard, accepts the default of "one NAT Gateway per Availability Zone" for high availability, spreads across three AZs, and walks away. Three weeks later the Cost Explorer line for `EC2-Other / NatGateway-Hours` reads like this:

```
NAT Gateway hours:   3 gateways × 730 hrs/mo × $0.045/hr   = $98.55 / month
NAT data processing: 3 gateways carrying 200 GB total      = $9.00  / month
                                                             ----------------
                                                             $107.55 / month
```

That is **before a single byte of useful work**. The three idle NAT Gateways alone cost more per month than many engineers' monthly laptop depreciation. And the kicker: in a dev environment, the traffic those NAT Gateways carry is almost entirely `pip install`, `docker pull` from ECR, `aws s3 cp`, and SSM agent heartbeats — every one of which can go through a VPC endpoint instead.

The pricing numbers above are us-east-1 list as of early 2026. They drift by region and over time. The *shape* of the problem does not: NAT Gateway has a per-hour charge **and** a per-GB charge, and you pay the per-hour charge for every gateway, in every AZ, around the clock.

> **The exam-room version.** A NAT Gateway in us-east-1 costs about **$0.045 per hour** (~$32.85/month) plus about **$0.045 per GB** processed. An interface VPC endpoint costs about **$0.01 per hour per AZ** (~$7.30/month per AZ) plus about **$0.01 per GB**. A gateway endpoint (S3, DynamoDB) costs **$0.00** — it is free. Internet Gateways are also free. Memorize that hierarchy: IGW free, gateway endpoint free, interface endpoint cheap-and-metered, NAT Gateway expensive-and-metered.

---

## 2. CIDR planning — get this right before you provision anything

A VPC is defined by one or more CIDR blocks. A CIDR block is just an IP range written `address/prefix`. The prefix is how many leading bits are fixed; the rest are addresses you can use.

| CIDR | Addresses | Typical use |
|------|----------:|-------------|
| `10.0.0.0/16` | 65,536 | One VPC |
| `10.0.0.0/20` | 4,096 | One subnet tier in one AZ |
| `10.0.0.0/24` | 256 | A small subnet |
| `10.0.0.0/28` | 16 | The smallest subnet AWS allows |

AWS reserves **five** addresses in every subnet: the network address, the VPC router, the DNS, a future-use address, and the broadcast address. So a `/28` gives you 11 usable IPs, not 16. This matters when you size subnets for tasks that consume an IP each (Fargate tasks, Lambda ENIs, interface endpoints).

**The default we teach:** one `/16` per VPC, carved into `/20` subnets. A `/16` is 65,536 addresses — generous, and it leaves room. A `/20` subnet is 4,096 addresses — enough for a large autoscaling group plus endpoint ENIs, with headroom. Three AZs × three tiers (public, private, isolated) = nine subnets, each `/20`, fits comfortably inside a `/16` with room left over for a fourth AZ later.

Why does this matter so much? **Because CIDR overlap is a one-way door.** The day you want to connect two VPCs with peering or a Transit Gateway, their CIDRs must not overlap. If every team grabbed `10.0.0.0/16` because it was the wizard default, you cannot connect any of them without re-addressing — which means re-deploying everything in the VPC. Plan the whole estate up front:

```
Org-wide IPAM allocation (illustrative)
  10.0.0.0/16     dev      us-east-1
  10.1.0.0/16     stage    us-east-1
  10.2.0.0/16     prod     us-east-1
  10.10.0.0/16    dev      eu-west-1
  10.11.0.0/16    stage    eu-west-1
  10.12.0.0/16    prod     eu-west-1
```

That is the entire reason **AWS IPAM** (IP Address Manager) exists, and why this course assigns non-overlapping ranges from day one. You do not need IPAM for a single VPC, but you need the *discipline* it enforces.

> **War story.** A team peered two `10.0.0.0/16` VPCs "temporarily" by NAT-ing one behind the other. It worked. Then a third VPC needed in. Then a Transit Gateway. Eighteen months later the "temporary" double-NAT was load-bearing infrastructure nobody could safely remove, and every cross-VPC call paid a NAT data-processing charge twice. Plan your CIDRs.

---

## 3. The three subnet tiers

A subnet is just a CIDR slice pinned to one AZ. What makes a subnet "public," "private," or "isolated" is **its route table** — nothing else. There is no checkbox called "public." There is only "does this subnet's route table have a route to an Internet Gateway?"

### Public subnet

Route table contains a default route to the Internet Gateway:

```
Destination     Target
10.0.0.0/16     local
0.0.0.0/0       igw-xxxxxxxx
```

Resources here can be reached from the internet (if they have a public IP and a permissive security group) and can reach the internet directly. **What lives here:** load balancers, NAT Gateways, bastion hosts (if you must), and almost nothing else. Your application servers do **not** belong in a public subnet.

### Private subnet (with egress)

Route table sends the default route to a NAT Gateway that lives in a public subnet:

```
Destination     Target
10.0.0.0/16     local
0.0.0.0/0       nat-xxxxxxxx
```

Resources here can reach the internet **outbound** (to download packages, call third-party APIs) but cannot be reached inbound from the internet. **What lives here:** application servers, ECS/EKS workloads that genuinely need to call out to non-AWS endpoints.

### Isolated subnet (no egress)

Route table has **no** default route at all — only the local route and whatever endpoints you attach:

```
Destination     Target
10.0.0.0/16     local
pl-xxxxxxxx      vpce-xxxxxxxx     (S3 prefix list → gateway endpoint)
```

Resources here cannot reach the internet at all, and cannot be reached from it. They can reach AWS services *only* through VPC endpoints. **What lives here:** databases (RDS, ElastiCache), and — this is the punchline of the whole lecture — **workloads whose only "internet" needs are actually AWS services**. With the right endpoints, an isolated subnet can run an entire containerized application that pulls images from ECR, reads config from S3, fetches secrets from SSM, and signs requests with STS/KMS, while never having a route to the internet and never touching a NAT Gateway.

### Why three AZs and not two

An AZ is an isolated failure domain. With two AZs, losing one halves your capacity and a load balancer with two targets becomes a load balancer with one. With three AZs, losing one costs you a third and the math on quorum-based systems (etcd, Aurora, anything that wants an odd number) works out. Most AWS-managed services (RDS Multi-AZ, EKS control plane, ALB) assume you have at least three. **Default to three AZs.** It costs nothing extra for the subnets themselves; subnets are free.

---

## 4. Internet Gateway, NAT Gateway, egress-only IGW

| Gateway | Direction | IP version | Cost | Scaling |
|---------|-----------|-----------|------|---------|
| **Internet Gateway (IGW)** | In + out | IPv4 + IPv6 | **Free** | Horizontal, region-level, no bottleneck |
| **NAT Gateway** | Out only | IPv4 | **$$$** hourly + per-GB | Per-AZ, up to 100 Gbps |
| **Egress-only IGW** | Out only | IPv6 | **Free** | Horizontal |

The **Internet Gateway** is a logical, horizontally-scaled component attached to the VPC. There is exactly one per VPC. It does not throttle, it does not cost money, and it performs 1:1 NAT for instances that have public IPv4 addresses. A resource is reachable from the internet only if (a) it has a public IP, (b) its subnet routes `0.0.0.0/0` to the IGW, and (c) its security group and NACL allow it. All three.

The **NAT Gateway** exists because a private instance with no public IP still sometimes needs to *initiate* outbound connections. NAT Gateway performs source NAT: it sits in a public subnet, has an Elastic IP, and translates the private instance's source address to its own so return traffic can find its way back. It is **stateful** and **outbound-only** — nothing on the internet can initiate a connection through it. And it is **metered twice**: per hour it exists, and per GB it processes.

**The HA tradeoff that costs you.** A NAT Gateway lives in a single AZ. If that AZ fails, private instances in *other* AZs that route through it lose internet egress. The "best practice" the wizard nudges you toward is one NAT Gateway per AZ, each serving the private subnets in its own AZ, so an AZ failure is contained. That is genuinely correct for production. It is also three times the hourly cost. The judgment call:

- **Production with real egress needs:** one NAT Gateway per AZ. Pay for the resilience.
- **Dev / stage / cost-sensitive:** **one** NAT Gateway total. An AZ failure degrading egress in a dev account is survivable. This is what we build in Exercise 1.
- **Workloads whose only egress is AWS services:** **zero** NAT Gateways. Use endpoints. This is the goal.

The **egress-only Internet Gateway** is the IPv6 story. IPv6 addresses are globally routable, so there is no "private IPv6" — every IPv6 address can in principle be reached. The egress-only IGW provides the stateful, outbound-only behavior NAT gives IPv4, but for IPv6, and it is **free**. If your workload can speak IPv6 to its upstreams, an egress-only IGW replaces a NAT Gateway at zero cost. Adoption is still uneven in 2026 (not every third-party API answers on IPv6), but for AWS-service traffic it is increasingly viable.

---

## 5. Route tables — how a packet actually decides

A route table is a list of rules: destination CIDR → target. When a packet leaves a subnet, AWS evaluates the subnet's associated route table and picks the route with the **most specific** (longest-prefix) matching destination. This is the same longest-prefix-match rule every router on Earth uses.

```
Destination       Target            Picked when...
10.0.0.0/16       local             dest is inside the VPC
10.0.0.0/24       pcx-aaaa          dest is in the peered VPC's /24 (more specific than /16? no — see note)
pl-63a5400a       vpce-s3           dest IP is in the S3 prefix list (gateway endpoint)
0.0.0.0/0         nat-xxxx          everything else
```

Two things trip people up:

1. **`local` always wins for in-VPC traffic and cannot be removed.** Every route table has an unremovable `local` route for the VPC's own CIDR(s). You cannot route around it.
2. **Gateway endpoints work by injecting a prefix list, not `0.0.0.0/0`.** When you attach an S3 gateway endpoint to a route table, AWS adds a route whose destination is the **managed prefix list** `pl-xxxx` representing all of S3's public IP ranges in that region, and whose target is the endpoint. Because the prefix list is more specific than `0.0.0.0/0`, S3 traffic takes the endpoint even though a NAT default route also exists. That is the mechanism by which endpoints "steal" traffic away from NAT — purely through routing, transparently to the application.

This is why a gateway endpoint requires **no application change whatsoever**. Your code still calls `s3.amazonaws.com`. DNS still resolves it to public S3 IPs. But the route table now says "those IPs go to the endpoint," and the packet never reaches the NAT Gateway.

---

## 6. Security Groups vs NACLs

Both are firewalls. They operate at different layers and behave differently, and confusing them causes outages.

| | Security Group | Network ACL |
|--|----------------|-------------|
| Scope | ENI / instance | Subnet |
| State | **Stateful** — return traffic auto-allowed | **Stateless** — you allow each direction explicitly |
| Rules | **Allow only** | **Allow and deny** |
| Evaluation | All rules, OR'd together | Numbered, **first match wins** |
| Default | Deny all inbound, allow all outbound | Default NACL allows all; custom NACL denies all |

**Security Groups are stateful.** If you allow inbound TCP 443, the response packets are allowed out automatically — you do not write an outbound rule for them. They are **allow-only**: you cannot write a "deny" rule in a security group; absence of an allow is the deny. And they are attached to ENIs, so two instances in the same subnet can have completely different security postures. You can reference one security group from another (`allow from sg-abc`), which is how you say "the app tier can talk to the database tier" without hard-coding IPs.

**NACLs are stateless and subnet-wide.** They evaluate rules in numbered order, first match wins, and they have explicit deny. Because they are stateless, the classic gotcha is **ephemeral ports**: if a client behind a NACL makes an outbound HTTPS request, the response comes back to a high-numbered ephemeral port (1024–65535), and you must add an inbound NACL rule allowing that range or the response is dropped. Forget it and "the network just stops working in a way security groups never would."

**The rule of thumb:** do almost all your work in security groups. Reach for NACLs only when you need a coarse, subnet-wide *deny* — for example, blocking a known-bad CIDR at the subnet boundary, or enforcing "this isolated subnet may never talk to the internet, full stop" as defense in depth. NACLs are a blunt instrument; security groups are the scalpel.

---

## 7. VPC endpoints — the actual trick

There are two kinds of VPC endpoint, and the difference is the whole lecture.

### Gateway endpoints — free, for S3 and DynamoDB only

A gateway endpoint is a target you add to a route table. It supports exactly two services: **S3** and **DynamoDB**. It costs **nothing** — no hourly charge, no per-GB charge. When attached, AWS adds the service's prefix-list route to the route tables you select, and traffic to S3/DynamoDB takes that route instead of the NAT default. There is no ENI, no IP consumed, no bandwidth limit beyond the VPC's own.

There is no reason to *not* have S3 and DynamoDB gateway endpoints in every VPC. They are free, they remove the largest source of NAT data-processing charges in most accounts (image layers, build artifacts, logs, backups all live in S3), and they require no application change. Add them by reflex.

### Interface endpoints — PrivateLink, metered, for everything else

An interface endpoint is an **ENI** (with a private IP) placed into your subnets, fronting an AWS service over **PrivateLink**. It supports almost every other AWS service: STS, KMS, SSM (and `ssmmessages`, `ec2messages`), ECR API, ECR DKR, Secrets Manager, CloudWatch Logs, SQS, SNS, and many more. It costs about **$0.01/hr per AZ** the endpoint is deployed in, plus about **$0.01/GB**. So an interface endpoint in three AZs is roughly $22/month before data — still far cheaper than a NAT Gateway, and the traffic through it is private.

The mechanism is different from gateway endpoints. Interface endpoints rely on **private DNS**: when enabled, the endpoint creates a private hosted zone that overrides the public DNS name of the service (e.g. `kms.us-east-1.amazonaws.com`) to resolve to the endpoint's private ENI IPs. Your code calls KMS at its normal endpoint; DNS quietly returns a `10.x` address; the packet goes to the ENI; PrivateLink carries it to the service. No internet, no NAT.

> **The minimum set for a containerized workload.** To run a container in an isolated subnet that pulls from ECR and is managed by Systems Manager, you need: **S3 gateway endpoint** (ECR stores image *layers* in S3 — miss this and `docker pull` fails even with the ECR endpoints present), **ECR API** (`com.amazonaws.<region>.ecr.api`), **ECR DKR** (`com.amazonaws.<region>.ecr.dkr`), **SSM** + **ssmmessages** + **ec2messages** (for Session Manager), **STS** (for credential vending), and usually **KMS** (if your images or buckets are encrypted) and **CloudWatch Logs** (for log delivery). Build all of these in Exercise 2. The single most common "why won't my private task start" bug is a missing S3 gateway endpoint behind the ECR endpoints.

### Endpoint policies

Both kinds support an **endpoint policy** — a resource policy on the endpoint itself that constrains which API calls and which resources are reachable *through* it. A common pattern: an S3 gateway endpoint whose policy allows access only to your own account's buckets, so even a compromised instance cannot exfiltrate to an arbitrary public bucket through the endpoint. We use endpoint policies in the mini-project.

---

## 8. Building it in CDK

Here is the core of Exercise 1 and the mini-project — a three-AZ VPC with all three tiers and exactly one NAT Gateway, in TypeScript CDK. The L2 `Vpc` construct does an enormous amount for you; read what it emits with `cdk synth`.

```typescript
import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

export class NetworkStack extends Stack {
  public readonly vpc: ec2.Vpc;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/16'),
      maxAzs: 3,
      // ONE NAT Gateway for the whole VPC, not one per AZ. This is the cost decision.
      natGateways: 1,
      subnetConfiguration: [
        {
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 20,
        },
        {
          name: 'private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, // routes 0.0.0.0/0 to the NAT
          cidrMask: 20,
        },
        {
          name: 'isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,    // no default route at all
          cidrMask: 20,
        },
      ],
    });
  }
}
```

Three things to notice:

- `natGateways: 1`. The construct defaults to one NAT per AZ when you have public subnets. We override to one. That single line is the difference between $33/month and $99/month.
- `PRIVATE_WITH_EGRESS` is the modern name for "private subnet routed to NAT." `PRIVATE_ISOLATED` is "no egress at all."
- `cidrMask: 20` makes each subnet a `/20`. With `maxAzs: 3` and three tiers, that's nine `/20` subnets — well inside the `/16`.

Now the endpoints. Gateway endpoints first (free):

```typescript
this.vpc.addGatewayEndpoint('S3Endpoint', {
  service: ec2.GatewayVpcEndpointAwsService.S3,
});
this.vpc.addGatewayEndpoint('DynamoDbEndpoint', {
  service: ec2.GatewayVpcEndpointAwsService.DYNAMODB,
});
```

Then the interface endpoints. We place them in the isolated subnets (where the workloads that need them live) and enable private DNS:

```typescript
const interfaceServices: Record<string, ec2.InterfaceVpcEndpointAwsService> = {
  Sts: ec2.InterfaceVpcEndpointAwsService.STS,
  Kms: ec2.InterfaceVpcEndpointAwsService.KMS,
  Ssm: ec2.InterfaceVpcEndpointAwsService.SSM,
  SsmMessages: ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
  Ec2Messages: ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
  EcrApi: ec2.InterfaceVpcEndpointAwsService.ECR,
  EcrDocker: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
  Logs: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
};

for (const [id, service] of Object.entries(interfaceServices)) {
  this.vpc.addInterfaceEndpoint(`${id}Endpoint`, {
    service,
    subnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
    privateDnsEnabled: true,
  });
}
```

The same VPC in Python CDK, for the Python track:

```python
from aws_cdk import Stack, aws_ec2 as ec2
from constructs import Construct


class NetworkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=3,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=20
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=20,
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=20,
                ),
            ],
        )

        self.vpc.add_gateway_endpoint(
            "S3Endpoint", service=ec2.GatewayVpcEndpointAwsService.S3
        )
        self.vpc.add_gateway_endpoint(
            "DynamoDbEndpoint", service=ec2.GatewayVpcEndpointAwsService.DYNAMODB
        )
```

And the same VPC skeleton in OpenTofu, so you see how much the CDK construct hides:

```hcl
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "crunch-net" }
}

# One subnet per tier per AZ — OpenTofu makes you write each one (or loop).
resource "aws_subnet" "isolated" {
  for_each          = toset(["us-east-1a", "us-east-1b", "us-east-1c"])
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 4, index(["us-east-1a", "us-east-1b", "us-east-1c"], each.key) + 6)
  tags              = { Name = "crunch-isolated-${each.key}", Tier = "isolated" }
}

# The free S3 gateway endpoint, associated with the isolated route tables.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.us-east-1.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.isolated.id]
}
```

The OpenTofu version is more verbose because nothing is inferred. That verbosity is also clarity: you can see every subnet, every route table, every association. When the CDK `Vpc` does something surprising, drop into the synthesized template or rebuild the piece in OpenTofu to understand it.

---

## 9. Proving zero NAT — the flat line

Building the endpoints is half the job. *Proving* the traffic takes them is the other half, and it is the skill that separates "I think it's working" from "I demonstrated it's working." The proof is a CloudWatch metric: NAT Gateway `BytesOutToDestination`.

After deploying a private (isolated) EC2 instance and the endpoints, you `aws ssm start-session` into the instance (no SSH key, no bastion — Session Manager rides the SSM endpoints), then generate AWS-service traffic:

```bash
# Read an S3 object — should go through the S3 gateway endpoint (free, no NAT).
aws s3 cp s3://my-bucket/big-object.bin /dev/null

# Pull a container image from ECR — through the ECR + S3 endpoints, no NAT.
aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker pull "$ECR_REGISTRY/myimage:latest"
```

Then query the NAT Gateway metric for the window you ran the test:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name BytesOutToDestination \
  --dimensions Name=NatGatewayId,Value=nat-0abc123 \
  --start-time "$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Sum
```

If your endpoints are working, the `Sum` for every 5-minute datapoint is **0** (or a few stray bytes from OS background chatter). If you forgot the S3 gateway endpoint, you will see the `docker pull` show up as megabytes of NAT data processing, and you will have learned exactly what that endpoint is for. That contrast — run it without the endpoint, see the bytes; add the endpoint, see zero — is the most memorable moment of the week. We do it deliberately in Exercise 3.

---

## 10. PrivateLink, Transit Gateway, and peering — choosing

Interface endpoints are *consuming* PrivateLink. You can also *provide* it. If your team runs an internal service and wants other VPCs (or other accounts) to reach it privately, you put the service behind a **Network Load Balancer**, create a **VPC endpoint service** from it, and consumers create interface endpoints to your service. No peering, no shared CIDRs, no transitive routing — just a private one-way pipe to one service. This is how SaaS vendors expose products inside your VPC without internet exposure.

For connecting whole VPCs to each other, you have two tools:

- **VPC peering** is a direct, **non-transitive** link between exactly two VPCs. A↔B and B↔C does **not** give you A↔C. It is cheap (no hourly charge; you pay only inter-AZ/inter-region data) and simple. Use it for a small, stable number of VPCs that need full connectivity — say, two or three.
- **Transit Gateway** is a regional router. Every VPC attaches once to the TGW, and the TGW's route tables decide who can reach whom — including transitively. It has an **hourly charge per attachment** plus per-GB data, so it costs more than peering, but it scales: connecting 20 VPCs with peering needs 190 peering connections (n·(n−1)/2); with a TGW it needs 20 attachments. Use TGW when you have many VPCs, need transitive routing, or want centralized network control (e.g. a shared inspection/egress VPC).

The decision tree: **two or three VPCs, full mesh, cost-sensitive → peering. Many VPCs, hub-and-spoke, transitive, central control → Transit Gateway. One private service exposed to consumers → PrivateLink endpoint service.**

---

## 11. What you should be able to do now

- Carve a `/16` into `/20` subnets across three AZs and three tiers without overlap.
- Look at a route table and say which tier the subnet is and where its packets go.
- Quote the cost of a NAT Gateway and an interface endpoint from memory, and justify one NAT vs three.
- List the endpoints a private containerized workload needs — and remember the S3 gateway endpoint behind ECR.
- Prove, with a CloudWatch metric, that AWS-service traffic is not crossing NAT.
- Pick between peering, Transit Gateway, and PrivateLink for a given topology.

Next lecture we leave the VPC and go to the edge: Route 53 routing policies, CloudFront, ACM-managed TLS, and a WAF rate-limit rule you can trip on demand.

---

*Reading checkpoint:* before Exercise 1, re-read §3 (subnet tiers) and §7 (endpoints) until you can draw the VPC from memory — three AZs, three tiers, one NAT, the endpoints attached to the isolated tier. If you cannot draw it, you cannot build it.
