# Challenge 1 — Route 53 Health-Checked Failover: Run the Drill, Measure RTO and RPO

> **Estimated time:** 2.5–3 hours. This is the week's synthesis: the multi-Region DR posture, *proven* with a stopwatch, not asserted with a diagram. It is also the exact failover the capstone must demonstrate in Week 15.

## The problem

You have data replicating to a second Region (DynamoDB Global Tables and an Aurora Global Database from Exercise 3), encrypted with a multi-Region KMS key so the replica is decryptable (Exercise 2). What you do **not** yet have is a way to actually move *traffic* to the DR Region when the primary fails — and proof that it works. Your job: put two endpoints behind a Route 53 health-checked failover record, break the primary, and measure the **RTO** (how long until the DR Region serves) and the **RPO** (how much data was lost at the cut). Then write the drill report and the runbook a tired on-call engineer would follow at 3 a.m.

The two numbers you produce are the deliverable. "We're highly available" is not a DR plan; "RTO 4m12s, RPO 0s (DynamoDB) / 1.1s (Aurora), drilled 2026-06-12, runbook below" is.

## What you build

1. **Two endpoints**, one per Region, each returning a health response and the Region it is serving from. The simplest acceptable form is two API Gateway HTTP APIs (or two ALBs, or two CloudFront-fronted Lambdas) — one in `us-east-1` (primary), one in `us-west-2` (DR) — each behind a `/health` path and a `/whoami` path that returns its Region.
2. **A Route 53 health check** on the primary endpoint's `/health`, and **failover records** (`PRIMARY` + `SECONDARY`) for one DNS name pointing at the two endpoints, with a **low TTL**.
3. **A measurement harness** — a loop that hits the DNS name every second, logging which Region answered and the wall-clock time, so you can see the exact moment the flip completes (your RTO).
4. **An RPO probe** — a writer that writes monotonically increasing items to the DynamoDB Global Table (and/or Aurora) in the primary right up to the cut, so after failover you can count how many of the last writes made it to the DR Region (your RPO).
5. **A written `DRILL.md`** with the achieved-vs-target numbers, the timeline, and the runbook.

## Starter: the failover records (CDK)

```typescript
import * as route53 from 'aws-cdk-lib/aws-route53';

// A health check on the PRIMARY endpoint. Tight interval + threshold = fast detection.
const primaryHealth = new route53.CfnHealthCheck(this, 'PrimaryHealth', {
  healthCheckConfig: {
    type: 'HTTPS',
    fullyQualifiedDomainName: primaryApiDomain,   // e.g. abc123.execute-api.us-east-1.amazonaws.com
    resourcePath: '/health',
    port: 443,
    requestInterval: 30,        // check every 30s
    failureThreshold: 3,        // 3 consecutive failures => unhealthy => ~90s detection
  },
});

// PRIMARY failover record -- answered while the health check is healthy.
new route53.CfnRecordSet(this, 'ApiPrimary', {
  hostedZoneId: zone.hostedZoneId,
  name: 'api.capstone.example.com',
  type: 'CNAME',
  ttl: '60',                    // LOW ttl -- this is a floor on your RTO
  setIdentifier: 'primary',
  failover: 'PRIMARY',
  healthCheckId: primaryHealth.attrHealthCheckId,
  resourceRecords: [primaryApiDomain],
});

// SECONDARY failover record -- answered when the primary's health check fails.
new route53.CfnRecordSet(this, 'ApiSecondary', {
  hostedZoneId: zone.hostedZoneId,
  name: 'api.capstone.example.com',
  type: 'CNAME',
  ttl: '60',
  setIdentifier: 'secondary',
  failover: 'SECONDARY',
  resourceRecords: [drApiDomain],
});
```

If you do not own a domain, use a Route 53 *private* hosted zone with a made-up name and resolve against it from an EC2 instance in the VPC, or just observe the health-check state transition directly (`aws route53 get-health-check-status`) and the record Route 53 *would* return — the measurement is the same shape.

## Starter: the measurement harness

```python
import socket
import time
import urllib.request

DNS_NAME = "api.capstone.example.com"
PRIMARY_HINT = "us-east-1"   # /whoami returns the Region serving

def whoami() -> str:
    try:
        with urllib.request.urlopen(f"https://{DNS_NAME}/whoami", timeout=3) as r:
            return r.read().decode().strip()
    except Exception as e:
        return f"ERROR({e.__class__.__name__})"

def main():
    print("time_s,region_served")
    t0 = time.time()
    flipped_at = None
    while time.time() - t0 < 600:        # watch up to 10 minutes
        region = whoami()
        t = time.time() - t0
        print(f"{t:6.1f},{region}")
        if flipped_at is None and region.startswith("us-west-2"):
            flipped_at = t
            print(f"# FLIP: DR Region serving at t={t:.1f}s (this is your RTO)")
        time.sleep(1)

if __name__ == "__main__":
    main()
```

## Starter: the RPO probe

```python
import time
import boto3

ddb = boto3.client("dynamodb", region_name="us-east-1")
TABLE = "c19-wk13-app"

def writer():
    """Write monotonically increasing items to the primary until interrupted (Ctrl-C
    at the moment you break the primary). The last-written seq is your 'before' mark."""
    seq = 0
    try:
        while True:
            seq += 1
            ddb.put_item(TableName=TABLE, Item={
                "pk": {"S": "rpo-probe"}, "sk": {"S": f"{seq:08d}"},
                "written_at": {"N": str(time.time())},
            })
            print(f"wrote seq={seq}")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"LAST WRITTEN seq={seq} in primary before cut")

# After failover, count what made it to the DR Region:
def count_in_dr(last_seq_in_primary: int):
    ddb_dr = boto3.client("dynamodb", region_name="us-west-2")
    resp = ddb_dr.query(
        TableName=TABLE,
        KeyConditionExpression="pk = :p",
        ExpressionAttributeValues={":p": {"S": "rpo-probe"}},
        ScanIndexForward=False, Limit=1,
    )
    last_in_dr = int(resp["Items"][0]["sk"]["S"]) if resp["Items"] else 0
    lost = last_seq_in_primary - last_in_dr
    print(f"last in primary={last_seq_in_primary}, last in DR={last_in_dr}, lost={lost} writes")
    # lost writes x your write interval ~= RPO in seconds
```

## How to run the drill

1. Deploy both endpoints and the failover records. Confirm `dig api.capstone.example.com` and `/whoami` return the **primary** (`us-east-1`).
2. Start the measurement harness in one terminal and the RPO probe writer in another.
3. **Break the primary**: the cleanest "Region failure" simulation that exercises the *real* path is to make the primary's `/health` start failing — e.g. flip a feature flag the health endpoint reads, stop the primary Lambda/service, or (Route 53 specific) `aws route53 update-health-check --health-check-id ... --disabled` is *not* it; instead point the health check at a path that now 500s, or stop the backing service so `/health` times out. Note the wall-clock moment.
4. **Stop the RPO writer** (Ctrl-C) at the same moment and record the last seq written.
5. Watch the harness: Route 53 needs `requestInterval × failureThreshold` (~90s here) to mark the primary unhealthy, then up to `TTL` (60s) for clients to re-resolve. The harness prints the `FLIP` line when `/whoami` first returns `us-west-2`. That elapsed time is your **RTO**.
6. Run `count_in_dr(last_seq)` to find how many of the last writes reached the DR Region. `lost_writes × write_interval` is your DynamoDB **RPO**. For Aurora, read `AuroraGlobalDBReplicationLag` at the cut (Exercise 3's probe).
7. **Fail back**: restore the primary's health, watch Route 53 return to `PRIMARY`, and note that fail-*back* has its own RTO (and, if you wrote to the DR Region during the outage, its own reconciliation story).

## Acceptance criteria

- [ ] Two Region-distinct endpoints behind one Route 53 failover DNS name with a health check on the primary.
- [ ] The failover records use a **low TTL** (≤ 60s) and you can explain why the TTL is a floor on RTO.
- [ ] A measurement harness log showing the primary serving, the outage, and the moment the DR Region begins serving — with the elapsed **RTO** marked.
- [ ] An RPO measurement: the number of writes lost at the cut (DynamoDB) and/or the Aurora replication lag at the cut, converted to seconds.
- [ ] A `DRILL.md` containing:
  - The **DR posture** you implemented, named (warm standby / pilot light / …).
  - **Target** RTO and RPO and **achieved** RTO and RPO, side by side. If you missed a target, say so and explain why (e.g. health-check detection + TTL exceeded your RTO target; Aurora's ~1.1s exceeded a ≤1s RPO target).
  - The **detection + propagation breakdown** of the RTO (health-check time vs DNS TTL vs DR warm-up).
  - A **runbook**: the ordered steps an on-call engineer follows to fail over manually and to fail back, including how they *confirm* the DR Region has current data before cutting traffic.
- [ ] The warm-standby resources (Aurora Global secondary, DynamoDB replica) are torn down after you capture the numbers.

## Stretch

- Make the failover **automatic end-to-end**: a GuardDuty/CloudWatch-alarm-driven Lambda that promotes the Aurora secondary on a sustained primary-Region health failure, so the DB write tier follows the DNS flip without a human.
- Add a **second DR Region** (three-Region Global Table) and reason about which Region Route 53 fails over to and in what order.
- Measure **fail-back** RTO separately, and write the reconciliation note for the case where writes happened in *both* Regions during a partition (last-writer-wins on DynamoDB; manual on Aurora).
- Replace the manual "break the primary" with an actual scaled-down outage: drain the primary's ECS/EKS service to zero and confirm the health check and failover behave identically to the simulated break.

## What "good" looks like

A strong `DRILL.md` reads like a real incident-drill artifact: it names the posture, states target and achieved numbers side by side, breaks the RTO into its detection-and-propagation parts, *admits where a target was missed and why*, and gives a runbook a stranger could execute. A weak submission says "failover works" with no number, or claims an RTO of "a few seconds" that ignores the 90s health-check detection and the 60s TTL that physics imposes. The entire week — the entire course — is built to make you the first kind of engineer: the one whose DR plan has been tested and whose numbers are real.
