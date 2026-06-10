# Lecture 2 — The Edge: CloudFront Functions vs Lambda@Edge vs Global Accelerator, and What Each Costs

> **Reading time:** ~80 minutes. **Hands-on time:** ~75 minutes (you stand up CloudFront over an API origin, add a CloudFront Function and a Lambda@Edge function, and watch a request flow through both).

Lecture 1 taught you to put a dollar on every decision. This lecture is where that habit earns its keep, because the edge is a place engineers casually spend 6× more than they need to by running the wrong logic in the wrong tier. The edge has *three* compute options on AWS — CloudFront Functions, Lambda@Edge, and Global Accelerator — and they differ on what they can do, where in the request lifecycle they run, and what they cost by **two orders of magnitude**. By the end you will be able to look at a piece of edge logic and say, without hesitation, "that's a CloudFront Function" or "that needs Lambda@Edge" or "that's a Global Accelerator job," and attach the per-million-requests cost to the choice. You will also build the exact edge layer the capstone spec mandates: CloudFront + WAF, a CloudFront Function for header rewrites, and a Lambda@Edge function that injects a tenant header from a signed cookie.

## 2.1 — Why an edge tier at all

CloudFront is AWS's CDN: a global fleet of edge locations that sit between your users and your origin (the API Gateway / ALB / S3 your capstone serves). Three reasons it earns a place in front of the capstone:

1. **Latency.** The edge terminates TLS close to the user and serves cacheable responses without a round trip to the origin Region. A user in Tokyo hits a Tokyo edge, not your `us-east-1` ALB.
2. **Cost.** Data transfer *out of CloudFront* is cheaper than data transfer *out of an origin* (EC2/ALB/S3), and cache hits never touch the origin at all — every cached response is origin compute and transfer you didn't pay for. A well-cached edge *reduces* the bill; this is why edge belongs in a FinOps week.
3. **Security and control.** CloudFront is where WAF attaches, where you enforce TLS and HTTP/3, where you do header/cache-key normalization, and where you run tenant-routing logic *before* a request ever reaches your application. The capstone's WAF managed rules and rate-limit rule live here.

But the moment you want *logic* at the edge — rewrite this header, route this tenant, verify this cookie — you must choose a compute tier, and that choice is the heart of the lecture.

## 2.2 — The request lifecycle: four trigger points

To choose correctly you must know *where in the request lifecycle* each edge function can run. A CloudFront request has four interception points:

```
   User                  CloudFront edge                       Origin (API GW / ALB)
    │                          │                                      │
    │ ── request ───────────►  │                                      │
    │                  (1) VIEWER REQUEST   ◄── CF Function or L@E    │
    │                          │  cache lookup...                     │
    │                          │ ── (cache miss) ──────────────────►  │
    │                  (3) ORIGIN REQUEST   ◄── Lambda@Edge only      │
    │                          │                                      │ ── process ──►
    │                          │ ◄── origin response ─────────────────│
    │                  (4) ORIGIN RESPONSE  ◄── Lambda@Edge only      │
    │                          │  ...store in cache                   │
    │                  (2) VIEWER RESPONSE  ◄── CF Function or L@E    │
    │ ◄── response ──────────  │                                      │
```

- **Viewer request (1)** — runs on *every* request, before the cache lookup. The hot path. Whatever runs here runs on every viewer, cache hit or miss.
- **Origin request (3)** — runs only on a *cache miss*, just before CloudFront calls the origin. Much lower volume (cache hits skip it).
- **Origin response (4)** — runs on a cache miss, after the origin replies, before caching.
- **Viewer response (2)** — runs on every response to the viewer, just before it's sent.

The two tiers map onto these points differently, and that mapping is half the decision:

| Trigger point | CloudFront Function | Lambda@Edge |
|---|---|---|
| Viewer request (1) | ✅ | ✅ |
| Viewer response (2) | ✅ | ✅ |
| Origin request (3) | ❌ | ✅ |
| Origin response (4) | ❌ | ✅ |

**CloudFront Functions run only at the viewer tier (1 and 2).** **Lambda@Edge runs at all four**, and is the *only* option at the origin tier (3 and 4). That's not arbitrary: viewer-tier logic must be blisteringly fast because it runs on every request, so AWS restricts it to a tiny, sandboxed runtime; origin-tier logic runs less often and can afford a full runtime.

## 2.3 — CloudFront Functions: sub-millisecond, viewer-only, dirt cheap

A **CloudFront Function** is a small **JavaScript** (ECMAScript 5.1-ish, a constrained `cloudfront-js` runtime) program that runs at the viewer tier in **sub-millisecond** time. It is designed for one thing: **fast, simple, high-volume transforms of the request or response** — header manipulation, URL rewrites, cache-key normalization, redirects, simple auth-token presence checks, A/B cookie assignment.

Its constraints are the price of its speed:

- **No network access.** It cannot call other AWS services or the internet. (The one exception, added because it's so common: it can read from a **CloudFront KeyValueStore** — a small, in-region key-value lookup — without a network call.)
- **No filesystem, tiny runtime, ~1 ms max, ~10 KB code, ~2 MB memory.** It is for transformation, not computation.
- **Viewer request/response only.**

Here is a CloudFront Function that normalizes a cache key and rewrites a header — the kind of thing the capstone uses to keep the cache efficient. It lowercases the `Host`-derived cache key and strips a tracking query param so two URLs that should share a cache entry actually do:

```javascript
// CloudFront Function (cloudfront-js-2.0 runtime). Runs at VIEWER REQUEST.
function handler(event) {
    var request = event.request;

    // 1) Cache-key hygiene: drop a tracking param so '/p?id=1&utm=x' and
    //    '/p?id=1' share one cache entry instead of fragmenting the cache.
    if (request.querystring['utm_source']) {
        delete request.querystring['utm_source'];
    }

    // 2) Add a header the origin can trust came from the edge (CF strips
    //    client-supplied copies because this runs after CF normalizes input).
    request.headers['x-edge-processed'] = { value: 'cloudfront-function' };

    // 3) A cheap redirect: force the apex onto www without an origin round trip.
    var host = request.headers['host'].value;
    if (host === 'example.com') {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: { 'location': { value: 'https://www.example.com' + request.uri } }
        };
    }

    return request; // pass through to the cache/origin
}
```

**Cost:** CloudFront Functions bill **per million invocations** at roughly **$0.10 per 1M** (verify current pricing) — and that's *it*; no duration charge. At a billion requests a month that's $100. This is the cheapest compute AWS offers, and it's why the rule is: **if it can be a CloudFront Function, make it a CloudFront Function.**

## 2.4 — Lambda@Edge: the full runtime at the origin tier

When the viewer-tier sandbox isn't enough — you need to **call the network** (DynamoDB, Secrets Manager, an auth service), run a **real runtime** (Node.js or Python with libraries), handle a **larger payload**, or intercept at the **origin tier** — you reach for **Lambda@Edge**. It is a regular Lambda function (Node or Python only) that CloudFront replicates to edge locations and runs at one of the four trigger points.

Its capabilities and costs are the mirror image of CloudFront Functions:

- **Full Node/Python runtime**, network access, larger code (up to 1 MB for viewer triggers, 50 MB for origin triggers), more memory, longer execution (up to 5 s viewer / 30 s origin).
- **Runs at all four trigger points** — and is the only edge compute that can touch the origin request/response.
- **Cost:** ~**$0.60 per 1M requests** *plus* a duration charge (GB-seconds), so **~6×+ the per-request price of a CloudFront Function before duration.** It also adds a few milliseconds of latency (it's a real function invocation, not a 1 ms transform), and a **cold start** on first use at each edge.

The capstone's mandated edge job — **inject a tenant header from a signed cookie** — is a *Lambda@Edge* job, not a CloudFront Function job, because it requires cryptographic verification of a signed cookie and (optionally) a lookup, which exceeds the viewer-tier sandbox. Here it is at the **viewer request** trigger, in Python:

```python
# Lambda@Edge, Python, VIEWER REQUEST trigger.
# Injects 'x-tenant-id' from a signed cookie so the origin can route by tenant
# WITHOUT trusting a client-supplied header. Must be deployed in us-east-1.
import base64
import hashlib
import hmac
import json
import os

# In real code the secret comes from a baked-in config or SSM-at-build, because
# Lambda@Edge cannot read environment variables at runtime. We embed a key id and
# verify against a public key / shared secret provisioned at deploy time.
SIGNING_SECRET = b"REPLACE_AT_DEPLOY_TIME_FROM_SSM"  # see note below on config


def _verify(tenant: str, sig_b64: str) -> bool:
    """Constant-time HMAC verification of the tenant cookie."""
    expected = hmac.new(SIGNING_SECRET, tenant.encode(), hashlib.sha256).digest()
    try:
        provided = base64.urlsafe_b64decode(sig_b64 + "==")
    except Exception:
        return False
    return hmac.compare_digest(expected, provided)


def _parse_cookies(headers: dict) -> dict:
    out = {}
    for h in headers.get("cookie", []):
        for pair in h["value"].split(";"):
            if "=" in pair:
                k, v = pair.strip().split("=", 1)
                out[k] = v
    return out


def handler(event, context):
    request = event["Records"][0]["cf"]["request"]
    cookies = _parse_cookies(request["headers"])

    tenant = cookies.get("tenant", "")
    sig = cookies.get("tenant_sig", "")

    if tenant and sig and _verify(tenant, sig):
        # Trusted: inject the header the origin will route on.
        request["headers"]["x-tenant-id"] = [{"key": "X-Tenant-Id", "value": tenant}]
    else:
        # Untrusted/missing: strip any client-supplied copy so the origin can't be
        # tricked into trusting a forged tenant header.
        request["headers"].pop("x-tenant-id", None)
        # Optionally short-circuit unauthenticated tenants:
        return {
            "status": "401",
            "statusDescription": "Unauthorized",
            "headers": {"content-type": [{"key": "Content-Type", "value": "application/json"}]},
            "body": json.dumps({"error": "invalid or missing tenant cookie"}),
        }

    return request
```

Two senior-grade details in that function:

1. **It strips the client-supplied `x-tenant-id` on the untrusted path.** A naive implementation only *adds* the header when the cookie is valid and forgets that a malicious client can send `X-Tenant-Id: victim-tenant` directly. The edge function must *overwrite or remove* the client copy so the origin can trust the header absolutely. This is the whole security value of doing tenant routing at the edge: the origin never sees an unverified tenant claim.

2. **Lambda@Edge cannot read environment variables at runtime.** This is a real restriction people hit constantly. You bake configuration into the deployment package (or fetch it once and cache it in the execution environment), or read from SSM/Secrets Manager *inside the handler* on cold start and cache it. The CDK `EdgeFunction` construct and a build-time config-injection step are the usual pattern; the exercise shows one.

### The Lambda@Edge deployment wrinkle: us-east-1 only

Lambda@Edge functions **must be created in `us-east-1`** (CloudFront replicates them out from there). In CDK, that means either deploying the whole stack to `us-east-1` or using the `cloudfront.experimental.EdgeFunction` construct, which provisions the function in `us-east-1` via a cross-region support stack even when your main stack is elsewhere:

```typescript
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as lambda from 'aws-cdk-lib/aws-lambda';

// EdgeFunction handles the us-east-1 placement for you, even from another region.
const tenantFn = new cloudfront.experimental.EdgeFunction(this, 'TenantInjector', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'index.handler',
  code: lambda.Code.fromAsset('lambda/tenant-injector'),
});

// ...associate it in the distribution's default behavior (below).
```

There are also **no environment variables, no `$LATEST` (you associate a specific version), and replication takes a few minutes** — so the edit/deploy loop for Lambda@Edge is slower than ordinary Lambda. Develop the logic as a normal Lambda you can iterate on fast, then promote it to the edge.

## 2.5 — The decision: CF Function vs Lambda@Edge

Here is the decision table to tattoo next to Week 11's SageMaker-modes one:

| Question | If yes → | |
|---|---|---|
| Does it need network access (call DynamoDB/Secrets/an API)? | **Lambda@Edge** | CF Functions can't reach the network (except KeyValueStore). |
| Does it run at the **origin** tier (origin request/response)? | **Lambda@Edge** | CF Functions are viewer-tier only. |
| Does it need a real runtime / libraries / >10 KB code? | **Lambda@Edge** | CF Functions are a tiny JS sandbox. |
| Is it a fast header/URL/cache-key transform on every request? | **CloudFront Function** | Sub-ms, ~$0.10/1M, no duration charge. |
| Is it a simple in-region key lookup? | **CF Function + KeyValueStore** | No network call needed. |

The cost discipline distilled: **push as much logic as possible into the cheap viewer-tier CloudFront Function, and use Lambda@Edge only for the part that genuinely needs the full runtime.** For the capstone, that means the *cache-key/header normalization* is a CloudFront Function (every request, must be cheap) and only the *signed-cookie verification + tenant injection* is Lambda@Edge (needs crypto/lookup). Splitting it that way instead of doing everything in Lambda@Edge can cut the edge-compute bill by 80%+ when most requests are cache hits that never need the expensive tier. *That* is cost-as-a-feature.

## 2.6 — Global Accelerator: the other edge, for the non-HTTP case

Neither CloudFront nor its functions help a workload that isn't HTTP — a game server on UDP, a gRPC streaming service, an IoT MQTT broker, or anything that needs a **static anycast IP** that doesn't change. That's **AWS Global Accelerator**.

Global Accelerator gives you **two static anycast IP addresses** advertised from the AWS edge worldwide. A user's traffic enters the **AWS global network at the nearest edge** and rides AWS's backbone to your origin Region — avoiding the public internet's congestion and variability for most of the path. It does TCP/UDP (not just HTTP), does **fast regional failover** (sub-minute, on health checks), and gives you those fixed IPs (useful for IP allow-lists and DNS that can't change).

The decision between CloudFront and Global Accelerator:

- **CloudFront** — HTTP/HTTPS, **caching**, content delivery, edge functions, WAF. If it's web/API traffic that can be cached or transformed, it's CloudFront.
- **Global Accelerator** — **non-HTTP protocols, static IPs, or pure network-path acceleration with no caching.** TCP/UDP, fast failover, IP-allowlist needs.

**Cost shape differs too:** CloudFront is pay-per-use (requests + transfer, $0 at idle). Global Accelerator has a **fixed hourly charge per accelerator (~$0.025/hr ≈ ~$18/month)** plus a per-GB data-transfer *premium* on top of normal transfer. So GA has a floor cost CloudFront doesn't — another dollar to weigh. For the capstone's *HTTP API*, CloudFront is correct; the stretch goal fronts a non-HTTP component with GA precisely to feel the difference.

## 2.7 — WAF at the edge: managed rules + a rate limit

The capstone spec requires **WAF managed rules + a custom rate-limit rule** on the edge. AWS WAF attaches to the CloudFront distribution as a **web ACL** and inspects every request before it reaches your origin or edge functions.

Two pieces you build:

- **Managed rule groups** — AWS-curated rule sets (the Core Rule Set, Known Bad Inputs, IP reputation, SQLi/XSS). You enable them and they block the bulk of common attacks for a per-rule fee. Start with `AWSManagedRulesCommonRuleSet` and `AWSManagedRulesKnownBadInputsRuleSet`.
- **A custom rate-based rule** — counts requests per source IP over a 5-minute window and blocks a source above a threshold. The capstone's "custom rate-limit rule":

```typescript
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';

// WAF for CloudFront must be created with scope CLOUDFRONT in us-east-1.
new wafv2.CfnWebACL(this, 'EdgeWebAcl', {
  scope: 'CLOUDFRONT',
  defaultAction: { allow: {} },
  visibilityConfig: {
    cloudWatchMetricsEnabled: true,
    metricName: 'edge-web-acl',
    sampledRequestsEnabled: true,
  },
  rules: [
    {
      name: 'AWSCommon',
      priority: 0,
      overrideAction: { none: {} },
      statement: {
        managedRuleGroupStatement: {
          vendorName: 'AWS',
          name: 'AWSManagedRulesCommonRuleSet',
        },
      },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'aws-common',
        sampledRequestsEnabled: true,
      },
    },
    {
      name: 'RateLimit',
      priority: 1,
      action: { block: {} },                 // block the offending source
      statement: {
        rateBasedStatement: {
          limit: 2000,                        // requests per 5-min window per source IP
          aggregateKeyType: 'IP',
        },
      },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'rate-limit',
        sampledRequestsEnabled: true,
      },
    },
  ],
});
```

Note `scope: 'CLOUDFRONT'` and the **us-east-1 requirement** — WAF for CloudFront, like Lambda@Edge and the CUR, is a us-east-1 global resource. The rate-based rule's `limit` is per 5-minute sliding window; tune it to your real traffic so you block abuse without blocking a legitimate burst.

## 2.8 — Origin failover: the edge's high availability

The last edge capability the capstone needs is **origin failover**. CloudFront lets you define an **origin group** — a *primary* and a *secondary* origin — and configure which status codes (e.g. `500, 502, 503, 504`, or connection failures) trigger a failover. When the primary returns a failover-triggering response, CloudFront *automatically retries the request against the secondary* before returning an error to the user.

This is the edge layer of your multi-region DR (Week 13). If your primary origin is the `us-east-1` ALB and your secondary is the `us-west-2` failover stack, CloudFront fails reads over to the standby Region at the edge, transparently, without a Route 53 DNS-TTL wait. In CDK:

```typescript
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';

const primary = new origins.HttpOrigin('api.primary.example.com');
const secondary = new origins.HttpOrigin('api.failover.example.com');

new cloudfront.Distribution(this, 'EdgeDist', {
  defaultBehavior: {
    origin: new origins.OriginGroup({
      primaryOrigin: primary,
      fallbackOrigin: secondary,
      fallbackStatusCodes: [500, 502, 503, 504], // fail over on origin errors
    }),
    viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
  },
  webAclId: edgeWebAcl.attrArn, // attach the WAF web ACL from above
});
```

The Friday challenge has you **prove this works by killing the primary origin** while traffic flows and watching CloudFront serve from the secondary — the same muscle Week 15's chaos drill exercises when "CloudFront origin failure" is your bonus drill. Note the constraint: origin failover triggers on *idempotent* methods (GET/HEAD/OPTIONS by default for the retry); a non-idempotent POST is not automatically retried, because retrying a write could double-apply it. Design accordingly.

## 2.9 — Putting it together: the capstone edge tier

Stacking everything this lecture covered, the capstone's edge looks like:

```
   User
    │
    ▼
  CloudFront distribution  ── ACM TLS, HTTP/3 ──┐
    │                                            │
    ├─ WAF web ACL (managed rules + rate limit)  │  ← inspect every request
    │
    ├─ Viewer request:
    │     ├─ CloudFront Function: cache-key/header normalization   ($0.10/1M)
    │     └─ Lambda@Edge: verify signed cookie, inject x-tenant-id ($0.60/1M + dur)
    │
    ├─ Cache (hit → return without touching origin = $0 origin cost)
    │
    └─ Origin group (miss):
          primary  → us-east-1 API origin
          fallback → us-west-2 failover origin   ← origin failover on 5xx
```

Every box has a dollar on it, and the architecture is *shaped by those dollars*: cheap logic in the CloudFront Function, expensive logic only in Lambda@Edge, caching to keep requests off the origin entirely, and WAF/failover for safety. That is the cost-as-a-feature mindset made concrete, and it is exactly what the mini-project asks you to build in front of the capstone API.

## 2.10 — Open-source / multi-cloud comparators (what you traded away)

- **Cloudflare Workers** — V8-isolate edge compute. Unlike Lambda@Edge it has *near-zero cold start* (isolates, not containers) and can do network calls cheaply, blurring the CF-Function/Lambda@Edge split into one tier. If your edge logic is heavy and latency-critical, Workers' model is genuinely different; the trade is leaving the AWS-integrated world (WAF, signed cookies, origin failover all become Cloudflare equivalents).
- **Fastly Compute** — WebAssembly at the edge. You compile (Rust/Go/JS/etc.) to Wasm and run it with very low cold-start; the model rewards CPU-heavier edge logic than CloudFront Functions allow. Again, you trade AWS integration for a different performance/cost envelope.

The pattern, one last time: AWS gives you a *two-tier* edge (cheap-and-limited vs full-and-costlier) tightly integrated with the rest of AWS; the competitors collapse that into a single isolate/Wasm tier with different cold-start economics. Know the shape so you can defend the choice — and so when someone says "just use Workers," you can say exactly what you'd gain and lose.

## 2.11 — What you should be able to do now

- Name the four CloudFront trigger points and which tier each edge compute can run at.
- Choose CloudFront Function vs Lambda@Edge from the network/origin-tier/runtime questions, and attach the per-1M cost to the choice.
- Write a CloudFront Function for cache-key/header normalization and explain why it's cheap.
- Write a Lambda@Edge tenant-injector that *strips* the untrusted client header, and recall the us-east-1 / no-env-var / replication constraints.
- Pick Global Accelerator over CloudFront for non-HTTP / static-IP / pure-acceleration needs, and state its fixed-hourly cost floor.
- Attach a WAF web ACL with a managed rule group and a rate-based rule (scope CLOUDFRONT, us-east-1).
- Configure CloudFront origin failover with an origin group and explain the idempotent-method caveat.

## 2.12 — The challenge that goes with this lecture

**Challenge 1 — Edge + WAF + origin failover + the cost decision.** Put WAF managed rules and a rate-based rule on your CloudFront distribution, configure origin failover, prove failover by killing the primary origin while traffic flows, and write the cost-as-a-feature decision doc that justifies *which logic you placed in which tier and why*, with the per-million-requests numbers. The acceptance criteria are in `challenges/challenge-01-edge-waf-origin-failover-cost.md`. Bring real numbers — the same discipline as Lecture 1.
