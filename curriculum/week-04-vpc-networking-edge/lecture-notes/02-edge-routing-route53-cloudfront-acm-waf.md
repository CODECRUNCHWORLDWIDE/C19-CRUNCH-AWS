# Lecture 2 — Edge Routing Done Right: Route 53 Policies, CloudFront, ACM TLS, and WAF Rate-Limiting

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can put a custom domain in front of an AWS resource with the correct Route 53 routing policy, serve it over HTTPS through CloudFront with an ACM-managed certificate, and attach an AWS WAF web ACL with a rate-based rule you can demonstrate firing under load. You can also explain Shield Standard vs Advanced without hand-waving.

If you only remember one thing from this lecture, remember this:

> **The edge is where you do three jobs at once: name resolution (Route 53), content delivery + TLS termination (CloudFront + ACM), and the first line of defense (WAF + Shield).** Each of these is a separate AWS service with its own quirks, but they compose into one request path: DNS → edge → origin. Learn the path and the quirks fall into place.

Last lecture you built the private network. This lecture is the public face that sits in front of it. The two meet in the mini-project, where Route 53 → CloudFront → ALB lands traffic into the VPC you already built.

---

## 1. The request path, end to end

Before any service details, fix the path in your head. A user types `app.example.com` and presses enter:

```
1. Browser asks the resolver for app.example.com
2. Resolver walks DNS to Route 53 (the authoritative name server for example.com)
3. Route 53 applies the routing policy and returns an answer:
     - an ALIAS to a CloudFront distribution → a set of edge IPs
4. Browser opens TLS to the nearest CloudFront edge location
     - CloudFront presents the ACM certificate for app.example.com (cert lives in us-east-1)
5. WAF web ACL on the distribution evaluates the request
     - rate-based rule, managed rule groups, geo rules → allow / block / count
6. CloudFront checks its cache; on a miss it fetches from the ORIGIN
     - origin is the ALB in your public subnet (or an S3 bucket via OAC)
7. ALB routes to a target in the private subnet; response flows back, gets cached, returns to the user
```

Every service in this lecture owns one hop. Route 53 owns step 3. CloudFront and ACM own steps 4 and 6. WAF and Shield own step 5. Keep the path in mind and you will always know which service to reach for.

---

## 2. Route 53 — hosted zones and records

Route 53 is AWS's authoritative DNS. You give it a **hosted zone** for a domain, and it answers queries for that domain's records.

- A **public hosted zone** answers queries from the internet. You register or delegate `example.com` to Route 53's name servers, and it becomes the source of truth.
- A **private hosted zone** is associated with one or more VPCs and answers queries only from inside them. This is how you give internal services friendly names (`db.internal.example.com`) that resolve to private IPs and never leak to the public internet. The interface-endpoint private DNS from Lecture 1 is private hosted zones under the hood.

A hosted zone costs **$0.50/month** plus query charges. The query charges are tiny ($0.40 per million for standard queries). The thing to watch is health checks ($0.50/month each) if you use failover.

### Alias vs CNAME — always alias to AWS resources

A **CNAME** maps one name to another name. You cannot put a CNAME at a zone apex (`example.com` itself) — DNS forbids it. And a CNAME costs you a query to resolve the target.

An **alias record** is a Route 53 extension. It maps a name directly to an AWS resource (a CloudFront distribution, an ALB, an S3 website endpoint, another Route 53 record) and Route 53 resolves the target's IPs internally at query time. Alias records:

- **Work at the zone apex.** You can alias `example.com` → CloudFront. A CNAME cannot.
- **Are free to resolve** — no charge for the alias query to an AWS resource.
- **Track the target's IPs automatically.** When CloudFront's edge IPs change, the alias keeps working.

The rule: **alias to AWS resources, CNAME only to external (non-AWS) hostnames.** In this course you will almost never write a CNAME.

---

## 3. Route 53 routing policies

A routing policy decides *which* answer Route 53 returns when there is more than one possible record for a name. There are seven; you need fluency in five.

| Policy | What it does | Use it for |
|--------|--------------|-----------|
| **Simple** | One record, one answer. | A single resource, no failover. |
| **Weighted** | Splits traffic by integer weights across records. | Blue/green, canary, A/B (90/10). |
| **Latency** | Returns the record in the region with lowest latency to the user. | Multi-region apps; send users to the nearest region. |
| **Failover** | Primary + secondary; health check flips to secondary when primary is unhealthy. | Active/passive DR. |
| **Geolocation** | Routes by the user's continent/country. | Compliance, localization, geo-blocking. |
| **Geoproximity** | Routes by geographic distance with a bias knob. | Fine-grained traffic shaping (Traffic Flow). |
| **Multivalue answer** | Returns up to 8 healthy records at random. | Cheap client-side load spreading. |

The two you will lean on most:

**Weighted** for safe deploys. You stand up a green environment, point a weighted record at it with weight 10 and the blue environment with weight 90, watch the dashboards, then shift weights. No DNS surgery, just integer changes.

**Failover** for DR. You attach a **health check** to the primary record. The health check pings an endpoint (HTTP/HTTPS/TCP) from multiple AWS locations; when it fails the threshold, Route 53 stops returning the primary and returns the secondary instead. This is the backbone of Week 14's multi-region DR.

Latency and failover both depend on health checks to be useful — a failover record with no health check never fails over. Geolocation has a subtle trap: always configure a **default** location record, or users from a country you didn't enumerate get **no answer at all**.

In CDK, an alias record to a CloudFront distribution with a simple policy:

```typescript
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as targets from 'aws-cdk-lib/aws-route53-targets';

const zone = route53.HostedZone.fromLookup(this, 'Zone', {
  domainName: 'example.com',
});

new route53.ARecord(this, 'AppAlias', {
  zone,
  recordName: 'app',
  target: route53.RecordTarget.fromAlias(
    new targets.CloudFrontTarget(distribution),
  ),
});
```

A weighted pair (blue 90 / green 10) is the same `ARecord` twice with `weight` and a shared `setIdentifier`:

```typescript
new route53.ARecord(this, 'AppBlue', {
  zone, recordName: 'app',
  target: route53.RecordTarget.fromAlias(new targets.CloudFrontTarget(blueDist)),
  weight: 90,
  setIdentifier: 'blue',
});
new route53.ARecord(this, 'AppGreen', {
  zone, recordName: 'app',
  target: route53.RecordTarget.fromAlias(new targets.CloudFrontTarget(greenDist)),
  weight: 10,
  setIdentifier: 'green',
});
```

---

## 4. CloudFront — the CDN and TLS terminator

CloudFront is AWS's content delivery network: a global fleet of **edge locations** (hundreds of them) that cache your content close to users and terminate TLS at the edge. It does three jobs that matter to us:

1. **Caches** static and cacheable dynamic content at the edge, cutting latency and origin load.
2. **Terminates TLS** with an ACM certificate, so users get HTTPS to the nearest edge even if your origin is plain HTTP inside the VPC.
3. **Is the attachment point** for WAF and Shield — your first line of defense lives here.

A **distribution** has one or more **origins** (where the real content comes from) and **cache behaviors** (path-pattern rules deciding how each request is cached and which origin it hits). Origins are commonly:

- An **S3 bucket** for static assets, accessed privately via **Origin Access Control (OAC)** so the bucket stays fully private and only CloudFront can read it.
- An **ALB** for dynamic content, which is the mini-project's pattern: CloudFront → ALB (public subnet) → targets (private subnet).

**OAC, not OAI.** Older docs mention Origin Access Identity. OAC is the current mechanism; it signs CloudFront's requests to S3 with SigV4 and supports SSE-KMS. Use OAC. In CDK, the `S3BucketOrigin.withOriginAccessControl()` helper wires it for you.

A minimal CloudFront distribution fronting an ALB origin, in CDK:

```typescript
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';

// NOTE: the cert MUST be in us-east-1 for CloudFront, regardless of where the app lives.
const distribution = new cloudfront.Distribution(this, 'Cdn', {
  defaultBehavior: {
    origin: new origins.LoadBalancerV2Origin(alb, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
    }),
    viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
  },
  domainNames: ['app.example.com'],
  certificate: acm.Certificate.fromCertificateArn(this, 'Cert', usEast1CertArn),
  minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
  webAclId: webAcl.attrArn, // WAF, attached below
});
```

`REDIRECT_TO_HTTPS` is non-negotiable — never serve an app on plain HTTP at the edge. `CACHING_OPTIMIZED` is a sensible default managed cache policy; for a truly dynamic app you would use `CACHING_DISABLED` or a custom policy, but the static hello page in this week's challenge caches fine.

---

## 5. ACM — managed TLS, and the us-east-1 rule

AWS Certificate Manager issues and **auto-renews** public TLS certificates for free. You never touch a private key; ACM generates it, stores it, and rotates the cert before expiry. This alone makes manual cert management obsolete for AWS-hosted services.

Two rules you must internalize:

1. **For CloudFront, the certificate must be in `us-east-1`.** CloudFront is a global service whose control plane lives in us-east-1, and it can only attach certs from that region. If your app runs in eu-west-1, your ALB cert is in eu-west-1 but your CloudFront cert is in us-east-1. This trips up everyone once. In CDK you handle it with a cross-region stack or the `DnsValidatedCertificate`/`Certificate` in a `us-east-1`-pinned stack.
2. **Use DNS validation, not email.** ACM proves you control the domain. DNS validation adds a CNAME record to your hosted zone; if Route 53 manages the zone, CDK can write that record automatically and the cert validates in minutes with no human in the loop. Email validation requires someone to click a link every renewal — avoid it.

Requesting a DNS-validated cert in CDK, with Route 53 auto-validation:

```typescript
const cert = new acm.Certificate(this, 'AppCert', {
  domainName: 'app.example.com',
  validation: acm.CertificateValidation.fromDns(zone), // writes the CNAME for you
});
```

For the CloudFront case, this stack must be deployed to `us-east-1` (set `env: { region: 'us-east-1' }` on the stack, or use a dedicated edge stack). The mini-project shows the cross-region wiring.

---

## 6. AWS WAF — web ACLs and the rate-based rule

AWS WAF is a layer-7 firewall you attach to a CloudFront distribution, an ALB, an API Gateway stage, or an AppSync API. The unit is a **web ACL** — an ordered list of **rules**, each of which **allows**, **blocks**, or **counts** matching requests, with a **default action** for requests that match nothing.

Rules come in three flavors:

- **Managed rule groups** — AWS- or vendor-maintained rule sets. The two you turn on by reflex: `AWSManagedRulesCommonRuleSet` (the OWASP-ish baseline) and `AWSManagedRulesAmazonIpReputationList` (known-bad IPs). They cost a little and catch a lot.
- **Rate-based rules** — the star of this lecture. A rate-based rule counts requests from each source IP (or other key) over a **5-minute sliding window** and blocks any source that exceeds a limit you set. This is your defense against credential-stuffing, scraping, and small floods.
- **Custom rules** — match on IP set, geo, headers, URI, body, regex, etc.

> **The rate-based rule, precisely.** You set a `Limit` (minimum 10, evaluated over a trailing 5-minute window) and an `AggregateKeyType` (commonly `IP`, or `FORWARDED_IP` when behind CloudFront, since the client IP arrives in the `X-Forwarded-For` header). When a single source crosses the limit, WAF blocks **that source** until its rate drops back under the limit. It does not block everyone — only the offending key. This is exactly the behavior you will demonstrate in the challenge: hammer the endpoint from one machine, watch your own requests start returning `403`, then stop and watch them recover.

WAF has no L2 CDK construct yet — you use the L1 `CfnWebACL`. Here is a web ACL with the two managed groups and a rate-based rule, scoped to CloudFront (`scope: 'CLOUDFRONT'`, which **must** be created in `us-east-1`):

```typescript
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';

const webAcl = new wafv2.CfnWebACL(this, 'WebAcl', {
  scope: 'CLOUDFRONT', // for ALB/API GW use 'REGIONAL'
  defaultAction: { allow: {} },
  visibilityConfig: {
    cloudWatchMetricsEnabled: true,
    metricName: 'crunchWebAcl',
    sampledRequestsEnabled: true,
  },
  rules: [
    {
      name: 'RateLimit',
      priority: 0,
      action: { block: {} },
      statement: {
        rateBasedStatement: {
          limit: 100,            // requests per 5-minute window per IP
          aggregateKeyType: 'IP',
        },
      },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'rateLimit',
        sampledRequestsEnabled: true,
      },
    },
    {
      name: 'AWSCommon',
      priority: 1,
      overrideAction: { none: {} },
      statement: {
        managedRuleGroupStatement: {
          vendorName: 'AWS',
          name: 'AWSManagedRulesCommonRuleSet',
        },
      },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'awsCommon',
        sampledRequestsEnabled: true,
      },
    },
    {
      name: 'IpReputation',
      priority: 2,
      overrideAction: { none: {} },
      statement: {
        managedRuleGroupStatement: {
          vendorName: 'AWS',
          name: 'AWSManagedRulesAmazonIpReputationList',
        },
      },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'ipReputation',
        sampledRequestsEnabled: true,
      },
    },
  ],
});
```

Three details that bite people:

- **`scope: 'CLOUDFRONT'` web ACLs must be created in `us-east-1`.** A `REGIONAL` web ACL (for ALB/API GW) is created in the resource's region.
- **`action` vs `overrideAction`.** Your own rules use `action` (`block`/`allow`/`count`). Managed rule groups use `overrideAction` (`none` to honor the group's own actions, or `count` to run them in count-only "dry run" mode while you tune).
- **Lower `priority` evaluates first.** Put the rate-based rule early so a flood is dropped before it costs you managed-rule evaluations.

---

## 7. Shield Standard vs Advanced

**Shield Standard** is free, automatic, and already protecting every AWS account at the network and transport layers (L3/L4). It absorbs the common SYN/UDP floods and reflection attacks against CloudFront, Route 53, and Global Accelerator with no configuration and no cost. You already have it. You do nothing to turn it on.

**Shield Advanced** costs **$3,000 per month** (one-year commitment, billed per organization, plus data transfer out fees during attacks) and adds:

- **Layer-7 DDoS protection** with health-based detection and the ability to engage the **Shield Response Team (SRT)** during an active attack.
- **Cost protection** — AWS credits back the scaling charges (CloudFront, Route 53, ELB, EC2) incurred *because* of a covered DDoS attack, so a volumetric attack doesn't also hand you a surprise bill.
- **Automatic application-layer mitigation** in concert with WAF, and managed rule recommendations.
- **Global visibility** of attacks across protected resources.

The decision is simple and almost always the same: **Shield Standard for everything; Shield Advanced only when you have a public, revenue-critical, attack-attractive target and the $36k/year is cheaper than the risk.** For this course and for the vast majority of workloads, Standard plus a well-configured WAF (including the rate-based rule above) is the right posture. Reaching for Shield Advanced on a hobby project is the same mistake as deploying three NAT Gateways in dev — paying for resilience you don't need.

---

## 8. Putting it together — the edge stack shape

The mini-project assembles all of this. The shape:

```
Route 53 public hosted zone (example.com)
  └── A (alias) app.example.com ──► CloudFront distribution
                                       ├── ACM cert (us-east-1) for app.example.com
                                       ├── WAF web ACL (CLOUDFRONT scope, us-east-1)
                                       │     ├── rate-based rule (limit 100/5min/IP)
                                       │     ├── AWSManagedRulesCommonRuleSet
                                       │     └── AWSManagedRulesAmazonIpReputationList
                                       └── origin: ALB (public subnet of the Week-4 VPC)
                                             └── targets in the PRIVATE subnet
```

Notice the layering: the public name resolves to the edge, the edge holds the cert and the firewall, and only past the firewall does a request reach your ALB and — through the VPC you built in Lecture 1 — your actual workload sitting safely in a private subnet. The network and the edge are two halves of one design.

---

## 9. Proving the rate limit fires

Like the zero-NAT proof last lecture, "I configured a rate limit" is not the same as "I demonstrated a rate limit." The proof is load plus observation.

Generate sustained traffic from one source with `hey`:

```bash
# 2000 requests, 50 concurrent, against the CloudFront domain.
hey -n 2000 -c 50 https://app.example.com/
```

With the limit at 100 requests per 5-minute window per IP, a burst of 2000 from one IP will quickly exceed it, and `hey`'s status-code histogram will show a mix of `200` and `403`:

```
Status code distribution:
  [200] 612 responses
  [403] 1388 responses
```

The `403`s are WAF blocking your IP. Confirm it in the WAF metrics:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/WAFV2 \
  --metric-name BlockedRequests \
  --dimensions Name=WebACL,Value=crunchWebAcl Name=Region,Value=us-east-1 Name=Rule,Value=rateLimit \
  --start-time "$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 60 \
  --statistics Sum
```

A non-zero `BlockedRequests` on the `rateLimit` rule is your evidence. Stop the load, wait out the 5-minute window, and a fresh request returns `200` again — the block is per-source and self-healing. That whole loop — trip it, observe the metric, watch it recover — is the deliverable for the challenge.

---

## 10. What you should be able to do now

- Trace a request from DNS to origin and name which service owns each hop.
- Choose the right Route 53 routing policy for blue/green, multi-region, and DR.
- Explain why you alias (not CNAME) to AWS resources and why it works at the apex.
- Stand up a CloudFront distribution with an ACM cert, remembering the cert lives in `us-east-1`.
- Attach a WAF web ACL with managed groups and a rate-based rule, and explain `action` vs `overrideAction`.
- Demonstrate the rate-based rule firing and recovering, with CloudWatch evidence.
- Decide, correctly, that you do not need Shield Advanced for this course.

Next we build it: Exercise 1 is the VPC, the challenge is the edge, and the mini-project fuses them into the network foundation every later week reuses.

---

*Reading checkpoint:* before the challenge, re-read §6 (WAF rate-based rule) and §9 (proving it fires). The single most common challenge failure is configuring the rule with `scope: 'REGIONAL'` when it should be `CLOUDFRONT`, or building the web ACL outside `us-east-1`. Get the scope and region right and the rest follows.
