// Exercise 3 — Deploy the same FastAPI app as Lambda + API Gateway behind CloudFront
//
// Goal: Take the SAME FastAPI service from exercises 1 and 2 and run it on the
//       serverless end of the spectrum — a single Lambda function (container image,
//       FastAPI unchanged via the AWS Lambda Web Adapter), fronted by an API Gateway
//       HTTP API, fronted by a CloudFront distribution. Scope the function's IAM
//       execution role to read exactly one S3 prefix (the Lambda mirror of the IRSA
//       scope you proved in exercise 2), and emit the cold-start number you will need
//       for the Friday benchmark.
//
//       Expected outcome: the identical /healthz, /compute, and /read endpoints,
//       now $0 when idle, billed per millisecond, with a visible cold-start on the
//       first request and single-digit-ms warm latency after.
//
// Estimated time: ~2 hours.
//
// ----------------------------------------------------------------------------------
// HOW TO USE THIS FILE
// ----------------------------------------------------------------------------------
//
// 1. Scaffold a TypeScript CDK app next to your week-05 work:
//
//      mkdir infra-lambda && cd infra-lambda
//      cdk init app --language typescript
//      npm install aws-cdk-lib constructs
//
//    Replace lib/<stack>.ts with the STACK below, and bin/<app>.ts with the APP entry.
//    (cdk init names them after the folder; adjust the import path accordingly.)
//
// 2. Put the FastAPI app + Dockerfile from exercise 1 in ./app (see the APP NOTES at
//    the bottom of this file for the two-line Dockerfile change that turns the same
//    image into a Lambda image via the Lambda Web Adapter).
//
// 3. Deploy:
//
//      cdk bootstrap        # once per account/region, if not already done in week 3
//      cdk deploy
//
// 4. Hit the endpoints and read the cold start. See the RUN section at the bottom.
//
// ----------------------------------------------------------------------------------
// ACCEPTANCE CRITERIA
// ----------------------------------------------------------------------------------
//
//   [ ] `cdk deploy` provisions a Lambda (container image), an HTTP API, and a
//       CloudFront distribution, all in private/regional config, with 0 errors.
//   [ ] GET <cloudfront-domain>/healthz returns {"status":"ok"}.
//   [ ] GET <cloudfront-domain>/read?key=public/hello.txt returns the object's first line.
//   [ ] GET <cloudfront-domain>/read?key=private/secret.txt returns 403/AccessDenied
//       (the execution role is scoped to public/* only — the serverless mirror of IRSA).
//   [ ] The first request shows an Init Duration in the Lambda REPORT log (cold start);
//       subsequent requests do not. You record both for the benchmark.
//   [ ] `cdk destroy` removes everything (Lambda is $0 idle, but CloudFront + logs linger).
//
// ----------------------------------------------------------------------------------
// THE STACK  (lib/lambda-apigw-cloudfront-stack.ts)
// ----------------------------------------------------------------------------------

import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import { HttpLambdaIntegration } from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as path from "path";

export class LambdaApigwCloudfrontStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ---- 1. The data bucket, with one readable and one forbidden prefix ----------
    // Same shape as exercise 2 so the IRSA-vs-execution-role comparison is apples-to-apples.
    const bucket = new s3.Bucket(this, "DataBucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // lab convenience; never in prod
      autoDeleteObjects: true,
    });

    // Seed public/hello.txt (readable) and private/secret.txt (must stay forbidden).
    new s3deploy.BucketDeployment(this, "SeedObjects", {
      destinationBucket: bucket,
      sources: [
        s3deploy.Source.data("public/hello.txt", "hello from lambda\n"),
        s3deploy.Source.data("private/secret.txt", "you should never read this\n"),
      ],
    });

    // ---- 2. The Lambda function: the SAME FastAPI container, Web-Adapter-wrapped ---
    // DockerImageFunction builds ./app/Dockerfile and pushes to ECR for us.
    // Memory is the CPU dial on Lambda: 1024 MB ~= ~0.58 vCPU. The /compute endpoint
    // is CPU-bound, so we give it real memory; tune this in the benchmark.
    const fn = new lambda.DockerImageFunction(this, "FastApiFn", {
      code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, "..", "app"), {
        platform: cdk.aws_ecr_assets.Platform.LINUX_ARM64, // Graviton: ~20% cheaper GB-s
      }),
      architecture: lambda.Architecture.ARM_64,
      memorySize: 1024,
      timeout: cdk.Duration.seconds(29), // must be < API Gateway's 30s integration cap
      environment: {
        // The Lambda Web Adapter reads these. It boots uvicorn on 8080 and proxies.
        AWS_LWA_PORT: "8080",
        DATA_BUCKET: bucket.bucketName,
        // Surfaces cold starts clearly in the REPORT line; harmless in prod.
        PYTHONUNBUFFERED: "1",
      },
      logGroup: new logs.LogGroup(this, "FnLogs", {
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // ---- 3. Least-privilege execution role: read public/* and NOTHING else --------
    // This is the serverless mirror of exercise 2's IRSA scope. Prove the negative:
    // the function can GetObject from public/* and gets AccessDenied on private/*.
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["s3:GetObject"],
        resources: [bucket.arnForObjects("public/*")],
      })
    );
    // NOTE: we deliberately do NOT grant bucket.grantRead(fn) — that would grant the
    // whole bucket and break the scope proof. Grant exactly the prefix.

    // ---- 4. API Gateway HTTP API in front of the function -------------------------
    // HTTP API (v2) is cheaper and lower-latency than REST API (v1) and is the right
    // default for a plain proxy. The payload-format v2 contract is what the Lambda Web
    // Adapter understands out of the box.
    const integration = new HttpLambdaIntegration("FastApiIntegration", fn, {
      payloadFormatVersion: apigwv2.PayloadFormatVersion.VERSION_2_0,
    });

    const httpApi = new apigwv2.HttpApi(this, "HttpApi", {
      apiName: "c19-week05-fastapi",
      // Catch-all proxy: every path/method goes to the one function; FastAPI routes internally.
      defaultIntegration: integration,
    });

    // ---- 5. CloudFront in front of the API ----------------------------------------
    // CloudFront terminates TLS at the edge, can cache GETs, and is the front door the
    // capstone uses for Lambda@Edge tenant routing. We disable caching for the dynamic
    // API (CACHING_DISABLED) and forward all viewer query strings/headers the origin needs.
    const apiDomain = `${httpApi.apiId}.execute-api.${this.region}.amazonaws.com`;

    const distribution = new cloudfront.Distribution(this, "Cdn", {
      defaultBehavior: {
        origin: new origins.HttpOrigin(apiDomain, {
          protocolPolicy: cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        // Forward query strings (e.g. ?key=) and the Host the origin expects.
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
      },
      comment: "c19-week05 FastAPI serverless front door",
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100, // NA+EU edges only; cheapest
    });

    // ---- 6. Outputs ----------------------------------------------------------------
    new cdk.CfnOutput(this, "CloudFrontUrl", {
      value: `https://${distribution.distributionDomainName}`,
      description: "Hit /healthz, /compute, /read?key=public/hello.txt here",
    });
    new cdk.CfnOutput(this, "ApiUrl", {
      value: httpApi.apiEndpoint,
      description: "Direct API Gateway URL (bypasses CloudFront, for cold-start isolation)",
    });
    new cdk.CfnOutput(this, "BucketName", { value: bucket.bucketName });
    new cdk.CfnOutput(this, "FunctionName", { value: fn.functionName });
  }
}

// ----------------------------------------------------------------------------------
// THE APP ENTRY  (bin/infra-lambda.ts)
// ----------------------------------------------------------------------------------
//
//   import * as cdk from "aws-cdk-lib";
//   import { LambdaApigwCloudfrontStack } from "../lib/lambda-apigw-cloudfront-stack";
//
//   const app = new cdk.App();
//   new LambdaApigwCloudfrontStack(app, "LambdaApigwCloudfrontStack", {
//     env: {
//       account: process.env.CDK_DEFAULT_ACCOUNT,
//       region: process.env.CDK_DEFAULT_REGION,
//     },
//   });
//
// ----------------------------------------------------------------------------------
// APP NOTES — turning the exercise-1 image into a Lambda image
// ----------------------------------------------------------------------------------
//
// The FastAPI app is byte-for-byte the same as exercise 1 (app/main.py). The only
// change is the Dockerfile: copy in the AWS Lambda Web Adapter and let it proxy.
// Put this at ./app/Dockerfile:
//
//   FROM public.ecr.aws/lambda/python:3.12-arm64
//   # The Lambda Web Adapter: a layer/extension that runs your HTTP server and
//   # translates Lambda invocations <-> HTTP. FastAPI needs ZERO code changes.
//   COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 \
//        /lambda-adapter /opt/extensions/lambda-adapter
//   WORKDIR /var/task
//   COPY requirements.txt .
//   RUN pip install --no-cache-dir -r requirements.txt
//   COPY main.py .
//   ENV AWS_LWA_PORT=8080
//   # Start uvicorn exactly like the Fargate/EKS image does. The adapter does the rest.
//   ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
//
// app/requirements.txt:
//
//   fastapi==0.115.0
//   uvicorn[standard]==0.30.6
//   boto3==1.35.0
//
// app/main.py (identical to exercises 1 and 2 — the whole point of the week):
//
//   import os, time
//   import boto3
//   from fastapi import FastAPI, HTTPException
//   from botocore.exceptions import ClientError
//
//   app = FastAPI()
//   _s3 = boto3.client("s3")
//   BUCKET = os.environ["DATA_BUCKET"]
//
//   @app.get("/healthz")
//   def healthz():
//       return {"status": "ok"}
//
//   @app.get("/compute")
//   def compute(n: int = 100_000):
//       # A small CPU burn so latency/cost differences between platforms are visible.
//       total = 0
//       for i in range(n):
//           total = (total + i * i) % 1_000_003
//       return {"n": n, "checksum": total}
//
//   @app.get("/read")
//   def read(key: str):
//       try:
//           obj = _s3.get_object(Bucket=BUCKET, Key=key)
//           first_line = obj["Body"].read().decode().splitlines()[0]
//           return {"key": key, "first_line": first_line}
//       except ClientError as e:
//           code = e.response["Error"]["Code"]
//           raise HTTPException(status_code=403 if code == "AccessDenied" else 404, detail=code)
//
// ----------------------------------------------------------------------------------
// RUN  (read the cold start — this is the number Friday's benchmark needs)
// ----------------------------------------------------------------------------------
//
//   cdk deploy
//   CF=$(aws cloudformation describe-stacks --stack-name LambdaApigwCloudfrontStack \
//     --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" --output text)
//
//   curl -s "$CF/healthz"                       # {"status":"ok"} (FIRST call: cold start)
//   curl -s "$CF/healthz"                       # warm: single-digit ms
//   curl -s "$CF/read?key=public/hello.txt"     # {"key":...,"first_line":"hello from lambda"}
//   curl -s "$CF/read?key=private/secret.txt"   # 403 {"detail":"AccessDenied"}  <-- scope proof
//
//   # Pull the cold-start number straight from the REPORT line:
//   FN=$(aws cloudformation describe-stacks --stack-name LambdaApigwCloudfrontStack \
//     --query "Stacks[0].Outputs[?OutputKey=='FunctionName'].OutputValue" --output text)
//   aws logs filter-log-events --log-group-name "/aws/lambda/$FN" \
//     --filter-pattern "REPORT" --query "events[].message" --output text
//   # Look for "Init Duration: NNN.NN ms" — that is the cold start. Warm invocations omit it.
//
//   # Force a fresh cold start any time by updating an env var (bumps the function version):
//   aws lambda update-function-configuration --function-name "$FN" \
//     --environment "Variables={DATA_BUCKET=$FN-ignored,AWS_LWA_PORT=8080}" >/dev/null
//   # (then set it back — or just redeploy)
//
// TEAR DOWN:
//
//   cdk destroy
//   # Lambda is $0 idle, but the CloudFront distribution and the log group are not free
//   # to leave lying around. Destroy them. CloudFront deletion takes a few minutes
//   # (it disables, then deletes the edge config) — that's normal.
//
// ----------------------------------------------------------------------------------
// HINTS (don't peek for 15 minutes)
// ----------------------------------------------------------------------------------
//
// * 502 from the API? The container didn't boot a server on AWS_LWA_PORT (8080), or the
//   adapter extension wasn't copied. Check the function logs; you should see uvicorn's
//   "Uvicorn running on http://0.0.0.0:8080" line. If you see the adapter complaining it
//   can't reach the app, your ENTRYPOINT port and AWS_LWA_PORT disagree.
//
// * /read returns AccessDenied for public/* too? Your execution-role statement scoped
//   the wrong prefix, or you accidentally also called bucket.grantRead(fn) which would
//   have widened it (but the deny-by-omission still wouldn't grant public). Re-check
//   the single PolicyStatement resources: it must be arnForObjects("public/*").
//
// * /read returns 200 for private/* — that's a SCOPE FAILURE, the opposite bug. You
//   granted too much (likely bucket.grantRead). Remove it; the only grant is public/*.
//
// * CloudFront returns the API's response but strips ?key=? The query string isn't being
//   forwarded. Confirm originRequestPolicy is ALL_VIEWER_EXCEPT_HOST_HEADER (CloudFront
//   must NOT forward the viewer Host to API Gateway, or APIGW rejects it; it must forward
//   query strings, which this managed policy does).
//
// * Cold start looks huge (>2s)? A container-image Lambda has a larger init than a zip,
//   but 1–1.5s for a Python FastAPI image on first call is normal. To shrink it: smaller
//   image, fewer imports at module load, or provisioned concurrency (priced in the
//   challenge). SnapStart for Python is the 2026 option — try it as a stretch goal.
