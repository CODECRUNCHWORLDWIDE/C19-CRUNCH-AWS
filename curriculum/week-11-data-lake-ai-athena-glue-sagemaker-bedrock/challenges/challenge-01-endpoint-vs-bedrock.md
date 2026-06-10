# Challenge 1 — Call the SageMaker endpoint from Lambda and benchmark it against Bedrock Claude Haiku

> **Estimated time:** 2.5–3 hours. This is the week's synthesis: the self-hosted-vs-managed decision, made with numbers, not vibes. It is also the exact architecture the capstone's recommendation feature uses.

## The problem

You have a SageMaker real-time endpoint (from Exercise 3) that classifies a 4-feature tabular input with a small RandomForest. You also have Bedrock access to Anthropic Claude Haiku. Your job: build a single Lambda that, given one input, invokes **both** paths, returns both answers, and records the **cost** and **latency** of each. Then write a decision doc that says — for a stated traffic profile — which you would ship, and at what traffic level the answer flips.

The two paths are not doing identical work (a tiny classifier vs a frontier LLM prompted to classify), and your write-up must be honest about that. The senior skill being tested is holding "they cost X and Y" and "they are not the same capability" in your head at once and still producing a defensible recommendation.

## What you build

1. A Lambda (Python) with two code paths:
   - **Path A — SageMaker:** `sagemaker-runtime:invoke_endpoint` against your real-time endpoint with the 4 features.
   - **Path B — Bedrock:** `bedrock-runtime:converse` against Claude Haiku, prompting it to produce the same classification from a natural-language description of the same input.
2. Per-call instrumentation: wall-clock latency for each path, and for Bedrock the `usage` token counts returned by the API.
3. A small driver (run from your laptop or a second Lambda invocation loop) that fires the Lambda ~50 times and aggregates p50/p99 latency and average cost per call for both paths.
4. A written decision doc (`DECISION.md`) with the break-even calculation and a recommendation.

## Starter: the Lambda

Redeploy the Exercise 3 endpoint first (or keep one running for the duration of the challenge, then delete it). Set `ENDPOINT_NAME` and `BEDROCK_MODEL_ID` as Lambda environment variables.

```python
import json
import os
import time

import boto3

sm = boto3.client("sagemaker-runtime")
bedrock = boto3.client("bedrock-runtime")

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
# A cross-Region inference profile id. Verify the current Haiku id for your account.
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-haiku-20241022-v1:0"
)

# Map the classifier's integer label to a human class name for the LLM prompt.
CLASS_NAMES = {0: "setosa", 1: "versicolor", 2: "virginica"}


def invoke_sagemaker(features: list[float]) -> dict:
    t0 = time.perf_counter()
    resp = sm.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps([features]),
    )
    pred = json.loads(resp["Body"].read())[0]
    return {
        "label": int(pred),
        "class": CLASS_NAMES.get(int(pred), str(pred)),
        "latency_ms": (time.perf_counter() - t0) * 1000,
    }


def invoke_bedrock(features: list[float]) -> dict:
    prompt = (
        "You are classifying an iris flower into one of: setosa, versicolor, "
        "virginica. Given sepal_length, sepal_width, petal_length, petal_width "
        f"= {features}, reply with exactly one of those three words and nothing else."
    )
    t0 = time.perf_counter()
    resp = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 8, "temperature": 0.0},
    )
    text = resp["output"]["message"]["content"][0]["text"].strip().lower()
    usage = resp["usage"]
    return {
        "class": text,
        "latency_ms": (time.perf_counter() - t0) * 1000,
        "input_tokens": usage["inputTokens"],
        "output_tokens": usage["outputTokens"],
    }


def handler(event, context):
    features = event["features"]  # e.g. [5.1, 3.5, 1.4, 0.2]
    return {
        "sagemaker": invoke_sagemaker(features),
        "bedrock": invoke_bedrock(features),
    }
```

The Lambda's execution role needs exactly two extra grants, both scoped:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sagemaker:InvokeEndpoint",
      "Resource": "arn:aws:sagemaker:us-east-1:111122223333:endpoint/iris-realtime-*"
    },
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0",
        "arn:aws:bedrock:us-east-1:111122223333:inference-profile/us.anthropic.claude-3-5-haiku-20241022-v1:0"
      ]
    }
  ]
}
```

Note `converse` against an inference profile requires invoke permission on *both* the underlying foundation model and the inference-profile ARN — a common gotcha that produces an `AccessDeniedException` if you grant only one.

## The driver

Fire the Lambda ~50 times across a few inputs and aggregate. A laptop loop is fine:

```python
import json
import statistics

import boto3

lam = boto3.client("lambda", region_name="us-east-1")
SAMPLES = [
    [5.1, 3.5, 1.4, 0.2],
    [6.2, 2.9, 4.3, 1.3],
    [7.3, 2.9, 6.3, 1.8],
]


def call(features):
    resp = lam.invoke(
        FunctionName="wk11-endpoint-vs-bedrock",
        Payload=json.dumps({"features": features}).encode(),
    )
    return json.loads(resp["Payload"].read())


def main():
    sm_lat, bd_lat, bd_in, bd_out = [], [], [], []
    for i in range(50):
        r = call(SAMPLES[i % len(SAMPLES)])
        sm_lat.append(r["sagemaker"]["latency_ms"])
        bd_lat.append(r["bedrock"]["latency_ms"])
        bd_in.append(r["bedrock"]["input_tokens"])
        bd_out.append(r["bedrock"]["output_tokens"])

    def p(xs, q):
        return statistics.quantiles(xs, n=100)[q - 1]

    print(f"SageMaker  p50={statistics.median(sm_lat):.1f}ms  p99={p(sm_lat,99):.1f}ms")
    print(f"Bedrock    p50={statistics.median(bd_lat):.1f}ms  p99={p(bd_lat,99):.1f}ms")
    print(f"Bedrock    avg tokens in={statistics.mean(bd_in):.1f} out={statistics.mean(bd_out):.1f}")


if __name__ == "__main__":
    main()
```

## Acceptance criteria

- [ ] A deployed Lambda that invokes both paths on the same input and returns both results.
- [ ] The Lambda role grants `sagemaker:InvokeEndpoint` and `bedrock:InvokeModel` on **specific resources**, not `*`. (A Week-2 IAM review would fail `Resource: "*"` here.)
- [ ] Measured p50 and p99 latency for both paths over ≥ 50 calls.
- [ ] Measured average input/output tokens per Bedrock call.
- [ ] A `DECISION.md` containing:
  - The **per-call cost** of each path, computed from *your* measured numbers and the *current* pricing pages (cite the figures you used and the date you pulled them).
  - The **break-even traffic** in requests/month where the always-on SageMaker endpoint's fixed cost equals Bedrock's variable cost.
  - A recommendation for two named traffic profiles: "internal tool, ~500 calls/day" and "production feature, ~5M calls/month."
  - At least three non-cost factors (operational burden, capability ceiling, cold start, compliance boundary) and how they affect the call.
- [ ] The endpoint is deleted after you finish capturing numbers.

## Stretch

- Add a **SageMaker Serverless** variant as a third path and show where it sits between the always-on endpoint and Bedrock on both cost and latency.
- Switch the Bedrock call from `converse` to `invoke_model` and note in `DECISION.md` how the request body becomes model-specific — concretely demonstrating why the Converse API preserves the "router" benefit and `InvokeModel` partially gives it up.
- Estimate the cost of a **self-hosted vLLM** alternative on a `g5.xlarge` Spot instance for the LLM path, and find *its* break-even against Bedrock. (Hint: the fixed-cost-vs-per-token shape repeats; only the numbers change.)

## What "good" looks like

A strong submission's `DECISION.md` reads like a real design-review artifact: it states the numbers, shows the break-even arithmetic, names the traffic assumption explicitly, and then makes a call you can disagree with but not call *unsupported*. A weak submission says "Bedrock is easier" or "SageMaker is cheaper" with no number attached. The entire course is built to make you the first kind of engineer.
