# Challenge 1 — LocalStack, `sam local invoke`, and Drift

**Time estimate:** ~120 minutes.

This challenge closes the loop the whole week has been building toward. You will run the Exercise 1 Lambda against an **emulated** S3 bucket with `sam local invoke` — no real AWS, no cost — and then deploy the same stack to your real `dev` account, mutate a resource by hand in the console, and catch the **drift** from CloudFormation. By the end you will have felt both halves of the IaC operating model: the cheap local inner loop, and the discipline that keeps a deployed stack honest.

The exercises proved you can *write* IaC. This challenge is the first time you *operate* it.

---

## Prerequisites

- A working **Exercise 1** TS CDK app (`crunch-iac-ts`) that synthesizes `CrunchIacTsStack` with a VPC, a KMS-encrypted S3 bucket, and a Lambda reader. If you skipped Exercise 1, do it first — this challenge builds directly on it.
- **Docker** running. LocalStack and `sam local invoke` both need it.
- **AWS SAM CLI** installed: `sam --version` should print `1.x`.
- **LocalStack** installed: `pip install localstack awscli-local` (gives you `localstack` and `awslocal`), and the CDK wrapper `npm install -g aws-cdk-local` (gives you `cdklocal`).
- A `crunch-dev` AWS profile you can `aws sso login --profile crunch-dev` into, for the real-AWS drift half. (LocalStack Community edition does **not** implement CloudFormation drift detection, which is exactly why that half runs against real AWS.)

---

## Part A — Run the Lambda locally with `sam local invoke` (45 min)

The Lambda reads an object from S3. To invoke it locally you need two things emulated: the **function runtime** (SAM gives you that in a Docker container) and the **S3 bucket** it reads from (LocalStack gives you that). The trick is wiring the function's `boto3` S3 client to talk to LocalStack instead of real S3.

### Step A1 — Start LocalStack and seed a bucket

```bash
localstack start -d
localstack status services | grep -E "s3|lambda|kms|cloudformation"
```

Wait until `s3` reads `available`. Now create a bucket and put an object in it using `awslocal` (the AWS CLI pre-pointed at `http://localhost:4566`):

```bash
awslocal s3 mb s3://local-data-bucket
echo "hello from localstack" > hello.txt
awslocal s3 cp hello.txt s3://local-data-bucket/hello.txt
awslocal s3 ls s3://local-data-bucket
# 2026-06-09 12:00:00         22 hello.txt
```

### Step A2 — Synthesize a SAM-invokable template

`sam local invoke` reads a SAM or CloudFormation template to find the function, its handler, runtime, and code location. CDK synthesizes exactly such a template. From your `crunch-iac-ts` directory:

```bash
cdk synth --no-staging > /dev/null   # writes cdk.out/CrunchIacTsStack.template.json
```

The `--no-staging` flag keeps the asset path pointing at your local `lambda/` directory rather than copying it into `cdk.out/asset.<hash>/`, which is what `sam local invoke` wants so it can mount your source directly.

Find the function's **logical ID** — SAM addresses functions by logical ID, not by the friendly name:

```bash
jq -r '.Resources | to_entries[] | select(.value.Type=="AWS::Lambda::Function") | .key' \
  cdk.out/CrunchIacTsStack.template.json
# ReaderFunctionXXXXXXXX
```

### Step A3 — Make the handler talk to LocalStack

Your Exercise 1 handler created its S3 client as `boto3.client("s3")`. For local invocation, point that client at LocalStack when an override is present. Edit `lambda/read_object.py` so the client respects an `AWS_ENDPOINT_URL_S3` (or generic `AWS_ENDPOINT_URL`) environment variable — which is also the **production-correct** pattern, because the AWS SDKs honour `AWS_ENDPOINT_URL_S3` natively as of 2024:

```python
import os
import boto3

# boto3 >= 1.34 reads AWS_ENDPOINT_URL_S3 automatically; passing it explicitly
# makes the intent obvious and works on older SDKs too.
_endpoint = os.environ.get("AWS_ENDPOINT_URL_S3") or os.environ.get("AWS_ENDPOINT_URL")
s3 = boto3.client("s3", endpoint_url=_endpoint) if _endpoint else boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]


def handler(event, _context):
    key = event.get("key", "hello.txt")
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    body = obj["Body"].read()
    return {
        "statusCode": 200,
        "bucket": BUCKET,
        "key": key,
        "size": len(body),
        "preview": body[:200].decode("utf-8", errors="replace"),
    }
```

Re-synth so the change is in the template: `cdk synth --no-staging > /dev/null`.

### Step A4 — Invoke locally

Create an event file `event.json`:

```json
{ "key": "hello.txt" }
```

Now invoke. From the host, the SAM Docker container reaches LocalStack via the special DNS name `host.docker.internal` (macOS/Windows) or `172.17.0.1` (Linux default bridge). Pass the bucket name, the endpoint override, and dummy credentials (LocalStack accepts anything):

```bash
sam local invoke ReaderFunctionXXXXXXXX \
  --template cdk.out/CrunchIacTsStack.template.json \
  --event event.json \
  --parameter-overrides '' \
  --env-vars <(cat <<'JSON'
{
  "ReaderFunctionXXXXXXXX": {
    "BUCKET_NAME": "local-data-bucket",
    "AWS_ENDPOINT_URL_S3": "http://host.docker.internal:4566",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "AWS_DEFAULT_REGION": "us-east-1"
  }
}
JSON
)
```

Replace `ReaderFunctionXXXXXXXX` with your real logical ID in both places.

**Expected output** (the JSON your handler returns, after SAM's build/run log lines):

```json
{"statusCode": 200, "bucket": "local-data-bucket", "key": "hello.txt", "size": 22, "preview": "hello from localstack\n"}
```

That is a Lambda, running in a container that mirrors the real Lambda runtime, reading from an emulated S3 bucket, for **zero dollars**. This is the inner loop.

> **If you get `Could not connect to the endpoint URL`:** the container can't reach LocalStack. On Linux, replace `host.docker.internal` with `172.17.0.1`, or run SAM with `--docker-network` set to the LocalStack network. On macOS/Windows, confirm `host.docker.internal` resolves from inside a container with `docker run --rm alpine getent hosts host.docker.internal`.

---

## Part B — Deploy to real `dev` and detect drift (60 min)

LocalStack Community does not implement `detect-stack-drift`. Drift detection is a **server-side CloudFormation** feature that diffs the deployed physical resources against the template's expected configuration — so this half must run against real AWS. The spend is pennies (one KMS key for an hour, an S3 bucket, a Lambda); you will `cdk destroy` at the end.

### Step B1 — Deploy

```bash
aws sso login --profile crunch-dev
cdk deploy CrunchIacTsStack --profile crunch-dev
```

Confirm the stack is `CREATE_COMPLETE` and note the bucket name from the outputs.

### Step B2 — Establish a clean baseline

Drift detection compares against what CloudFormation *thinks* the resources should be. Run it once before you change anything; the stack should report `IN_SYNC`:

```bash
DRIFT_ID=$(aws cloudformation detect-stack-drift \
  --stack-name CrunchIacTsStack --profile crunch-dev \
  --query StackDriftDetectionId --output text)

aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id "$DRIFT_ID" --profile crunch-dev \
  --query "{Status:DetectionStatus,Drift:StackDriftStatus}"
# { "Status": "DETECTION_COMPLETE", "Drift": "IN_SYNC" }
```

### Step B3 — Mutate a resource out-of-band

This is the realistic failure mode: a teammate "just fixes one thing" in the console. Pick the S3 bucket and turn **off** the bucket versioning that your CDK code turned on (or, if your bucket has versioning enforced by a policy, add an unmanaged tag instead — tags drift cleanly and reversibly):

Console path:

1. S3 → your bucket → **Properties** → **Bucket Versioning** → **Edit** → **Suspend** → Save.

Or, equivalently and scriptably, with the CLI (this *is* an out-of-band change — you are bypassing CloudFormation deliberately):

```bash
aws s3api put-bucket-versioning \
  --bucket <your-bucket-name> \
  --versioning-configuration Status=Suspended \
  --profile crunch-dev
```

You have now created drift: the template says `Status: Enabled`, the live bucket says `Suspended`.

### Step B4 — Catch the drift

```bash
DRIFT_ID=$(aws cloudformation detect-stack-drift \
  --stack-name CrunchIacTsStack --profile crunch-dev \
  --query StackDriftDetectionId --output text)

aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id "$DRIFT_ID" --profile crunch-dev \
  --query "{Status:DetectionStatus,Drift:StackDriftStatus,Drifted:DriftedStackResourceCount}"
# { "Status": "DETECTION_COMPLETE", "Drift": "DRIFTED", "Drifted": 1 }
```

Now get the property-level diff — *which* resource, *which* property:

```bash
aws cloudformation describe-stack-resource-drifts \
  --stack-name CrunchIacTsStack \
  --stack-resource-drift-status-filters MODIFIED \
  --profile crunch-dev \
  --query "StackResourceDrifts[].{Logical:LogicalResourceId,Status:StackResourceDriftStatus,Diffs:PropertyDifferences}"
```

You should see the `VersioningConfiguration` property reported as `NOT_EQUAL`, with the expected value (`Enabled`) and the actual value (`Suspended`). Read that JSON carefully — being able to read a drift report is the deliverable.

### Step B5 — Heal the drift the right way

The wrong fix is to flip versioning back in the console. The right fix is to **re-converge through the IaC**: a no-op `cdk deploy` reasserts the template's desired state and the drift disappears.

```bash
cdk deploy CrunchIacTsStack --profile crunch-dev
```

> **Why a no-op deploy heals it:** CloudFormation does not blindly skip "unchanged" resources during drift — but a deploy *does* re-apply the template's declared properties, and `VersioningConfiguration: Enabled` is in the template. After deploy, re-run drift detection; it should report `IN_SYNC` again. The lesson: **the console is read-only in a world with IaC.** Every change goes through the code.

### Step B6 — Tear down

```bash
cdk destroy CrunchIacTsStack --profile crunch-dev
```

The KMS key enters its deletion window (7 days) and stops billing on schedule. Confirm the stack is gone with `aws cloudformation describe-stacks --stack-name CrunchIacTsStack --profile crunch-dev` returning a "does not exist" error.

---

## Acceptance criteria

- [ ] `sam local invoke` returns the handler's JSON with `"statusCode": 200` and the correct `size`/`preview`, reading from a **LocalStack** bucket with **no real AWS calls**.
- [ ] The handler reads its S3 endpoint from `AWS_ENDPOINT_URL_S3` (or `AWS_ENDPOINT_URL`) so the same code runs locally and in production unchanged.
- [ ] A clean baseline drift check reports `IN_SYNC`.
- [ ] After the out-of-band mutation, `detect-stack-drift` reports `DRIFTED` with `DriftedStackResourceCount` ≥ 1.
- [ ] `describe-stack-resource-drifts` shows the exact property (`VersioningConfiguration` or your chosen tag) as `NOT_EQUAL`, with expected vs actual values.
- [ ] A no-op `cdk deploy` heals the drift; a follow-up detection reports `IN_SYNC`.
- [ ] `cdk destroy` removes the stack; you confirmed it is gone.
- [ ] You captured the drift report JSON into `challenge-01/drift-report.json` in your repo.

## Deliverable writeup

In `challenge-01/README.md` (≤ 1 page), answer:

1. **What did drift detection *not* catch?** Try a second mutation that drift detection misses (hint: add an IAM inline policy statement to a role, or change a Lambda's reserved concurrency — not all properties are drift-detectable). Name one property type CloudFormation drift cannot see and explain why.
2. **Why is "fix it in the console" a trap?** In two or three sentences, explain to a junior engineer why healing drift by editing the console re-creates the problem, and what the correct workflow is.
3. **Local vs real:** which behaviors did LocalStack let you iterate on cheaply, and which one (drift) forced you onto real AWS? Generalize that into a one-line rule for when to use the emulator.

## Stretch

- **Drift as a guardrail.** Write a tiny shell or Python script `check-drift.sh` that triggers detection, polls until `DETECTION_COMPLETE`, and exits non-zero if `StackDriftStatus != IN_SYNC`. This is the seed of the drift CI job you would run on a schedule in production. (Bonus: wire it into a `package.json` script `"drift": "..."`.)
- **`cdk diff` vs drift.** Run `cdk diff CrunchIacTsStack` while the stack is drifted. Note that `cdk diff` compares your *code* against the *last deployed template* — it does **not** see out-of-band drift. Write one sentence on the difference between `cdk diff` (code-vs-template) and `detect-stack-drift` (template-vs-reality). This distinction trips up engineers constantly.
- **`DeletionPolicy: Retain` experiment.** Add `bucket.applyRemovalPolicy(RemovalPolicy.RETAIN)` to a throwaway second bucket, deploy, then `cdk destroy`. Observe that the bucket survives the stack deletion. Clean it up by hand. This is the flag that saves your data — and the one that orphans resources if you forget about it.
