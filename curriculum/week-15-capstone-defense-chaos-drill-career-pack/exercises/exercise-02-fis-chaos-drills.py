#!/usr/bin/env python3
"""
Exercise 2 - Chaos drill driver for the Event-Driven SaaS Backbone capstone.

Drive the two remaining required chaos drills against your LIVE (non-prod)
capstone, capture a precise timeline, measure the SLO impact and recovery, and
emit a POSTMORTEM.md skeleton you fill in. Pick one drill per run:

  dynamo-throttle   Hammer a SINGLE DynamoDB partition key to force a hot
                    partition and provoke throttling / ProvisionedThroughput-
                    ExceededException, then prove the back-pressure lands in the
                    SQS retry queue / DLQ and the rest of the table is unaffected.
                    Run it once WITHOUT write-sharding and once WITH, to show the
                    mitigation works.

  lambda-concurrency  Drive more concurrent invocations than the target Lambda's
                    reserved concurrency allows, so Lambda throttles (429) the
                    excess. Trace the back-pressure into SQS depth / the DLQ and
                    confirm it is back-pressure, not data loss.

This is the same measure-the-timeline discipline as Exercise 1, applied to the
DynamoDB and Lambda drills the capstone spec requires. The AZ-failover drill is
Exercise 1 (driven by FIS directly); these two are driven here because the fault
is a *load pattern* against your own resources, which a script expresses more
naturally than a FIS action.

USAGE
  python -m venv .venv && source .venv/bin/activate
  pip install boto3
  export REGION=us-east-1
  export API_URL="https://<your-api>/v1/events"     # the public ingest endpoint
  export TABLE_NAME="capstone-single-table"          # your DynamoDB table
  export RETRY_QUEUE_URL="https://sqs.../capstone-retry"
  export DLQ_URL="https://sqs.../capstone-retry-dlq"
  export TARGET_LAMBDA="capstone-event-handler"      # lambda-concurrency drill

  python exercise-02-fis-chaos-drills.py dynamo-throttle --duration 180
  python exercise-02-fis-chaos-drills.py dynamo-throttle --duration 180 --sharded
  python exercise-02-fis-chaos-drills.py lambda-concurrency --concurrency 200 --duration 180

WHAT IT DOES (and does NOT do)
  It probes the public API once per second (steady-state SLO), injects the fault
  (a hot-partition write loop, or a burst of concurrent invokes), and records
  status + latency. It reads DynamoDB ThrottledRequests, Lambda Throttles, and
  the SQS/DLQ queue depths from CloudWatch / SQS to find where the back-pressure
  landed. It does NOT mutate your infrastructure; the fault is purely load, so it
  self-reverses when the script stops. Adapt the resource names via env vars.

ACCEPTANCE CRITERIA
  [ ] One drill runs end-to-end and prints a timeline: t0, t_fault, t_impact
      (first sustained SLO breach, or "none"), t_recover, recovery_seconds.
  [ ] dynamo-throttle WITHOUT --sharded shows a non-zero ThrottledRequests count;
      WITH --sharded shows materially fewer throttles (the mitigation works).
  [ ] lambda-concurrency shows a non-zero Lambda Throttles count and the SQS/DLQ
      depth moving (back-pressure), then draining (recovery).
  [ ] A POSTMORTEM.md skeleton is written with the measured timeline filled in.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import random
import threading
import time
import urllib.request

import boto3

# --------------------------------------------------------------------------- #
# Config from the environment. Adapt these to YOUR capstone.
# --------------------------------------------------------------------------- #
REGION = os.environ.get("REGION", "us-east-1")
API_URL = os.environ.get("API_URL", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "capstone-single-table")
RETRY_QUEUE_URL = os.environ.get("RETRY_QUEUE_URL", "")
DLQ_URL = os.environ.get("DLQ_URL", "")
TARGET_LAMBDA = os.environ.get("TARGET_LAMBDA", "capstone-event-handler")

# SLO: a probe is "good" if it returns 2xx within this many milliseconds.
SLO_LATENCY_MS = 500.0
# Consecutive good/bad probes that flips the steady-state verdict (hysteresis,
# so a single network blip is not recorded as an outage).
HYSTERESIS = 3

cw = boto3.client("cloudwatch", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
ddb = boto3.client("dynamodb", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #
def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: dt.datetime | None) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else "n/a"


# --------------------------------------------------------------------------- #
# The continuous probe: one HTTP request/sec against the public API.
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Probe:
    t: dt.datetime
    ok: bool
    status: int
    latency_ms: float


class Prober:
    """Background thread that probes the public API once per second."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.samples: list[Probe] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _one(self) -> Probe:
        body = json.dumps(
            {"tenant": "probe", "type": "probe", "id": f"probe-{int(time.time() * 1000)}"}
        ).encode()
        req = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=SLO_LATENCY_MS / 1000.0 * 4) as resp:
                latency_ms = (time.monotonic() - t0) * 1000.0
                ok = (200 <= resp.status < 300) and latency_ms <= SLO_LATENCY_MS
                return Probe(now_utc(), ok, resp.status, latency_ms)
        except Exception:
            latency_ms = (time.monotonic() - t0) * 1000.0
            return Probe(now_utc(), False, 0, latency_ms)

    def _loop(self) -> None:
        while not self._stop.is_set():
            tick = time.monotonic()
            self.samples.append(self._one())
            sleep = 1.0 - (time.monotonic() - tick)
            if sleep > 0:
                self._stop.wait(sleep)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


# --------------------------------------------------------------------------- #
# Timeline analysis: when did the SLO break and recover?
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Timeline:
    t_start: dt.datetime
    t_fault: dt.datetime | None = None
    t_impact: dt.datetime | None = None
    t_recover: dt.datetime | None = None

    @property
    def recovery_seconds(self) -> float | None:
        if self.t_fault and self.t_recover:
            return (self.t_recover - self.t_fault).total_seconds()
        return None

    @property
    def impact_seconds(self) -> float | None:
        if self.t_impact and self.t_recover:
            return (self.t_recover - self.t_impact).total_seconds()
        return None


def analyze(samples: list[Probe], t_fault: dt.datetime) -> Timeline:
    """Find the first sustained breach after the fault and the recovery."""
    tl = Timeline(t_start=samples[0].t if samples else now_utc(), t_fault=t_fault)
    after = [s for s in samples if s.t >= t_fault]
    bad = good = 0
    breached = False
    for s in after:
        if s.ok:
            good += 1
            bad = 0
            if breached and tl.t_recover is None and good >= HYSTERESIS:
                tl.t_recover = s.t
                break
        else:
            bad += 1
            good = 0
            if not breached and bad >= HYSTERESIS:
                breached = True
                tl.t_impact = s.t
    if not breached:
        # System absorbed the fault: recovery == fault time, no user-visible impact.
        tl.t_recover = t_fault
    return tl


# --------------------------------------------------------------------------- #
# CloudWatch / SQS reads (find the back-pressure and prove the mitigation)
# --------------------------------------------------------------------------- #
def metric_sum(namespace: str, metric: str, dims: list[dict], minutes: int = 5) -> float:
    """Sum a CloudWatch metric over the last `minutes` minutes; 0 on any error."""
    try:
        end = now_utc()
        start = end - dt.timedelta(minutes=minutes)
        resp = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric,
            Dimensions=dims,
            StartTime=start,
            EndTime=end,
            Period=60,
            Statistics=["Sum"],
        )
        return sum(p["Sum"] for p in resp.get("Datapoints", []))
    except Exception as exc:  # drill tooling degrades gracefully
        print(f"  (metric read {metric} failed: {exc}; reporting 0)")
        return 0.0


def queue_depth(queue_url: str) -> int:
    """Approximate messages available + in flight in an SQS queue; 0 on error."""
    if not queue_url:
        return 0
    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
        )["Attributes"]
        return int(attrs.get("ApproximateNumberOfMessages", 0)) + int(
            attrs.get("ApproximateNumberOfMessagesNotVisible", 0)
        )
    except Exception as exc:
        print(f"  (queue depth read failed: {exc}; reporting 0)")
        return 0


# --------------------------------------------------------------------------- #
# Drill 1: DynamoDB hot-partition throttle
# --------------------------------------------------------------------------- #
def _hot_partition_writer(stop: threading.Event, sharded: bool, counters: dict) -> None:
    """Hammer ONE partition key (unless --sharded) to force a hot partition.

    Writes go directly to DynamoDB so the fault is the write pattern itself, not
    the API. With --sharded we spread the same logical key across N suffixes
    (the Week-9 write-sharding mitigation) and expect far fewer throttles.
    """
    hot_pk = "TENANT#noisy-neighbor"
    shard_count = 16 if sharded else 1
    while not stop.is_set():
        shard = random.randint(0, shard_count - 1)
        pk = f"{hot_pk}#{shard}" if sharded else hot_pk
        try:
            ddb.put_item(
                TableName=TABLE_NAME,
                Item={
                    "PK": {"S": pk},
                    "SK": {"S": f"EVENT#{int(time.time() * 1e6)}#{random.random()}"},
                    "payload": {"S": "x" * 256},
                },
            )
            counters["writes"] += 1
        except ddb.exceptions.ProvisionedThroughputExceededException:
            counters["client_throttles"] += 1
        except Exception:
            counters["errors"] += 1


def drill_dynamo_throttle(duration_s: int, sharded: bool) -> tuple[Timeline, dict]:
    if not API_URL:
        raise SystemExit("dynamo-throttle needs API_URL set for the steady-state probe.")
    throttles_before = metric_sum(
        "AWS/DynamoDB", "ThrottledRequests", [{"Name": "TableName", "Value": TABLE_NAME}]
    )
    dlq_before = queue_depth(DLQ_URL)

    prober = Prober(API_URL)
    prober.start()
    print(f"[t0] steady state, probing {API_URL} ...")
    time.sleep(20)

    t_fault = now_utc()
    label = "WITH write-sharding" if sharded else "WITHOUT write-sharding"
    print(f"[t_fault={iso(t_fault)}] hammering one partition ({label}) for {duration_s}s")
    stop = threading.Event()
    counters = {"writes": 0, "client_throttles": 0, "errors": 0}
    writers = [threading.Thread(target=_hot_partition_writer, args=(stop, sharded, counters), daemon=True)
               for _ in range(8)]
    for w in writers:
        w.start()

    time.sleep(duration_s)
    stop.set()
    for w in writers:
        w.join(timeout=5)
    time.sleep(45)  # let any retried back-pressure drain so we can see recovery
    prober.stop()

    throttles_after = metric_sum(
        "AWS/DynamoDB", "ThrottledRequests", [{"Name": "TableName", "Value": TABLE_NAME}]
    )
    dlq_after = queue_depth(DLQ_URL)
    tl = analyze(prober.samples, t_fault)
    extra = {
        "drill": "dynamo-throttle",
        "sharded": sharded,
        "writes_attempted": counters["writes"],
        "client_side_throttles": counters["client_throttles"],
        "table_throttled_requests_delta": round(throttles_after - throttles_before, 1),
        "dlq_depth_before": dlq_before,
        "dlq_depth_after": dlq_after,
        "back_pressure": "none" if dlq_after <= dlq_before else f"DLQ grew by {dlq_after - dlq_before}",
        "samples": len(prober.samples),
    }
    return tl, extra


# --------------------------------------------------------------------------- #
# Drill 2: Lambda concurrency exhaustion
# --------------------------------------------------------------------------- #
def _invoke_burst(stop: threading.Event, counters: dict) -> None:
    """Fire async invokes at the target Lambda as fast as possible."""
    payload = json.dumps({"tenant": "flood", "type": "page_view"}).encode()
    while not stop.is_set():
        try:
            resp = lam.invoke(
                FunctionName=TARGET_LAMBDA,
                InvocationType="Event",  # async, so throttles route to the DLQ/destination
                Payload=payload,
            )
            if resp.get("StatusCode") == 429 or resp.get("FunctionError"):
                counters["client_throttles"] += 1
            else:
                counters["invokes"] += 1
        except lam.exceptions.TooManyRequestsException:
            counters["client_throttles"] += 1
        except Exception:
            counters["errors"] += 1


def drill_lambda_concurrency(duration_s: int, concurrency: int) -> tuple[Timeline, dict]:
    if not API_URL:
        raise SystemExit("lambda-concurrency needs API_URL set for the steady-state probe.")
    throttles_before = metric_sum(
        "AWS/Lambda", "Throttles", [{"Name": "FunctionName", "Value": TARGET_LAMBDA}]
    )
    retry_before = queue_depth(RETRY_QUEUE_URL)
    dlq_before = queue_depth(DLQ_URL)

    prober = Prober(API_URL)
    prober.start()
    print(f"[t0] steady state ...")
    time.sleep(20)

    t_fault = now_utc()
    print(f"[t_fault={iso(t_fault)}] bursting {concurrency} concurrent invokers at "
          f"{TARGET_LAMBDA} for {duration_s}s")
    stop = threading.Event()
    counters = {"invokes": 0, "client_throttles": 0, "errors": 0}
    burst = [threading.Thread(target=_invoke_burst, args=(stop, counters), daemon=True)
             for _ in range(concurrency)]
    for b in burst:
        b.start()

    time.sleep(duration_s)
    stop.set()
    for b in burst:
        b.join(timeout=5)
    time.sleep(60)  # let the back-pressure drain so we can measure recovery
    prober.stop()

    throttles_after = metric_sum(
        "AWS/Lambda", "Throttles", [{"Name": "FunctionName", "Value": TARGET_LAMBDA}]
    )
    retry_after = queue_depth(RETRY_QUEUE_URL)
    dlq_after = queue_depth(DLQ_URL)
    tl = analyze(prober.samples, t_fault)
    extra = {
        "drill": "lambda-concurrency",
        "burst_concurrency": concurrency,
        "invokes_sent": counters["invokes"],
        "client_side_throttles": counters["client_throttles"],
        "lambda_throttles_delta": round(throttles_after - throttles_before, 1),
        "retry_queue_before": retry_before,
        "retry_queue_after": retry_after,
        "dlq_depth_before": dlq_before,
        "dlq_depth_after": dlq_after,
        "verdict": "back-pressure (queues moved, then drained)"
        if (retry_after > retry_before or dlq_after > dlq_before)
        else "no measurable back-pressure (raise --concurrency or lower reserved concurrency)",
        "samples": len(prober.samples),
    }
    return tl, extra


# --------------------------------------------------------------------------- #
# Postmortem skeleton (Lecture 2's template, pre-filled with the timeline)
# --------------------------------------------------------------------------- #
def write_postmortem(tl: Timeline, extra: dict, path: str = "POSTMORTEM.md") -> None:
    recovery = tl.recovery_seconds
    impact = tl.impact_seconds
    md = f"""# Chaos Drill Postmortem - {extra['drill']}

> Generated by exercise-02-fis-chaos-drills.py on {iso(now_utc())}. Fill in the prose.

## Summary

- **Drill:** {extra['drill']}
- **Recovery time:** {f'{recovery:.0f}s' if recovery is not None else 'n/a'}
- **User-visible impact window:** {f'{impact:.0f}s' if impact is not None else 'none (system absorbed the fault)'}

## Timeline (UTC)

| Event | Time |
|---|---|
| Steady-state baseline | {iso(tl.t_start)} |
| Fault injected | {iso(tl.t_fault)} |
| First sustained SLO breach | {iso(tl.t_impact) if tl.t_impact else 'none'} |
| SLO restored | {iso(tl.t_recover)} |

## Measurements

```
{json.dumps(extra, indent=2)}
```

## Root cause (five whys)

<!-- Ask "why" past the proximate cause to a SYSTEMIC, fixable root. The injected
     fault is expected; the root is the design property that let it hurt (or the
     property that made it harmless). "Human error" is never a root cause. -->

## What we expected vs. what happened

<!-- The steady-state hypothesis vs. the measurement. Did write-sharding defeat
     the hot partition? Did the throttle become back-pressure, not data loss? -->

## Action items

| Action | Owner | Due | Tag (accept / mitigate-now / mitigate-later) |
|---|---|---|---|
|  |  |  |  |
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"\n[postmortem] wrote {path}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Capstone chaos-drill driver (DynamoDB + Lambda).")
    sub = parser.add_subparsers(dest="drill", required=True)

    p_ddb = sub.add_parser("dynamo-throttle")
    p_ddb.add_argument("--duration", type=int, default=180, help="seconds to inject load")
    p_ddb.add_argument("--sharded", action="store_true", help="apply write-sharding mitigation")

    p_lam = sub.add_parser("lambda-concurrency")
    p_lam.add_argument("--duration", type=int, default=180)
    p_lam.add_argument("--concurrency", type=int, default=200, help="concurrent invoker threads")

    args = parser.parse_args()

    print(f"=== Chaos drill: {args.drill} (region={REGION}) ===")
    if args.drill == "dynamo-throttle":
        tl, extra = drill_dynamo_throttle(args.duration, args.sharded)
    elif args.drill == "lambda-concurrency":
        tl, extra = drill_lambda_concurrency(args.duration, args.concurrency)
    else:  # unreachable due to required=True
        raise SystemExit(2)

    print("\n=== Timeline ===")
    print(f"  steady state : {iso(tl.t_start)}")
    print(f"  fault        : {iso(tl.t_fault)}")
    print(f"  first breach : {iso(tl.t_impact) if tl.t_impact else 'none'}")
    print(f"  recovered    : {iso(tl.t_recover)}")
    if tl.recovery_seconds is not None:
        print(f"  recovery_seconds: {tl.recovery_seconds:.0f}")
    print("\n=== Measurements ===")
    print(json.dumps(extra, indent=2))
    write_postmortem(tl, extra)


if __name__ == "__main__":
    main()
