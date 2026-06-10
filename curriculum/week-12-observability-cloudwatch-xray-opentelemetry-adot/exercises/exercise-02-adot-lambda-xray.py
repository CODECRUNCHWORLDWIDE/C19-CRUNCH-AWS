#!/usr/bin/env python3
"""
Exercise 2 — Instrument a Lambda with OpenTelemetry + the ADOT extension layer,
send traces to X-Ray, and read the service map.

Estimated time: ~90 minutes.
Cost: cents (a little Lambda + log ingestion) plus X-Ray per-trace charges for
      the few hundred traces you record. Trivial, but real -- X-Ray bills per trace.

WHAT THIS DOES
--------------
This driver script DEPLOYS and EXERCISES a traced Lambda. It:

  1. Writes a Lambda handler (app.py) and an ADOT collector config (collector.yaml)
     to disk, packages them, and creates the function with:
       - the ADOT Python managed layer (auto-instruments boto3/requests),
       - AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument (turns on auto-instrumentation),
       - tracing=Active (so API GW / Lambda propagate the X-Ray trace header).
  2. Adds X-Ray write permission to the execution role.
  3. Invokes the function ~50 times to generate traces.
  4. Pulls the X-Ray service graph and prints the discovered services + their
     error/latency stats, proving the traces landed.

The handler does real boto3 work (an STS GetCallerIdentity stands in for the
SageMaker/Bedrock calls of the capstone) so the auto-instrumentation has a
downstream call to trace, PLUS a MANUAL span around the "business logic" so you
see both auto- and manual-instrumentation in one trace.

IMPORTANT -- THE LAYER ARN IS REGION/ARCH-SPECIFIC AND VERSIONED
----------------------------------------------------------------
The ADOT Python layer ARN below is a STRUCTURE, not a guaranteed-live value.
Confirm the CURRENT version for your Region and architecture from:
    https://aws-otel.github.io/docs/getting-started/lambda
Set ADOT_LAYER_ARN in your environment to the live ARN before running.

HOW TO RUN
----------
    python -m venv .venv && source .venv/bin/activate
    pip install boto3
    export REGION=us-east-1
    export ADOT_LAYER_ARN="arn:aws:lambda:us-east-1:901920570463:layer:aws-otel-python-amd64-ver-1-32-0:1"
    python exercise-02-adot-lambda-xray.py

ACCEPTANCE CRITERIA
-------------------
  [ ] A Lambda with the ADOT layer + AWS_LAMBDA_EXEC_WRAPPER + Active tracing.
  [ ] Invocations produce traces visible in the X-Ray console service map.
  [ ] The trace shows BOTH an auto-instrumented downstream call (STS) AND your
      MANUAL "score_model" span.
  [ ] You can read the service graph from the CLI and see the service name,
      request count, and average latency.
  [ ] Cleanup removes the function and role.

SMOKE OUTPUT (your numbers will differ)
---------------------------------------
    deployed c19-wk12-traced; invoking 50x ...
    invoked 50 times; waiting ~30s for X-Ray to ingest ...
    === X-Ray service graph (last 10 min) ===
    service                 type                 requests   avg_ms   errors
    c19-wk12-traced         AWS::Lambda::Function      50     14.2        0
    AWS::STS                 remote                     50      9.1        0
    Open the X-Ray console -> Service map to see the waterfall and the manual span.
"""

from __future__ import annotations

import io
import os
import time
import zipfile

import boto3

REGION = os.environ.get("REGION", "us-east-1")
FN_NAME = "c19-wk12-traced"
ROLE_NAME = f"{FN_NAME}-role"
ADOT_LAYER_ARN = os.environ.get(
    "ADOT_LAYER_ARN",
    # Structure only -- confirm the live version from the ADOT docs and override via env.
    f"arn:aws:lambda:{REGION}:901920570463:layer:aws-otel-python-amd64-ver-1-32-0:1",
)

lam = boto3.client("lambda", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)
xray = boto3.client("xray", region_name=REGION)
sts = boto3.client("sts", region_name=REGION)

# ---------------------------------------------------------------------------
# The handler. Auto-instrumentation (via the ADOT wrapper) traces the boto3 STS
# call for free. We ALSO open a manual span around our own logic so the trace
# carries domain meaning the auto-instrumentation cannot see.
# ---------------------------------------------------------------------------
APP_PY = '''
import boto3
from opentelemetry import trace

tracer = trace.get_tracer("recommend")     # provider is configured by the ADOT wrapper
sts = boto3.client("sts")                  # boto3 calls are auto-instrumented -> child spans


def score_model(features):
    # MANUAL span: this is YOUR business logic, invisible to auto-instrumentation.
    with tracer.start_as_current_span("score_model") as span:
        span.set_attribute("model.feature_count", len(features))
        # Stand in for the real SageMaker inference with a cheap, traceable AWS call.
        ident = sts.get_caller_identity()          # auto-instrumented child span
        span.set_attribute("aws.account", ident["Account"])
        label = sum(features) % 3                   # trivial deterministic "prediction"
        span.set_attribute("model.label", label)
        return label


def handler(event, context):
    features = event.get("features", [5.1, 3.5, 1.4, 0.2])
    label = score_model(features)
    return {"label": label}
'''

# Minimal collector config: OTLP in, X-Ray for traces, EMF (CloudWatch) for metrics.
COLLECTOR_YAML = f'''
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: localhost:4317
processors:
  batch: {{}}
exporters:
  awsxray:
    region: {REGION}
  awsemf:
    region: {REGION}
    namespace: MyApp/Recommend
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsxray]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsemf]
'''

TRUST = (
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
    '"Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
)


def build_zip() -> bytes:
    """Package app.py + collector.yaml into a deployment zip in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("app.py", APP_PY)
        z.writestr("collector.yaml", COLLECTOR_YAML)
    return buf.getvalue()


def ensure_role() -> str:
    """Create the execution role with basic logging + X-Ray write, return its ARN."""
    try:
        iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=TRUST)
    except iam.exceptions.EntityAlreadyExistsException:
        pass
    for arn in (
        "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        # X-Ray write actions do not support resource scoping; this managed policy is the
        # documented least-privilege grant for emitting traces.
        "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess",
    ):
        iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=arn)
    account = sts.get_caller_identity()["Account"]
    role_arn = f"arn:aws:iam::{account}:role/{ROLE_NAME}"
    time.sleep(12)  # let the new role propagate before Lambda tries to assume it
    return role_arn


def deploy(role_arn: str) -> None:
    pkg = build_zip()
    common = dict(
        FunctionName=FN_NAME,
        Runtime="python3.12",
        Handler="app.handler",
        Role=role_arn,
        Timeout=15,
        Layers=[ADOT_LAYER_ARN],
        TracingConfig={"Mode": "Active"},  # propagate the X-Ray trace header
        Environment={
            "Variables": {
                # The wrapper that injects OTel auto-instrumentation + starts the collector:
                "AWS_LAMBDA_EXEC_WRAPPER": "/opt/otel-instrument",
                # Point the in-process collector at our bundled config:
                "OPENTELEMETRY_COLLECTOR_CONFIG_URI": "/var/task/collector.yaml",
            }
        },
    )
    try:
        lam.create_function(Code={"ZipFile": pkg}, **common)
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=FN_NAME, ZipFile=pkg)
        lam.get_waiter("function_updated").wait(FunctionName=FN_NAME)
        lam.update_function_configuration(
            FunctionName=FN_NAME,
            Layers=[ADOT_LAYER_ARN],
            TracingConfig={"Mode": "Active"},
            Environment=common["Environment"],
        )
    lam.get_waiter("function_active_v2").wait(FunctionName=FN_NAME)


def invoke_many(n: int = 50) -> None:
    for i in range(n):
        lam.invoke(
            FunctionName=FN_NAME,
            Payload=b'{"features":[5.1,3.5,1.4,0.2]}',
        )
    print(f"invoked {n} times; waiting ~30s for X-Ray to ingest ...")
    time.sleep(30)


def print_service_graph() -> None:
    end = time.time()
    start = end - 600
    graph = xray.get_service_graph(StartTime=start, EndTime=end)
    print("\n=== X-Ray service graph (last 10 min) ===")
    print(f"{'service':<24}{'type':<22}{'requests':>10}{'avg_ms':>9}{'errors':>9}")
    for svc in graph.get("Services", []):
        summary = svc.get("SummaryStatistics", {})
        count = summary.get("TotalCount", 0)
        avg_ms = summary.get("TotalResponseTime", 0.0) * 1000 / count if count else 0.0
        errors = summary.get("ErrorStatistics", {}).get("TotalCount", 0)
        print(f"{svc.get('Name','?'):<24}{svc.get('Type','?'):<22}"
              f"{count:>10}{avg_ms:>9.1f}{errors:>9}")
    print("\nOpen the X-Ray console -> Service map to see the waterfall and the manual span.")


def cleanup() -> None:
    try:
        lam.delete_function(FunctionName=FN_NAME)
    except lam.exceptions.ResourceNotFoundException:
        pass
    for arn in (
        "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess",
    ):
        try:
            iam.detach_role_policy(RoleName=ROLE_NAME, PolicyArn=arn)
        except iam.exceptions.NoSuchEntityException:
            pass
    try:
        iam.delete_role(RoleName=ROLE_NAME)
    except iam.exceptions.NoSuchEntityException:
        pass
    print("cleaned up function and role.")


def main() -> None:
    role_arn = ensure_role()
    deploy(role_arn)
    print(f"deployed {FN_NAME}; invoking 50x ...")
    invoke_many(50)
    print_service_graph()
    print(
        "\nLeave the function up if you want to explore the console, then run with "
        "CLEANUP=1 to remove it:\n    CLEANUP=1 python exercise-02-adot-lambda-xray.py"
    )


if __name__ == "__main__":
    if os.environ.get("CLEANUP") == "1":
        cleanup()
    else:
        main()
