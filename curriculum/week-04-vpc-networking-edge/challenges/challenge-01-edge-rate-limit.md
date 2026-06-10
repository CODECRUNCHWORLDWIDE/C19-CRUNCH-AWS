# Challenge 1 — Edge Rate-Limiting Under Load

**Time estimate:** ~2–3 hours.

## Problem statement

Stand up a complete edge: a **Route 53 alias** record pointing at a **CloudFront** distribution that serves a static "hello" page over **HTTPS** (TLS terminated with an **ACM-managed certificate**), with the CloudFront origin being an **ALB** in the public subnets of your Week-4 VPC. Attach an **AWS WAF** web ACL with a **rate-based rule**, then **demonstrate the rule firing under load** and recovering after the load stops.

You are reproducing the exact topology from Lecture 2:

```
Route 53 (app.<your-domain>)  ──alias──►  CloudFront distribution
                                            ├── ACM cert (us-east-1)
                                            ├── WAF web ACL (CLOUDFRONT scope, us-east-1)
                                            │     └── rate-based rule: 100 req / 5-min / IP → BLOCK
                                            └── origin: ALB (public subnet of the Week-4 VPC)
                                                  └── target: a trivial "hello" responder
```

The "hello" responder can be anything that returns HTTP 200 with a body — a single `t3.micro` running a one-line Python HTTP server, an ALB fixed-response rule, or an ECS task. The simplest correct answer is an **ALB listener fixed-response action** that returns `200 "hello from the edge"` with no compute at all. Use that unless you want the practice of wiring a target.

## Acceptance criteria

- [ ] A CDK app (TypeScript or Python) that deploys, on top of your Week-4 VPC:
  - An **internet-facing ALB** in the public subnets with a listener that produces a `200` "hello" response (fixed-response action is fine).
  - A **CloudFront distribution** whose origin is that ALB, with `viewerProtocolPolicy` set to `REDIRECT_TO_HTTPS`.
  - An **ACM certificate** in `us-east-1` for your `app.<your-domain>` name, **DNS-validated** via your Route 53 hosted zone.
  - A **Route 53 A (alias)** record `app.<your-domain>` → the CloudFront distribution.
  - A **WAF web ACL** with `scope: 'CLOUDFRONT'` (created in `us-east-1`) containing a **rate-based rule** with a limit of **100** requests per 5-minute window per IP, action `BLOCK`, plus `AWSManagedRulesCommonRuleSet` and `AWSManagedRulesAmazonIpReputationList` in `count` or `none` override.
- [ ] `curl https://app.<your-domain>/` returns `200` with your hello body, served over a valid TLS certificate (no cert warnings).
- [ ] `dig app.<your-domain>` shows the alias resolving to CloudFront edge addresses.
- [ ] **Under load**, a load tool (`hey` or `wrk`) shows a mix of `200` and `403` responses once you exceed the rate limit from a single source.
- [ ] The WAF CloudWatch metric `BlockedRequests` for your rate rule goes **non-zero** during the load and you capture the number.
- [ ] **After** the load stops and the 5-minute window passes, a fresh `curl` returns `200` again — proving the block is per-source and self-healing.
- [ ] A short `README.md` in `challenges/challenge-01/` with: the architecture sketch, the deploy commands, the exact load command you ran, the status-code histogram, and the `BlockedRequests` figure.
- [ ] `cdk destroy` cleanly removes everything (and you actually run it — CloudFront distributions take ~15 min to disable+delete; don't leave them).

## Fallback if you don't own a domain

Skip the ACM and Route 53 steps. CloudFront gives every distribution a free `*.cloudfront.net` domain with a valid AWS-managed certificate. Deploy the distribution with **no** `domainNames` and **no** custom certificate, and run all the load/proof steps against the assigned `dxxxx.cloudfront.net` hostname. You still demonstrate the WAF rate rule — you just don't practice the custom-domain + DNS-validation wiring. Note this substitution in your README.

## Hints

<details>
<summary>The ALB fixed-response "hello" — no compute needed</summary>

```typescript
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';

const alb = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
  vpc,                       // your Week-4 VPC
  internetFacing: true,
  vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
});

alb.addListener('Http', {
  port: 80,
  defaultAction: elbv2.ListenerAction.fixedResponse(200, {
    contentType: 'text/plain',
    messageBody: 'hello from the edge',
  }),
});
```

CloudFront talks to the ALB over HTTP (port 80) inside AWS; the TLS the user sees is terminated at CloudFront with the ACM cert. That's the standard and acceptable pattern for this challenge.
</details>

<details>
<summary>The us-east-1 problem in CDK</summary>

Both the ACM cert (for CloudFront) and the `CLOUDFRONT`-scoped WAF web ACL must be created in `us-east-1`. If your app runs elsewhere, put the cert + web ACL in a stack pinned to `us-east-1`:

```typescript
const edgeStack = new EdgeStack(app, 'CrunchEdgeUsEast1', {
  env: { account, region: 'us-east-1' },
  crossRegionReferences: true,   // lets the main-region stack consume these ARNs
});
```

`crossRegionReferences: true` on both the producing and consuming stacks lets CDK pass the cert ARN and web ACL ARN across regions via SSM parameters. Without it you'll hit "cannot reference a resource in a different region."
</details>

<details>
<summary>The WAF rate-based rule (L1 CfnWebACL)</summary>

```typescript
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';

const webAcl = new wafv2.CfnWebACL(this, 'WebAcl', {
  scope: 'CLOUDFRONT',                 // MUST be created in us-east-1
  defaultAction: { allow: {} },
  visibilityConfig: {
    cloudWatchMetricsEnabled: true,
    metricName: 'crunchEdge',
    sampledRequestsEnabled: true,
  },
  rules: [
    {
      name: 'RateLimit',
      priority: 0,
      action: { block: {} },
      statement: {
        rateBasedStatement: { limit: 100, aggregateKeyType: 'IP' },
      },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'rateLimit',
        sampledRequestsEnabled: true,
      },
    },
  ],
});

// Attach to the distribution:
const distribution = new cloudfront.Distribution(this, 'Cdn', {
  // ...origin/behavior/cert...
  webAclId: webAcl.attrArn,
});
```
</details>

<details>
<summary>Tripping and observing the limit</summary>

```bash
# Hammer it from one IP — 2000 requests, 50 concurrent.
hey -n 2000 -c 50 https://app.<your-domain>/

# Read the status histogram in hey's output. You want a mix of 200 and 403.

# Confirm in WAF metrics (us-east-1; CLOUDFRONT web ACL metrics report in us-east-1):
aws cloudwatch get-metric-statistics --region us-east-1 \
  --namespace AWS/WAFV2 --metric-name BlockedRequests \
  --dimensions Name=WebACL,Value=crunchEdge Name=Region,Value=CloudFront Name=Rule,Value=rateLimit \
  --start-time "$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 60 --statistics Sum
```

If you see all `200` and never a `403`, your `hey` run wasn't long/fast enough to cross 100 in a 5-minute window, or the limit is set too high. Increase `-n`/`-c` or lower the limit temporarily to 10 (the minimum) to make the demonstration crisp.
</details>

## Stretch

- Add a **second** rate rule keyed on `FORWARDED_IP` instead of `IP` and explain (in your README) why `FORWARDED_IP` is the correct key behind CloudFront — the `IP` aggregate sees CloudFront's edge IPs, not the real client. Demonstrate the difference.
- Add a **geolocation** custom rule that blocks one country and prove it (use a VPN exit node or an `X-Forwarded-For` override in a test request).
- Replace the ALB fixed-response with a real **CloudFront Function** that returns the hello page at the edge with no origin at all, and compare the latency.
- Turn the static page into an **S3 origin with OAC** instead of an ALB and keep the bucket fully private.

## Why this matters

The Route 53 → CloudFront → WAF → origin path is the front door of nearly every production web system on AWS. The rate-based rule is the cheapest, highest-leverage protection you can deploy — it stops credential-stuffing, scraping, and small floods before they reach your application, for cents. Every later week in this course that exposes anything to the internet (the EKS service in Week 5, the serverless API in Week 6, the capstone in Week 13) sits behind this exact pattern. Build it once here, correctly, and you'll reuse it for the rest of the course.

## Submission

Commit your `challenge-01/` CDK app and `README.md` to your Week-4 GitHub repo. The README must contain the load command, the status-code histogram showing `403`s, and the non-zero `BlockedRequests` metric. Then **run `cdk destroy`** and confirm the CloudFront distribution is gone — a forgotten distribution doesn't bill much, but a forgotten ALB and the WAF web ACL do.
