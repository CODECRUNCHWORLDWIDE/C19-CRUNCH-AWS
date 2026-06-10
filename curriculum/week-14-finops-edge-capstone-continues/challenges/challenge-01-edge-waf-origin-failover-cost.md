# Challenge 1 — Harden the Edge with WAF + Origin Failover, Prove It, and Write the Cost-as-a-Feature Decision

> **Estimated time:** 2.5–3 hours. This is the week's synthesis: the edge tier made production-grade and *defensible with numbers*. It is also the exact architecture the capstone's frontend/edge layer requires, and the origin-failover machinery you build here is what Week 15's "CloudFront origin failure" chaos drill exercises.

## The problem

You have a CloudFront distribution (from Exercise 3) with a CloudFront Function for cache-key hygiene and a Lambda@Edge function that injects a trusted `x-tenant-id` from a signed cookie. That is the *logic* tier. It is not yet *production*: it has no WAF in front of it, and it has a single origin — if that origin's Region goes down, the edge has nowhere to fail over to.

Your job: add **AWS WAF** (managed rules + a custom rate-based rule) and **CloudFront origin failover** (an origin group with a primary and a secondary), then **prove the failover works** by killing the primary origin while traffic flows and watching CloudFront serve from the secondary. Finally, write a `DECISION.md` that justifies — with the per-million-requests cost numbers — *which edge logic you placed in which tier and why*, and what the whole edge layer costs at a stated traffic profile.

The senior skill being tested is the same as Week 11's: holding "this costs X" and "this protects/accelerates Y" in your head at once and producing an edge design you can defend, not just one that works.

## What you build

1. **A WAF web ACL** (scope `CLOUDFRONT`, in `us-east-1`) attached to your distribution, containing:
   - At least one **managed rule group** (e.g. `AWSManagedRulesCommonRuleSet` and `AWSManagedRulesKnownBadInputsRuleSet`).
   - A **custom rate-based rule** that blocks a source IP exceeding a threshold per 5-minute window.
2. **An origin group** on the default behavior: a **primary** origin (your capstone API / Exercise 3 origin) and a **secondary** failover origin (a second API Gateway, a second Region's ALB, or even a static S3 "maintenance" origin), failing over on `5xx`/connection errors.
3. **A failover proof**: a captured terminal session (or screenshots) showing requests succeeding against the primary, then the primary made to fail (disable it / return 503), then requests *still succeeding* — served from the secondary — without client-visible error.
4. **A written `DECISION.md`** with the cost-as-a-feature analysis.

## Starter: the WAF web ACL via CLI

WAF for CloudFront is a `us-east-1`, `CLOUDFRONT`-scope resource. Create the web ACL, then associate its ARN with the distribution.

```bash
export REGION=us-east-1
cat > web-acl.json <<'JSON'
{
  "Name": "c19-wk14-edge-acl",
  "Scope": "CLOUDFRONT",
  "DefaultAction": { "Allow": {} },
  "VisibilityConfig": {
    "SampledRequestsEnabled": true,
    "CloudWatchMetricsEnabled": true,
    "MetricName": "c19-wk14-edge-acl"
  },
  "Rules": [
    {
      "Name": "AWSCommon",
      "Priority": 0,
      "OverrideAction": { "None": {} },
      "Statement": { "ManagedRuleGroupStatement": {
        "VendorName": "AWS", "Name": "AWSManagedRulesCommonRuleSet" } },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true, "CloudWatchMetricsEnabled": true,
        "MetricName": "aws-common" }
    },
    {
      "Name": "RateLimit",
      "Priority": 1,
      "Action": { "Block": {} },
      "Statement": { "RateBasedStatement": { "Limit": 1000, "AggregateKeyType": "IP" } },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true, "CloudWatchMetricsEnabled": true,
        "MetricName": "rate-limit" }
    }
  ]
}
JSON

aws wafv2 create-web-acl --region "$REGION" --cli-input-json file://web-acl.json
# Capture the returned ARN, then attach it to the distribution by setting
# DistributionConfig.WebACLId = <arn> and calling update-distribution (use the
# get-distribution-config + update-distribution ETag flow from Exercise 3).
```

The `RateBasedStatement.Limit` is per 5-minute sliding window per source IP. Set it low enough to trip in your test but high enough not to block normal use; 1000 is a reasonable lab value you can exceed with a `for` loop.

## Starter: prove the rate limit

```bash
# Hammer the distribution from one IP and watch WAF start returning 403 once you
# cross the threshold within the 5-minute window.
DOMAIN="d1234abcd.cloudfront.net"
for i in $(seq 1 1200); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://${DOMAIN}/")
  echo "$i $code"
done | tail -40   # you should see 200s flip to 403s as the limit trips
```

## Starter: origin failover with an origin group

Update the distribution to use an `OriginGroup` instead of a single origin on the default behavior. The relevant slice of the distribution config:

```json
{
  "Origins": { "Quantity": 2, "Items": [
    { "Id": "primary",   "DomainName": "primary-api.example.com",  "CustomOriginConfig": {"HTTPPort":80,"HTTPSPort":443,"OriginProtocolPolicy":"https-only","OriginSslProtocols":{"Quantity":1,"Items":["TLSv1.2"]}} },
    { "Id": "secondary", "DomainName": "failover-api.example.com", "CustomOriginConfig": {"HTTPPort":80,"HTTPSPort":443,"OriginProtocolPolicy":"https-only","OriginSslProtocols":{"Quantity":1,"Items":["TLSv1.2"]}} }
  ]},
  "OriginGroups": { "Quantity": 1, "Items": [{
    "Id": "api-group",
    "FailoverCriteria": { "StatusCodes": { "Quantity": 4, "Items": [500, 502, 503, 504] } },
    "Members": { "Quantity": 2, "Items": [ { "OriginId": "primary" }, { "OriginId": "secondary" } ] }
  }]},
  "DefaultCacheBehavior": { "TargetOriginId": "api-group", "...": "..." }
}
```

The `TargetOriginId` of the behavior points at the **origin group** id, not an individual origin. Failover triggers on the listed status codes (and connection failures/timeouts).

## Prove the failover

1. Confirm steady-state: `curl` the distribution a few times, all `200`, and (if your origin echoes it) note which origin served — primary.
2. **Break the primary.** Make it return a failover code: disable the primary API stage, point it at a deleted Lambda, or have it return `503`. (Killing the *whole* origin — connection refused — also triggers failover.)
3. `curl` again. You should still get `200` (or your secondary's response), served from the **secondary**. Capture this — the request succeeding *while the primary is down* is the proof.
4. **The idempotency caveat:** test with `GET`. CloudFront does not auto-retry non-idempotent `POST`/`PUT`/`PATCH` to the failover origin, because retrying a write could double-apply it. Note this in `DECISION.md` — it shapes how you design write paths behind a failover-protected edge.

## Acceptance criteria

- [ ] A WAF web ACL (scope `CLOUDFRONT`, `us-east-1`) with at least one managed rule group **and** a rate-based rule, attached to the distribution.
- [ ] A demonstrated rate-limit trip: captured output showing `200`s flipping to `403`s once the per-IP limit is exceeded.
- [ ] An origin group with a primary + secondary and a `FailoverCriteria` on `5xx`.
- [ ] A **proven failover**: captured evidence of requests succeeding from the secondary *while the primary is down*.
- [ ] The Lambda@Edge tenant injector and CloudFront Function from Exercise 3 still work (cookie → trusted `x-tenant-id`; no cookie → 401).
- [ ] A `DECISION.md` containing:
  - The **per-1M-requests cost** of each edge tier you used (CloudFront Function ~$0.10/1M; Lambda@Edge ~$0.60/1M + duration; WAF per-rule + per-1M-inspected; verify current figures and cite the date), and a justification of **which logic you placed in which tier and why** — including at least one piece of logic you *deliberately kept in the cheaper CloudFront Function* to control cost.
  - The estimated **monthly edge cost** of the whole layer (CloudFront requests + transfer + functions + WAF) at a stated traffic profile (e.g. 5M requests/month, 60% cache-hit).
  - The **idempotency caveat** for failover and how your write path accounts for it.
  - One sentence on when you'd reach for **Global Accelerator** instead of (or alongside) CloudFront for a capstone component, with its fixed-hourly cost floor noted.
- [ ] Teardown: distribution disabled+deleted (or kept for the mini-project and noted), WAF web ACL deleted or its monthly cost acknowledged, edge functions disassociated.

## Stretch

- Replace the Lambda@Edge tenant lookup with a **CloudFront KeyValueStore + CloudFront Function** where the tenant data is a simple key lookup (no crypto), and document the latency and cost difference — you may be able to drop the expensive tier entirely for the common case.
- Add a **CloudFront origin-failover CloudWatch alarm** (on the `OriginLatency`/5xx metrics) so a failover *pages someone* — wiring the edge into the Week-12 observability stack.
- Put a **Budgets action** behind the WAF: if the edge layer's tagged monthly cost breaches a threshold, auto-notify the owning team — closing the FinOps loop on the edge spend itself.

## What "good" looks like

A strong `DECISION.md` reads like a real design-review artifact: it states the per-tier numbers, shows *why* the cache-key rewrite is a CloudFront Function and the cookie-verify is Lambda@Edge (and what it would have cost to do everything in Lambda@Edge), proves the failover with captured evidence, and names the idempotency and Global-Accelerator trade-offs without being asked. A weak submission says "I added WAF and failover, it works" with no cost number and no proof the failover fired. The whole course is built to make you the first kind of engineer.
