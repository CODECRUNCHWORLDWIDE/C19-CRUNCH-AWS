# Exercise 1 — CloudWatch Logs, EMF, and Alarms

> **Estimated time:** ~75 minutes. **Cost:** a few cents (a little log ingestion, a handful of custom metrics via EMF, one alarm, a couple of Logs Insights queries).

## Goal

Take a Lambda, make it emit **structured JSON logs** with a `trace_id`, emit a **custom metric via the Embedded Metric Format** (not `PutMetricData`), query both in **Logs Insights**, build a **metric filter** that derives a metric from a log pattern, wire a **static-threshold alarm** with the correct `treatMissingData`, and watch it fire. The headline outcome: you understand that a log group is a queryable dataset, that custom metrics can be nearly free, and that an alarm's missing-data setting decides whether a dead service looks healthy.

This is the "signals exist and are connected" baseline. Exercise 2 adds the trace that ties them together.

## Prerequisites

- AWS CLI v2 configured (`aws sts get-caller-identity` returns your account).
- Permissions for Lambda, IAM, CloudWatch, and CloudWatch Logs.
- Python 3.12+ and `pip`.
- Region `us-east-1` assumed; substitute consistently if you use another.

## Acceptance criteria

- [ ] A Lambda that logs structured JSON (via Lambda Powertools `Logger`) including a `trace_id` field.
- [ ] The same Lambda emits an EMF custom metric `InferenceLatencyMs` with a `Path` dimension — and you can confirm in the console it was **not** sent via `PutMetricData`.
- [ ] A Logs Insights query that filters by `level` and aggregates `latency_ms` by `path`.
- [ ] A **metric filter** on the log group that counts `ERROR` lines into a CloudWatch metric.
- [ ] A static-threshold alarm on that error-count metric, with `treatMissingData` chosen on purpose and justified in a one-line comment.
- [ ] You drove enough errors to push the alarm into `ALARM` and saw it transition.

---

## Step 1 — Create the function and its dependencies

Make a project directory and install Lambda Powertools (the EMF + structured-logging library).

```bash
export REGION=us-east-1
export ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export FN_NAME=c19-wk12-emf-demo

mkdir -p wk12-ex01/build && cd wk12-ex01
python -m venv .venv && source .venv/bin/activate
pip install aws-lambda-powertools -t build/
```

## Step 2 — Write the handler

Save this as `wk12-ex01/build/app.py`. It logs structured JSON, emits an EMF metric, and randomly errors so you have something to alarm on.

```python
import os
import random
import time

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

logger = Logger(service="recommend")          # JSON logs; injects xray_trace_id when tracing is on
metrics = Metrics(namespace="MyApp/Recommend", service="recommend")

# Probability the handler "fails" -- drives the alarm.
FAIL_RATE = float(os.environ.get("FAIL_RATE", "0.0"))


@logger.inject_lambda_context
@metrics.log_metrics                          # flushes the EMF metric blob at the end of the call
def handler(event, context):
    path = event.get("path", "sagemaker")
    start = time.perf_counter()

    # Simulate work; the SageMaker path is fast, the bedrock path is slower.
    time.sleep(0.01 if path == "sagemaker" else 0.08)
    latency_ms = (time.perf_counter() - start) * 1000

    # ---- EMF custom metric: emitted as a log line, parsed by CloudWatch, no PutMetricData ----
    metrics.add_metric(name="InferenceLatencyMs", unit=MetricUnit.Milliseconds, value=latency_ms)
    metrics.add_dimension(name="Path", value=path)

    if random.random() < FAIL_RATE:
        logger.error("inference failed", extra={"path": path, "latency_ms": latency_ms})
        raise RuntimeError("synthetic failure")

    logger.info("inference ok", extra={"path": path, "latency_ms": latency_ms})
    return {"ok": True, "path": path, "latency_ms": latency_ms}
```

Package and deploy it. First the execution role (basic logging only — Powertools EMF needs nothing beyond writing logs):

```bash
cat > trust.json <<'JSON'
{ "Version": "2012-10-17",
  "Statement": [{ "Effect": "Allow",
    "Principal": { "Service": "lambda.amazonaws.com" },
    "Action": "sts:AssumeRole" }] }
JSON

aws iam create-role --role-name ${FN_NAME}-role \
  --assume-role-policy-document file://trust.json
aws iam attach-role-policy --role-name ${FN_NAME}-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

export ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${FN_NAME}-role"

# Zip the build dir (handler + powertools) and create the function.
cd build && zip -qr ../fn.zip . && cd ..
sleep 10  # let the role propagate
aws lambda create-function \
  --function-name ${FN_NAME} \
  --runtime python3.12 \
  --handler app.handler \
  --role "${ROLE_ARN}" \
  --timeout 10 \
  --zip-file fileb://fn.zip \
  --region ${REGION}
```

## Step 3 — Drive traffic and read the structured logs

Invoke the function a few dozen times across both paths.

```bash
for i in $(seq 1 40); do
  PATHV=$([ $((i % 2)) -eq 0 ] && echo sagemaker || echo bedrock)
  aws lambda invoke --function-name ${FN_NAME} \
    --payload "{\"path\":\"${PATHV}\"}" --cli-binary-format raw-in-base64-out \
    /dev/null >/dev/null
done
echo "invoked 40 times"
```

Now query the structured logs in Logs Insights. The log group is `/aws/lambda/${FN_NAME}`.

```bash
LOG_GROUP="/aws/lambda/${FN_NAME}"
START=$(($(date +%s) - 900))    # last 15 minutes
END=$(date +%s)

QID=$(aws logs start-query \
  --log-group-name "${LOG_GROUP}" \
  --start-time ${START} --end-time ${END} \
  --query-string 'fields @timestamp, level, path, latency_ms
                  | filter level = "INFO"
                  | stats count() as hits, avg(latency_ms) as avg_ms by path
                  | sort avg_ms desc' \
  --query 'queryId' --output text)

# Poll until complete, then print results.
while [ "$(aws logs get-query-results --query-id "$QID" --query 'status' --output text)" = "Running" ]; do
  sleep 2
done
aws logs get-query-results --query-id "$QID" --query 'results'
```

You should see two rows, `bedrock` and `sagemaker`, with the bedrock path showing higher `avg_ms` (it sleeps longer). **That you can group by `path` at all is because you logged structured JSON** — a free-text log line could not be aggregated this way.

## Step 4 — Confirm the EMF metric exists (and was free)

The `metrics.log_metrics` decorator emitted an EMF log line, which CloudWatch parsed into a metric. List it:

```bash
aws cloudwatch list-metrics \
  --namespace "MyApp/Recommend" \
  --metric-name "InferenceLatencyMs" \
  --query 'Metrics[*].Dimensions'
```

You should see the metric with a `Path` dimension. Crucially: you never called `put-metric-data`. The metric came from a log line you were already paying to ingest. That is EMF. Pull a statistic to prove data flowed:

```bash
aws cloudwatch get-metric-statistics \
  --namespace "MyApp/Recommend" --metric-name "InferenceLatencyMs" \
  --dimensions Name=Path,Value=bedrock \
  --start-time "$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '15 min ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 --statistics Average Maximum
```

## Step 5 — Metric filter + alarm, and the missing-data choice

First set retention on the log group (never skip this) and create a **metric filter** that counts `ERROR` lines:

```bash
aws logs put-retention-policy --log-group-name "${LOG_GROUP}" --retention-in-days 14

aws logs put-metric-filter \
  --log-group-name "${LOG_GROUP}" \
  --filter-name error-count \
  --filter-pattern '{ $.level = "ERROR" }' \
  --metric-transformations \
      metricName=RecommendErrors,metricNamespace=MyApp/Recommend,metricValue=1,defaultValue=0
```

The pattern `{ $.level = "ERROR" }` matches structured JSON where the `level` field is `ERROR`. Now the alarm. **The missing-data choice matters:** this is an error *count*, where "no data" genuinely means "no errors reported," so `notBreaching` is correct here. (For a heartbeat/canary metric you would use `breaching` — silence is a symptom.)

```bash
# Create an SNS topic for the alarm action (optional but realistic).
TOPIC_ARN=$(aws sns create-topic --name c19-wk12-alarms --query 'TopicArn' --output text)

aws cloudwatch put-metric-alarm \
  --alarm-name c19-wk12-error-rate \
  --namespace MyApp/Recommend --metric-name RecommendErrors \
  --statistic Sum --period 60 \
  --evaluation-periods 5 --datapoints-to-alarm 3 \
  --threshold 3 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions "${TOPIC_ARN}"
```

`--evaluation-periods 5 --datapoints-to-alarm 3` is the `M out of N` noise filter: 3 of the last 5 minutes must each see more than 3 errors before it fires.

## Step 6 — Force the alarm to fire

Crank the failure rate and hammer the function:

```bash
aws lambda update-function-configuration --function-name ${FN_NAME} \
  --environment "Variables={FAIL_RATE=0.9}" --region ${REGION}
sleep 5

for i in $(seq 1 120); do
  aws lambda invoke --function-name ${FN_NAME} \
    --payload '{"path":"bedrock"}' --cli-binary-format raw-in-base64-out /dev/null >/dev/null 2>&1
done

# Watch the alarm state (give it a few minutes to evaluate 3 of 5 periods).
watch -n 30 "aws cloudwatch describe-alarms --alarm-names c19-wk12-error-rate --query 'MetricAlarms[0].StateValue' --output text"
```

Within a few minutes the alarm transitions `INSUFFICIENT_DATA`/`OK` → `ALARM`. That is the whole loop: a log pattern became a metric, the metric crossed a threshold, the alarm fired. Then reset the fail rate and watch it return to `OK`:

```bash
aws lambda update-function-configuration --function-name ${FN_NAME} \
  --environment "Variables={FAIL_RATE=0.0}" --region ${REGION}
```

## Expected output

The Logs Insights query (Step 3) returns something like:

```
[[{"field":"path","value":"bedrock"},   {"field":"hits","value":"20"},{"field":"avg_ms","value":"81.4"}],
 [{"field":"path","value":"sagemaker"}, {"field":"hits","value":"20"},{"field":"avg_ms","value":"10.7"}]]
```

The alarm (Step 6) settles on:

```
ALARM
```

Your exact numbers differ, but the shape is: bedrock path slower than sagemaker, and the alarm reaches `ALARM` once 3 of 5 minutes breach.

## Cleanup (end-of-session)

```bash
aws lambda delete-function --function-name ${FN_NAME}
aws cloudwatch delete-alarms --alarm-names c19-wk12-error-rate
aws logs delete-metric-filter --log-group-name "${LOG_GROUP}" --filter-name error-count
aws logs delete-log-group --log-group-name "${LOG_GROUP}"
aws sns delete-topic --topic-arn "${TOPIC_ARN}"
aws iam detach-role-policy --role-name ${FN_NAME}-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name ${FN_NAME}-role
```

## Inline hints

- *Logs Insights query returns nothing* — your time window missed the invocations, or the function never wrote (check `aws logs describe-log-streams`). Widen `--start-time`.
- *`stats ... by path` errors with "field not found"* — you logged a free-text string, not JSON. Confirm the log lines are JSON objects with a `path` field; Powertools `Logger` does this, raw `print()` does not.
- *EMF metric never appears in `list-metrics`* — CloudWatch parses EMF asynchronously; wait 1–2 minutes after the invocations. Also confirm the `_aws` block is in the log line (`aws logs get-log-events` and look for `CloudWatchMetrics`).
- *Alarm stuck in `INSUFFICIENT_DATA`* — you haven't generated 3 breaching minutes yet, or your `treatMissingData` is `missing` and the metric is sparse. Keep driving errors; the count metric needs sustained breaches.
