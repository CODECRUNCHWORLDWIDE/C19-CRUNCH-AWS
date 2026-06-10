#!/usr/bin/env python3
"""
Exercise 3 — Stand up a CloudFront distribution in front of an API origin with a
CloudFront Function (cheap, viewer-tier header/cache-key rewrite) AND a
Lambda@Edge function (signed-cookie verification -> x-tenant-id injection), and
watch a request flow through both edge tiers.

Estimated time: ~90 minutes (CloudFront distribution + Lambda@Edge replication
are both slow to deploy -- budget for 10-20 minutes of "Deploying..." waits).
Cost: a few cents of CloudFront requests/transfer + Lambda@Edge invocations.
      An idle distribution is ~free; DISABLE + DELETE it (and disassociate the
      edge functions) when you finish -- the script's last step walks the
      teardown, which is multi-step because edge functions replicate globally.

WHY A SCRIPT INSTEAD OF CDK FOR THE EXERCISE
--------------------------------------------
The mini-project does this in CDK (the capstone needs IaC). This exercise uses
boto3 so you SEE each primitive -- the CloudFront Function, the Lambda@Edge
function with its us-east-1 placement, the function associations, the origin --
without the CDK construct hiding them. Build it once by hand here; pin it in CDK
in the mini-project.

WHAT THIS DOES
--------------
  1. Publishes a CLOUDFRONT FUNCTION (viewer request) that strips a tracking
     query param (cache-key hygiene) and stamps an x-edge-processed header.
  2. Deploys a LAMBDA@EDGE function (Python, in us-east-1) that verifies an
     HMAC-signed 'tenant' cookie and injects a trusted x-tenant-id header,
     stripping any client-supplied copy on the untrusted path.
  3. Creates a CloudFront distribution over an HTTP origin you provide
     (your capstone API, or the API Gateway echo described in the README),
     associating BOTH functions on the default behavior.
  4. Prints the distribution domain and how to test that a request flows
     through both tiers (curl with and without a valid cookie).
  5. Walks the (multi-step) teardown.

HOW TO RUN
----------
    python -m venv .venv && source .venv/bin/activate
    pip install boto3
    export REGION=us-east-1          # Lambda@Edge MUST be created here
    export ORIGIN_DOMAIN="your-api-id.execute-api.us-east-1.amazonaws.com"
    export TENANT_SIGNING_SECRET="dev-shared-secret-change-me"
    export LAMBDA_EDGE_ROLE_ARN="arn:aws:iam::<acct>:role/c19-wk14-edge-role"
    python exercise-03-cloudfront-edge-tenant-header.py deploy
    # ... test (see printed instructions) ...
    python exercise-03-cloudfront-edge-tenant-header.py teardown

THE EDGE ROLE (create once)
---------------------------
Lambda@Edge needs a role trusted by BOTH lambda.amazonaws.com and
edgelambda.amazonaws.com. Trust policy:
    {"Version":"2012-10-17","Statement":[{"Effect":"Allow",
     "Principal":{"Service":["lambda.amazonaws.com","edgelambda.amazonaws.com"]},
     "Action":"sts:AssumeRole"}]}
Attach AWSLambdaBasicExecutionRole for CloudWatch Logs (logs land in the REGION
NEAREST THE VIEWER, not us-east-1 -- a classic Lambda@Edge debugging gotcha).

ACCEPTANCE CRITERIA
-------------------
  [ ] A CloudFront Function is published and associated at viewer-request.
  [ ] A Lambda@Edge function is deployed in us-east-1 and associated at
      viewer-request (a specific VERSION ARN, not $LATEST).
  [ ] A request WITHOUT a valid tenant cookie is rejected (401) by the edge.
  [ ] A request WITH a valid signed cookie reaches the origin carrying a trusted
      x-tenant-id header (verify by echoing headers at the origin).
  [ ] You note the per-1M cost of each tier and which logic you placed where.
  [ ] Teardown leaves no enabled distribution and no orphaned edge functions.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import sys
import time
import zipfile

import boto3

REGION = os.environ.get("REGION", "us-east-1")
ORIGIN_DOMAIN = os.environ.get("ORIGIN_DOMAIN", "example-origin.execute-api.us-east-1.amazonaws.com")
SIGNING_SECRET = os.environ.get("TENANT_SIGNING_SECRET", "dev-shared-secret-change-me")
EDGE_ROLE_ARN = os.environ.get("LAMBDA_EDGE_ROLE_ARN", "")

CF_FUNCTION_NAME = "c19-wk14-cachekey"
EDGE_FN_NAME = "c19-wk14-tenant-injector"
CALLER_REF = "c19-wk14-edge"

# Lambda@Edge and CloudFront are global; their control-plane lives in us-east-1.
cf = boto3.client("cloudfront", region_name="us-east-1")
lam = boto3.client("lambda", region_name="us-east-1")


# --- the CloudFront Function source (cloudfront-js-2.0, runs at VIEWER REQUEST) -
CF_FUNCTION_CODE = """
function handler(event) {
    var request = event.request;
    // Cache-key hygiene: '/p?id=1&utm_source=x' and '/p?id=1' should share a
    // cache entry. Dropping the tracking param prevents cache fragmentation.
    if (request.querystring['utm_source']) { delete request.querystring['utm_source']; }
    // Stamp a header so the origin can tell the request was edge-processed.
    request.headers['x-edge-processed'] = { value: 'cloudfront-function' };
    return request;
}
""".strip()


# --- the Lambda@Edge source, written into a zip at deploy time ------------------
# NOTE: Lambda@Edge cannot read environment variables at runtime, so the signing
# secret is baked into the source at packaging time. In production you'd inject it
# from SSM at BUILD time (never commit a real secret); here we template it in.
def edge_source(secret: str) -> str:
    return f'''
import base64, hashlib, hmac, json

SIGNING_SECRET = {secret!r}.encode()

def _verify(tenant, sig_b64):
    expected = hmac.new(SIGNING_SECRET, tenant.encode(), hashlib.sha256).digest()
    try:
        provided = base64.urlsafe_b64decode(sig_b64 + "==")
    except Exception:
        return False
    return hmac.compare_digest(expected, provided)

def _cookies(headers):
    out = {{}}
    for h in headers.get("cookie", []):
        for pair in h["value"].split(";"):
            if "=" in pair:
                k, v = pair.strip().split("=", 1)
                out[k] = v
    return out

def handler(event, context):
    request = event["Records"][0]["cf"]["request"]
    c = _cookies(request["headers"])
    tenant, sig = c.get("tenant", ""), c.get("tenant_sig", "")
    if tenant and sig and _verify(tenant, sig):
        request["headers"]["x-tenant-id"] = [{{"key": "X-Tenant-Id", "value": tenant}}]
        return request
    # Untrusted/missing: strip any forged client header, reject.
    request["headers"].pop("x-tenant-id", None)
    return {{
        "status": "401",
        "statusDescription": "Unauthorized",
        "headers": {{"content-type": [{{"key": "Content-Type", "value": "application/json"}}]}},
        "body": json.dumps({{"error": "invalid or missing tenant cookie"}}),
    }}
'''.strip()


def sign_tenant(tenant: str, secret: str) -> str:
    """Helper you can call locally to mint a valid cookie pair for testing."""
    mac = hmac.new(secret.encode(), tenant.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def _zip_bytes(filename: str, content: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
def deploy() -> None:
    if not EDGE_ROLE_ARN:
        sys.exit("Set LAMBDA_EDGE_ROLE_ARN (see the header docstring for the trust policy).")

    # 1) CloudFront Function ---------------------------------------------------
    print("Publishing CloudFront Function...")
    try:
        created = cf.create_function(
            Name=CF_FUNCTION_NAME,
            FunctionConfig={"Comment": "cache-key hygiene", "Runtime": "cloudfront-js-2.0"},
            FunctionCode=CF_FUNCTION_CODE.encode(),
        )
        etag = created["ETag"]
    except cf.exceptions.FunctionAlreadyExists:
        desc = cf.describe_function(Name=CF_FUNCTION_NAME)
        etag = desc["ETag"]
    # Publish moves it from DEVELOPMENT to LIVE so a distribution can use it.
    pub = cf.publish_function(Name=CF_FUNCTION_NAME, IfMatch=etag)
    cf_fn_arn = pub["FunctionSummary"]["FunctionMetadata"]["FunctionARN"]
    print(f"  CF Function LIVE: {cf_fn_arn}")

    # 2) Lambda@Edge -----------------------------------------------------------
    print("Deploying Lambda@Edge (us-east-1)...")
    zip_bytes = _zip_bytes("index.py", edge_source(SIGNING_SECRET))
    try:
        fn = lam.create_function(
            FunctionName=EDGE_FN_NAME,
            Runtime="python3.12",
            Role=EDGE_ROLE_ARN,
            Handler="index.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=5,          # viewer-trigger max is 5s
            MemorySize=128,
            Publish=True,       # Lambda@Edge requires a published VERSION, not $LATEST
        )
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=EDGE_FN_NAME, ZipFile=zip_bytes, Publish=True)
        fn = lam.publish_version(FunctionName=EDGE_FN_NAME)
    edge_version_arn = fn["FunctionArn"]  # includes the :VERSION suffix
    print(f"  Lambda@Edge version ARN: {edge_version_arn}")

    # 3) Distribution ----------------------------------------------------------
    print("Creating CloudFront distribution (this is the slow part)...")
    dist_config = {
        "CallerReference": f"{CALLER_REF}-{int(time.time())}",
        "Comment": "C19 wk14 edge exercise",
        "Enabled": True,
        "Origins": {
            "Quantity": 1,
            "Items": [{
                "Id": "api-origin",
                "DomainName": ORIGIN_DOMAIN,
                "CustomOriginConfig": {
                    "HTTPPort": 80, "HTTPSPort": 443,
                    "OriginProtocolPolicy": "https-only",
                    "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
                },
            }],
        },
        "DefaultCacheBehavior": {
            "TargetOriginId": "api-origin",
            "ViewerProtocolPolicy": "redirect-to-https",
            "AllowedMethods": {"Quantity": 7,
                               "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
                               "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}},
            # Managed CachingDisabled policy id (constant across accounts) for an API:
            "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
            "FunctionAssociations": {
                "Quantity": 1,
                "Items": [{"EventType": "viewer-request", "FunctionARN": cf_fn_arn}],
            },
            "LambdaFunctionAssociations": {
                "Quantity": 1,
                "Items": [{"EventType": "viewer-request",
                           "LambdaFunctionARN": edge_version_arn,
                           "IncludeBody": False}],
            },
        },
    }
    dist = cf.create_distribution(DistributionConfig=dist_config)["Distribution"]
    print(f"  Distribution {dist['Id']} created; domain: {dist['DomainName']}")
    print("  Wait ~5-15 min for Status=Deployed before testing.\n")

    # 4) Test instructions -----------------------------------------------------
    good_sig = sign_tenant("acme", SIGNING_SECRET)
    print("TEST IT (after Status=Deployed):")
    print(f"  # No cookie -> 401 from the edge (never reaches origin):")
    print(f"  curl -i https://{dist['DomainName']}/")
    print(f"  # Valid signed cookie -> reaches origin carrying trusted X-Tenant-Id:")
    print(f"  curl -i --cookie 'tenant=acme; tenant_sig={good_sig}' https://{dist['DomainName']}/")
    print("  (Have your origin echo request headers so you can SEE x-tenant-id and")
    print("   x-edge-processed arrive -- proof both tiers ran.)\n")

    print("COST you placed (verify current pricing):")
    print("  - CloudFront Function (cache-key hygiene): ~$0.10 / 1M invocations, no duration.")
    print("  - Lambda@Edge (cookie verify + inject):   ~$0.60 / 1M + GB-seconds.")
    print("  We put the cheap, every-request rewrite in the CF Function and only the")
    print("  crypto-verify in Lambda@Edge -- the cost-as-a-feature split from Lecture 2.")
    print(f"\nSave the distribution id for teardown: {dist['Id']}")


def teardown(dist_id: str | None = None) -> None:
    """
    Edge teardown is multi-step BY NECESSITY: you must disable the distribution,
    wait for it to deploy disabled, delete it, then the replicated edge functions
    can be removed (replicas clear asynchronously, so Lambda@Edge delete may need
    a retry for up to ~an hour).
    """
    print("Teardown:")
    if dist_id:
        cfg = cf.get_distribution_config(Id=dist_id)
        etag, conf = cfg["ETag"], cfg["DistributionConfig"]
        if conf["Enabled"]:
            conf["Enabled"] = False
            cf.update_distribution(Id=dist_id, IfMatch=etag, DistributionConfig=conf)
            print("  Disabled distribution; wait for Status=Deployed, then re-run teardown to delete.")
            return
        cf.delete_distribution(Id=dist_id, IfMatch=etag)
        print(f"  Deleted distribution {dist_id}.")

    # Delete the CF Function (must not be associated with any LIVE distribution).
    try:
        et = cf.describe_function(Name=CF_FUNCTION_NAME)["ETag"]
        cf.delete_function(Name=CF_FUNCTION_NAME, IfMatch=et)
        print("  Deleted CloudFront Function.")
    except Exception as exc:  # noqa: BLE001
        print(f"  CF Function delete deferred: {exc}")

    # Delete the Lambda@Edge function (replicas must clear first; retry if needed).
    try:
        lam.delete_function(FunctionName=EDGE_FN_NAME)
        print("  Deleted Lambda@Edge function.")
    except Exception as exc:  # noqa: BLE001
        print(f"  Lambda@Edge replicas not cleared yet -- retry in ~15-60 min: {exc}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "deploy"
    if cmd == "deploy":
        deploy()
    elif cmd == "teardown":
        teardown(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "sign":  # convenience: mint a cookie pair, e.g. `... sign acme`
        t = sys.argv[2]
        print(f"tenant={t}; tenant_sig={sign_tenant(t, SIGNING_SECRET)}")
    else:
        sys.exit("usage: deploy | teardown [dist_id] | sign <tenant>")


if __name__ == "__main__":
    main()
