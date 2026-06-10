# Lecture 2 — The SageMaker Inference Path vs Bedrock: A Cost-and-Latency Decision Frame

> **Reading time:** ~75 minutes. **Hands-on time:** ~75 minutes (you train on Spot, deploy a real-time endpoint, and invoke it).

Lecture 1 ended on a claim: Bedrock is a router you pay for per token, and SageMaker is infrastructure you pay for per instance-hour. This lecture turns that claim into a decision frame you can defend in a design review with numbers. We will walk the full SageMaker inference path — Studio, a Spot training job, and the four serving modes — and then put SageMaker and Bedrock side by side on the only two axes that matter for the choice: **cost** and **latency**. By Friday you will produce the self-hosted-vs-managed write-up that is the deliverable for the challenge, and it will have a break-even traffic number in it, not an opinion.

## 2.1 — The shape of the SageMaker path

SageMaker is not one product; it is a dozen, and most of them you can ignore this week. The path that matters for inference is four steps:

1. **Studio** — the managed notebook/IDE environment where you write training code and orchestrate jobs. Think "JupyterLab plus the AWS plumbing pre-wired." You do not *have* to use Studio — everything is also drivable from the `sagemaker` Python SDK on your laptop — but Studio is where the cohort works because the IAM role, the default bucket, and the kernel images are already set up.

2. **A training job** — SageMaker spins up one or more instances, pulls a container (a prebuilt framework container like the scikit-learn one, or your own), runs your training script with your data from S3, writes the trained model artifact (`model.tar.gz`) back to S3, and *tears the instances down*. You pay only for the seconds the job ran. This is the key difference from training on a long-lived EC2 box: the compute is ephemeral and billed by the second.

3. **A model + endpoint configuration + endpoint** — to serve the trained artifact, you register a *model* (the artifact + the serving container), wrap it in an *endpoint configuration* (which instance type, how many, which serving mode), and deploy an *endpoint* (the live thing you call). The SDK collapses these three into one `.deploy()` call, but knowing they are three objects matters when you do blue/green endpoint updates later.

4. **Inference** — you call the endpoint. How you call it, and what it costs, depends entirely on which of the four serving modes you chose in step 3. That choice is the heart of this lecture.

```
   Studio / SDK
        │ writes training script + points at S3 data
        ▼
  Training job  ──(Spot instances, billed/sec, then torn down)──►  model.tar.gz in S3
        │
        ▼
   Model  ──►  Endpoint config (mode + instance) ──►  Endpoint  ──►  you invoke it
                                                          ▲
                                                          │
                                              real-time | serverless | async | batch
```

## 2.2 — Spot training: the same model for one-third the price

Training is embarrassingly interruptible: if the instance dies halfway through, you restart from the last checkpoint. That makes training a perfect fit for **Spot** capacity — spare AWS capacity sold at a 60–90% discount with the catch that AWS can reclaim it on two minutes' notice. **Managed Spot training** is SageMaker handling the Spot bidding, interruption, and checkpoint-resume for you. You flip two arguments on the estimator and read the savings line in the job's output.

Here is the scikit-learn training job you run Thursday, expressed with the SageMaker Python SDK:

```python
import sagemaker
from sagemaker.sklearn.estimator import SKLearn

session = sagemaker.Session()
role = sagemaker.get_execution_role()  # the Studio/notebook execution role
bucket = session.default_bucket()

estimator = SKLearn(
    entry_point="train.py",            # your training script (writes model to /opt/ml/model)
    source_dir="src",
    role=role,
    instance_type="ml.m5.large",
    instance_count=1,
    framework_version="1.2-1",         # the prebuilt scikit-learn container version
    py_version="py3",
    base_job_name="iris-spot",

    # --- the two lines that turn on managed Spot ---
    use_spot_instances=True,
    max_wait=3600,                     # total wall-clock budget incl. waiting for Spot capacity
    max_run=1200,                      # max seconds the job itself may run

    # checkpointing so an interruption resumes instead of restarting from zero
    checkpoint_s3_uri=f"s3://{bucket}/iris/checkpoints/",
)

estimator.fit({"train": f"s3://{bucket}/iris/train/"})
```

When the job finishes, SageMaker prints two numbers you must read:

```
Training seconds: 142
Billable seconds: 47
Managed Spot Training savings: 66.9%
```

`Training seconds` is wall clock; `Billable seconds` is what you pay for (Spot can make these differ, and the early seconds before the model is "warm" may be discounted differently). The **savings line** is the whole point: you got the identical model for roughly a third of the on-demand price, at the cost of a job that *might* have taken longer if Spot capacity was scarce (bounded by `max_wait`). For training — interruptible, non-latency-sensitive, runs in the background — Spot is almost always the right call. The mental rule: **Spot for training, on-demand for serving.** (You do *not* want your customer-facing endpoint reclaimed mid-request.)

A note on `train.py`: the contract is simple and container-imposed. SageMaker mounts your training data at `/opt/ml/input/data/train/`, passes hyperparameters as command-line args, and expects you to write the fitted model to `/opt/ml/model/`. Exercise 3 ships a complete, correct `train.py`; the point is the plumbing, so the model is a four-feature classifier you could fit in your sleep.

## 2.3 — The four serving modes, and the decision table

This is the section to tattoo on your forearm. SageMaker can serve the *same trained model* four ways, and picking wrong is the most common SageMaker cost and latency mistake.

### Real-time endpoint

A persistent HTTPS server backed by one or more instances that are **always on**. You call it synchronously and get a response in single-digit to low-double-digit milliseconds. You pay for the instance(s) **by the hour, 24/7, whether or not anyone calls.** An `ml.m5.large` real-time endpoint costs roughly **$0.115/hour ≈ $83/month** running continuously, before any traffic. This is the mode Thursday's exercise and the mini-project use, because the capstone's recommendation feature needs synchronous, low-latency responses on the request path.

```python
predictor = estimator.deploy(
    initial_instance_count=1,
    instance_type="ml.m5.large",
    endpoint_name="iris-realtime",
)
result = predictor.predict([[5.1, 3.5, 1.4, 0.2]])  # synchronous, ~10 ms
```

**Pick it when:** you need synchronous, low-latency, high-availability inference on the request path, and you have steady traffic that justifies a warm instance.

### Serverless endpoint

Same API, but SageMaker manages the instances and **scales to zero** when idle. You pay **per inference-second of compute plus per request**, nothing while idle. The catch is a **cold start** — when an idle endpoint gets a request, it must spin up, adding hundreds of milliseconds to a few seconds to that first call.

```python
from sagemaker.serverless import ServerlessInferenceConfig

predictor = estimator.deploy(
    serverless_inference_config=ServerlessInferenceConfig(
        memory_size_in_mb=2048,
        max_concurrency=5,
    ),
    endpoint_name="iris-serverless",
)
```

**Pick it when:** traffic is spiky or low-volume, and you can tolerate occasional cold-start latency. At low traffic it is dramatically cheaper than a warm real-time endpoint — you do not pay $83/month for an idle instance. The serverless break-even against real-time is the same shape of calculation we do for Bedrock below.

### Asynchronous endpoint

You submit a request that points at a large input in S3; SageMaker queues it, processes it, and writes the result to S3, notifying you (SNS) when done. Requests can be large (up to 1 GB) and slow (up to an hour). The endpoint can also **scale to zero** between bursts.

**Pick it when:** inference is expensive or the payload is large (a big document, an image batch), the caller does not need a synchronous answer, and you want queueing and auto-scaling-to-zero. Think "OCR a 200-page PDF," not "classify this click."

### Batch transform

Not an endpoint at all. A *job* that runs inference over an entire S3 dataset, writes all the predictions to S3, and shuts down. No persistent server, no per-hour cost — you pay for the job's instance-seconds, like training.

```python
transformer = estimator.transformer(
    instance_count=1,
    instance_type="ml.m5.large",
    output_path=f"s3://{bucket}/iris/batch-out/",
)
transformer.transform(f"s3://{bucket}/iris/batch-in/", content_type="text/csv")
```

**Pick it when:** you need predictions over a whole dataset on a schedule (nightly scoring of every user, say) and nothing needs to be real-time. It is the cheapest mode for bulk scoring because there is no idle server.

### The table

| Mode | Latency | Idle cost | Billing | Use it for |
|------|---------|-----------|---------|-----------|
| **Real-time** | Lowest (ms), constant | High (instance-hours 24/7) | Per instance-hour | Synchronous request-path inference, steady traffic |
| **Serverless** | Low, but cold starts | **Zero** (scales to 0) | Per inference-second + per request | Spiky/low-volume request-path inference |
| **Async** | Seconds–minutes, queued | Low/zero (scales to 0) | Per instance-second while processing | Large payloads, expensive inference, no sync need |
| **Batch transform** | N/A (offline) | Zero (job, not server) | Per instance-second of the job | Bulk/scheduled scoring of a whole dataset |

The decision is almost always made on two questions: *Does the caller need a synchronous answer?* (no → async or batch) and *Is the traffic steady enough to keep an instance warm?* (no → serverless). Get those two right and the mode picks itself.

## 2.4 — Calling the endpoint from Lambda

The capstone calls the real-time endpoint from a Lambda on the request path. The Lambda needs `sagemaker:InvokeEndpoint` on the specific endpoint ARN — least privilege, not `Resource: "*"`. Here is the handler:

```python
import json
import os
import boto3

runtime = boto3.client("sagemaker-runtime")
ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]

def handler(event, context):
    # event["features"] is a list of 4 floats, e.g. [5.1, 3.5, 1.4, 0.2]
    features = event["features"]
    payload = json.dumps([features])

    response = runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Body=payload,
    )
    prediction = json.loads(response["Body"].read())
    return {"prediction": prediction[0]}
```

The IAM policy attached to the Lambda's role, scoped tight:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sagemaker:InvokeEndpoint",
      "Resource": "arn:aws:sagemaker:us-east-1:111122223333:endpoint/iris-realtime"
    }
  ]
}
```

Note the endpoint, not the model or config, is the resource you grant on, and it is one specific ARN. If you wrote `Resource: "*"` here a Week-2 IAM review would (correctly) fail you.

## 2.5 — The decision frame: SageMaker self-hosted vs Bedrock managed

Now we put the two side by side. The challenge asks you to invoke the SageMaker endpoint and a Bedrock Claude Haiku call from Lambda on the *same input* and produce the self-hosted-vs-managed write-up. The write-up rests on two axes.

### Axis 1 — Cost: per-hour fixed vs per-token variable

This is the crux and it is just arithmetic.

**SageMaker real-time endpoint** is a *fixed* cost: you pay for the instance whether you serve one request or ten million. An `ml.m5.large` at ~$0.115/hr is **~$83/month** regardless of traffic. Per-request cost = $83 / (requests that month). At 10 requests/month that is $8.30/request — absurd. At 10 million requests/month it is $0.0000083/request — nearly free. **The per-request cost of a self-hosted endpoint falls as traffic rises**, because you are amortizing a fixed cost.

**Bedrock on-demand** is a *variable* cost: you pay per token, nothing at idle. Say a classification call is ~60 input tokens + ~5 output tokens, and Haiku is (verify current pricing) on the order of $0.80 per million input tokens and $4 per million output tokens. That request costs roughly `60 × $0.80/1e6 + 5 × $4/1e6 ≈ $0.000068`. **Every** request costs that; ten requests cost $0.00068, ten million cost $680. **The per-request cost of Bedrock is constant**, and the total scales linearly with traffic.

Now you can find the break-even. The SageMaker endpoint's *fixed* monthly cost ($83) divided by the Bedrock *per-request* cost ($0.000068) gives the traffic level where they cost the same:

```
break-even requests/month ≈ $83 / $0.000068 ≈ 1.22 million requests/month
                          ≈ ~28 requests/minute, sustained
```

Below that traffic, **Bedrock is cheaper** — you are not paying for an idle instance. Above it, **the self-hosted endpoint is cheaper** — the fixed cost is amortized across enough requests to beat the per-token rate. (And serverless SageMaker sits in between: variable like Bedrock, but you own the model.) This is the number that belongs in your write-up. Compute it with *your* measured token counts and *your* instance price, not these illustrative ones — verify both against the live pricing pages, because rates change.

A subtlety the write-up should acknowledge: the two sides are not doing the *same work*. The SageMaker endpoint runs *your* 4-feature classifier; Bedrock runs a general-purpose LLM you prompted into doing classification. The LLM is wildly more capable and wildly more expensive per unit of work. The honest framing is not "which is cheaper" in the abstract but "for *this task*, given that a tiny model suffices, the self-hosted endpoint is cheaper above ~1.2M req/mo, and Bedrock is cheaper below it and requires zero ML engineering." That nuance is what separates a senior write-up from a junior one.

### Axis 2 — Latency: warm instance vs network-plus-generation

**SageMaker real-time** on a warm instance answers a tiny classifier in **single-digit to low-double-digit milliseconds** — it is a local model inference behind an HTTPS call in the same Region. Predictable, low, no cold start (because real-time is always warm).

**Bedrock Haiku** answers in **hundreds of milliseconds to low seconds** — it is a large language model generating tokens, and latency scales with output length. Haiku is the fastest Claude tier precisely to make it usable on the request path, but it will not beat a warm linear classifier on raw latency, and it never will: generating text token-by-token is fundamentally more work than a matrix multiply over four features. Measure both p50 and p99 from your Lambda; Bedrock's tail (p99) is wider because generation time varies with output and shared-capacity load.

So the latency axis favors the self-hosted endpoint for this task — but again, the endpoint is doing far less work. If the task genuinely needed an LLM's reasoning, there would be no fast classifier to compare against, and Bedrock's few-hundred-ms latency would be the floor for that capability.

### Beyond cost and latency: the factors the write-up must not forget

A complete decision considers more than the two axes:

- **Operational burden.** The SageMaker endpoint is *yours* to patch, scale, monitor, and pay for at idle. Bedrock is someone else's problem. For a small team, "no infra to run" is worth real money even when Bedrock is nominally pricier.
- **Capability ceiling.** A self-hosted small model does exactly one thing. Bedrock gives you a frontier LLM that does summarization, extraction, reasoning, tool use, and your classification, all behind one API, swappable by model ID.
- **Data gravity and compliance.** Self-hosting keeps inference inside your VPC/account boundary; Bedrock processes your prompts in the managed service (within your Region, not used for training, per AWS's terms — but still a managed boundary). Some compliance regimes care.
- **Cold start.** Real-time has none (always warm). Serverless SageMaker and Bedrock provisioned-throughput-vs-on-demand each have their own warm-up story.

### The decision, distilled

> **Use Bedrock when:** traffic is low or spiky, the task benefits from a general LLM, you want zero infrastructure, and you are below the break-even traffic. **Self-host on SageMaker when:** a small purpose-built model suffices, traffic is high and steady (above break-even), you need single-digit-millisecond latency, or compliance requires inference inside your boundary. **Use SageMaker Serverless** as the middle path: you own the model, but pay per use like Bedrock.

For the capstone's recommendation feature specifically: the *recommendation* (a small model on tabular signals) self-hosts on a real-time endpoint because it is on the hot request path and traffic is steady; the *comparison feature* calls Bedrock Haiku because it is a capability the small model cannot provide and the team wants to demonstrate the router pattern. That is the architecture you are building toward, and now you can defend both halves with a number.

## 2.6 — Open-source comparators (what you traded away)

- **Ray** replaces SageMaker's managed training: distributed Python training you orchestrate yourself on your own cluster. You give up the managed Spot/checkpoint plumbing and gain control and portability. (Glue for Ray is AWS wrapping Ray for ETL.)
- **vLLM** replaces a self-hosted Bedrock-equivalent: high-throughput LLM serving with PagedAttention on your own GPUs. The break-even math changes entirely — now your "fixed cost" is a `g5`/`p5` instance-hour and your variable cost is near zero, so vLLM only beats Bedrock at *very* high token volume where the GPU is saturated. Below that, the GPU sits idle and expensive, exactly the trap a real-time SageMaker endpoint has at low traffic.

The pattern across this whole week: **managed services move you from a fixed-cost, you-operate-it world to a variable-cost, someone-else-operates-it world, and the break-even traffic is where you should switch.** Athena (per scan) vs a self-run Trino cluster, Bedrock (per token) vs vLLM on your GPU, SageMaker serverless (per second) vs a warm endpoint — they are all the same shape of decision. Learn to compute the break-even and you can make the call for any of them.

## 2.7 — What you should be able to do now

- Walk the four SageMaker steps: Studio → training job → model/config/endpoint → inference.
- Turn on managed Spot training and read the savings line.
- Choose among real-time, serverless, async, and batch transform from the two-question decision rule.
- Invoke an endpoint from Lambda with a least-privilege `sagemaker:InvokeEndpoint` policy.
- Compute the SageMaker-vs-Bedrock cost break-even from measured token counts and instance price.
- Measure and compare p50/p99 latency for both paths.
- Write the self-hosted-vs-managed decision doc with a break-even number and the non-cost factors — which is exactly the Friday challenge.

## 2.8 — The challenge that goes with this lecture

**Challenge 1 — Endpoint vs Bedrock from Lambda.** Invoke both the SageMaker real-time endpoint and a Bedrock Claude Haiku call on the same input from a single Lambda, capture cost and latency for each, compute the break-even, and write the decision doc. The acceptance criteria are in `challenges/challenge-01-endpoint-vs-bedrock.md`. Bring real numbers.
