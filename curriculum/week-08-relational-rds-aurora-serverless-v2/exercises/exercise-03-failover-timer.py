#!/usr/bin/env python3
# Exercise 3 — Force an Aurora failover and measure read & write recovery time
#
# Goal: Trigger `failover-db-cluster` on your Exercise-1 cluster and measure,
#       with a polling harness you understand, two SEPARATE numbers:
#
#         * WRITE recovery time  — how long until the cluster (writer)
#           endpoint accepts a successful INSERT again.
#         * READ  recovery time  — how long until the reader endpoint
#           accepts a successful SELECT again.
#
#       They differ, and Lecture 1 (§1.4) tells you why: the writer endpoint
#       CNAME must re-point at the promoted reader and that instance must open
#       the shared volume for writes; reads can often continue against the
#       OTHER (surviving) reader almost uninterrupted. You will SEE that gap.
#
# Estimated time: 60 minutes.
#
# WHY A HARNESS INSTEAD OF A STOPWATCH
#
#   "Aurora fails over in 10-30 seconds" is a marketing range. Your job is to
#   produce YOUR number, for YOUR cluster, on YOUR instance class, and to put
#   it in the mini-project failover report. Eyeballing the console clock is not
#   a measurement. This harness polls both endpoints every ~250ms, records the
#   first failure and the first recovery on each, and prints a timeline.
#
# REQUIREMENTS
#
#   pip install "psycopg[binary]" boto3
#   - psycopg 3.x (the "psycopg" package, NOT psycopg2)
#   - boto3 for the failover API call
#   AWS credentials with rds:FailoverDBCluster on the cluster.
#   Run this from INSIDE the VPC (a bastion or the EKS pod from Exercise 2),
#   because the cluster lives in isolated subnets.
#
# USAGE
#
#   export PGPASSWORD=$(aws secretsmanager get-secret-value \
#       --secret-id week8/aurora/master --query SecretString --output text \
#       | jq -r .password)
#   python3 exercise-03-failover-timer.py \
#       --cluster-id week8aurorastack-auroraXXXX \
#       --writer week8....cluster-abc.us-east-1.rds.amazonaws.com \
#       --reader week8....cluster-ro-abc.us-east-1.rds.amazonaws.com \
#       --db appdb --user crunchadmin --region us-east-1
#
# ACCEPTANCE CRITERIA
#
#   [ ] The harness establishes a healthy baseline on BOTH endpoints first.
#   [ ] It triggers exactly one failover via the RDS API.
#   [ ] It reports write_recovery_seconds and read_recovery_seconds separately.
#   [ ] write_recovery_seconds > read_recovery_seconds (the expected ordering).
#   [ ] The total write recovery is in the ~10-30s ballpark for r7g.large.
#   [ ] The printed timeline is pasteable into the mini-project report.

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field

import boto3
import psycopg


POLL_INTERVAL_S = 0.25
BASELINE_PROBES = 8          # consecutive healthy probes before we fail over
RECOVERY_HEALTHY_STREAK = 4  # consecutive healthy probes that count as "recovered"
MAX_WAIT_S = 180             # give up after 3 minutes


@dataclass
class ProbeResult:
    """Rolling state for one endpoint's probe loop."""
    name: str
    failed_at: float | None = None       # first failure timestamp
    recovered_at: float | None = None     # first sustained-recovery timestamp
    healthy_streak: int = 0
    events: list[tuple[float, str]] = field(default_factory=list)

    def recovery_seconds(self) -> float | None:
        if self.failed_at is None or self.recovered_at is None:
            return None
        return self.recovered_at - self.failed_at


def connect(host: str, db: str, user: str, password: str) -> psycopg.Connection:
    """Open a short-lived TLS connection. autocommit so each probe is atomic."""
    return psycopg.connect(
        host=host,
        dbname=db,
        user=user,
        password=password,
        sslmode="require",
        connect_timeout=2,
        autocommit=True,
    )


def probe_write(host: str, db: str, user: str, password: str) -> bool:
    """A WRITE probe: connect to the writer endpoint and INSERT one row.
    Fails if the endpoint is read-only (old writer demoted) or unreachable."""
    try:
        with connect(host, db, user, password) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS failover_probe "
                "(id bigserial PRIMARY KEY, t timestamptz DEFAULT now())"
            )
            conn.execute("INSERT INTO failover_probe DEFAULT VALUES")
            return True
    except Exception:
        return False


def probe_read(host: str, db: str, user: str, password: str) -> bool:
    """A READ probe: connect to the reader endpoint and SELECT."""
    try:
        with connect(host, db, user, password) as conn:
            conn.execute("SELECT count(*) FROM failover_probe")
            return True
    except Exception:
        return False


def step(result: ProbeResult, ok: bool, now: float, triggered: bool) -> None:
    """Advance one endpoint's state machine by one probe."""
    if ok:
        result.healthy_streak += 1
        if (
            triggered
            and result.failed_at is not None
            and result.recovered_at is None
            and result.healthy_streak >= RECOVERY_HEALTHY_STREAK
        ):
            # Recovery time is measured to the FIRST of the healthy streak.
            result.recovered_at = now - (RECOVERY_HEALTHY_STREAK - 1) * POLL_INTERVAL_S
            result.events.append((result.recovered_at, f"{result.name}: RECOVERED"))
    else:
        result.healthy_streak = 0
        if triggered and result.failed_at is None:
            result.failed_at = now
            result.events.append((now, f"{result.name}: FAILED"))


def wait_for_baseline(args, pw: str) -> None:
    """Refuse to fail over until both endpoints are solidly healthy."""
    print("Establishing baseline (both endpoints must be healthy)...")
    healthy = 0
    while healthy < BASELINE_PROBES:
        w = probe_write(args.writer, args.db, args.user, pw)
        r = probe_read(args.reader, args.db, args.user, pw)
        if w and r:
            healthy += 1
            print(f"  baseline probe {healthy}/{BASELINE_PROBES} OK", end="\r")
        else:
            healthy = 0
            print(f"  baseline NOT healthy (write={w} read={r}); retrying...", end="\r")
        time.sleep(POLL_INTERVAL_S)
    print("\nBaseline healthy. Triggering failover.                          ")


def trigger_failover(cluster_id: str, region: str) -> None:
    rds = boto3.client("rds", region_name=region)
    rds.failover_db_cluster(DBClusterIdentifier=cluster_id)


def run(args) -> int:
    pw = os.environ.get("PGPASSWORD")
    if not pw:
        print("ERROR: set PGPASSWORD (the master password) before running.", file=sys.stderr)
        return 2

    wait_for_baseline(args, pw)

    write = ProbeResult("WRITE")
    read = ProbeResult("READ")

    trigger_failover(args.cluster_id, args.region)
    t0 = time.monotonic()
    triggered = True

    while True:
        now = time.monotonic()
        if now - t0 > MAX_WAIT_S:
            print(f"\nGiving up after {MAX_WAIT_S}s — failover did not complete cleanly.")
            break

        step(write, probe_write(args.writer, args.db, args.user, pw), now, triggered)
        step(read, probe_read(args.reader, args.db, args.user, pw), now, triggered)

        # Done when both have failed AND recovered.
        if write.recovered_at is not None and read.recovered_at is not None:
            break
        # If neither ever failed within ~10s, the failover may have been
        # transparent (rare for the writer); stop after a grace period.
        if now - t0 > 15 and write.failed_at is None and read.failed_at is None:
            print("\nNo failure observed within 15s — failover may have been transparent.")
            break

        time.sleep(POLL_INTERVAL_S)

    print_report(write, read, t0)
    return 0


def print_report(write: ProbeResult, read: ProbeResult, t0: float) -> None:
    print("\n" + "=" * 60)
    print("AURORA FAILOVER RECOVERY REPORT")
    print("=" * 60)

    timeline = sorted(write.events + read.events, key=lambda e: e[0])
    print("\nTimeline (seconds since failover trigger):")
    for ts, label in timeline:
        print(f"  +{ts - t0:6.2f}s   {label}")

    wr = write.recovery_seconds()
    rr = read.recovery_seconds()
    print("\nRecovery:")
    print(f"  WRITE recovery: {wr:6.2f}s" if wr is not None else "  WRITE recovery: (not observed)")
    print(f"  READ  recovery: {rr:6.2f}s" if rr is not None else "  READ  recovery: (not observed / minimal)")

    if wr is not None and rr is not None:
        print(f"\n  Write-vs-read gap: {wr - rr:+.2f}s")
        print(
            "  Expected: write recovery > read recovery, because the writer\n"
            "  endpoint CNAME must re-point at the promoted reader and that\n"
            "  instance must open the shared volume for writes, while the\n"
            "  reader endpoint can keep serving from the surviving reader\n"
            "  (Lecture 1 §1.4)."
        )
    print("=" * 60)


def main() -> int:
    p = argparse.ArgumentParser(description="Measure Aurora failover recovery time.")
    p.add_argument("--cluster-id", required=True, help="DB cluster identifier")
    p.add_argument("--writer", required=True, help="Cluster (writer) endpoint host")
    p.add_argument("--reader", required=True, help="Reader endpoint host")
    p.add_argument("--db", default="appdb")
    p.add_argument("--user", default="crunchadmin")
    p.add_argument("--region", default="us-east-1")
    return run(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

# ---------------------------------------------------------------------------
# EXPECTED OUTPUT (your numbers will differ; the ORDERING should not)
# ---------------------------------------------------------------------------
#
#   Establishing baseline (both endpoints must be healthy)...
#   Baseline healthy. Triggering failover.
#
#   ============================================================
#   AURORA FAILOVER RECOVERY REPORT
#   ============================================================
#
#   Timeline (seconds since failover trigger):
#     +  1.75s   WRITE: FAILED
#     +  2.25s   READ: FAILED
#     +  4.50s   READ: RECOVERED
#     + 14.25s   WRITE: RECOVERED
#
#   Recovery:
#     WRITE recovery:  12.50s
#     READ  recovery:   2.25s
#
#     Write-vs-read gap: +10.25s
#     Expected: write recovery > read recovery, because the writer
#     endpoint CNAME must re-point at the promoted reader and that
#     instance must open the shared volume for writes, while the
#     reader endpoint can keep serving from the surviving reader
#     (Lecture 1 §1.4).
#   ============================================================
#
# ---------------------------------------------------------------------------
# AFTER THE RUN
# ---------------------------------------------------------------------------
#   * Run it 3 times and report mean + min + max for both numbers — one
#     sample is not a measurement.
#   * Cross-check your write recovery against the RDS "Events" log:
#       aws rds describe-events --source-identifier <cluster-id> \
#         --source-type db-cluster --duration 10 \
#         --query 'Events[].{t:Date,m:Message}'
#     You will see "Started cross AZ failover" and "Completed failover" events.
#   * Paste the report into mini-project/ as part of the failover deliverable.
#   * TEAR DOWN the cluster when done: `cdk destroy Week8AuroraStack`.
