#!/usr/bin/env python3
"""Exercise 3 — Run IAM Access Analyzer Across the Three Accounts and Triage.

Goal
----
Enable an EXTERNAL-access analyzer and an UNUSED-access analyzer, wait for them
to produce findings, then list every finding, classify it (external exposure vs
unused permission), and print a triage report you can paste into your engineering
journal. The point is not the script — it is that you read each finding out loud
and decide: archive-with-justification (intended) or remediate (a real hole).

Estimated time: ~3 hours (most of it is triage, not coding).

Why a script and not the console
---------------------------------
Access Analyzer is something you run *continuously*, not once. Doing it in
boto3 forces you to learn the API shape (analyzers -> findings -> archive rules)
that you will later wire into CI. The console hides the structure; the SDK shows it.

What this script does
---------------------
1. Creates (or reuses) one ACCOUNT-zone external-access analyzer per account.
2. Creates (or reuses) one UNUSED_ACCESS analyzer with a 90-day window.
3. Lists active findings from both, joins them into one table, and classifies.
4. Prints a triage report: counts by type, then one line per finding with a
   suggested action. YOU fill in the justification column by hand.

It does NOT auto-archive or auto-remediate. Security tooling that mutates state
without a human in the loop is how you delete the wrong role at 2am.

Prerequisites
-------------
    python3 -m pip install "boto3>=1.35.0"
    # Profiles from Exercise 1: identity-sso, dev, prod
    aws sso login --profile identity-sso

Run
---
    python3 exercise-03-access-analyzer.py --profile dev   --region us-east-1
    python3 exercise-03-access-analyzer.py --profile prod  --region us-east-1
    # ...and your identity/management profile if separate.

Access Analyzer is FREE for external-access analysis. Unused-access analysis is
billed per resource monitored per month; at lab scale it is cents, but tear it
down (`--teardown`) when you are done if cost is a hard constraint.

Acceptance criteria
-------------------
  [ ] An external-access analyzer and an unused-access analyzer exist in each
      account (verify: aws accessanalyzer list-analyzers).
  [ ] The script prints a triage table with every active finding.
  [ ] You have written a one-line justification for every finding you ARCHIVE
      and opened a remediation note for every finding you do NOT archive.
  [ ] Re-running the script after remediation shows a clean (or fully-justified)
      report — that clean report is the mini-project deliverable.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

EXTERNAL_ANALYZER_NAME = "crunch-external-access"
UNUSED_ANALYZER_NAME = "crunch-unused-access"
UNUSED_WINDOW_DAYS = 90


@dataclass
class TriagedFinding:
    """One finding, normalized across the two analyzer types."""

    analyzer: str  # "external" | "unused"
    finding_id: str
    resource: str
    resource_type: str
    detail: str
    status: str
    suggested_action: str


def get_client(profile: str, region: str):
    session = boto3.Session(profile_name=profile, region_name=region)
    return session.client("accessanalyzer")


def ensure_analyzer(client, name: str, analyzer_type: str) -> str:
    """Create the analyzer if absent; return its ARN. Idempotent."""
    existing = client.list_analyzers(type=analyzer_type).get("analyzers", [])
    for a in existing:
        if a["name"] == name:
            print(f"  reusing {analyzer_type} analyzer: {name}")
            return a["arn"]

    kwargs = {"analyzerName": name, "type": analyzer_type}
    if analyzer_type == "ACCOUNT_UNUSED_ACCESS":
        kwargs["configuration"] = {
            "unusedAccess": {"unusedAccessAge": UNUSED_WINDOW_DAYS}
        }
    arn = client.create_analyzer(**kwargs)["arn"]
    print(f"  created {analyzer_type} analyzer: {name}")
    return arn


def wait_for_findings(client, analyzer_arn: str, timeout_s: int = 90) -> None:
    """External analyzers scan asynchronously after creation. Poll briefly."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = client.get_analyzer(
            analyzerName=analyzer_arn.split("/")[-1]
        )["analyzer"]["status"]
        if status == "ACTIVE":
            return
        time.sleep(5)
    print("  (analyzer still warming up; findings may be incomplete this run)")


def list_external_findings(client, analyzer_arn: str) -> list[TriagedFinding]:
    out: list[TriagedFinding] = []
    paginator = client.get_paginator("list_findings_v2")
    for page in paginator.paginate(
        analyzerArn=analyzer_arn,
        filter={"status": {"eq": ["ACTIVE"]}},
    ):
        for f in page.get("findings", []):
            resource = f.get("resource", "(unknown)")
            rtype = f.get("resourceType", "(unknown)")
            # External findings tell you WHO outside your zone of trust can reach
            # the resource. That is the dangerous direction — read it out loud.
            principal = f.get("principal", {})
            detail = f"reachable by external principal: {principal or 'public/anonymous'}"
            action = "REVIEW: is this exposure intended? If yes, archive with reason."
            out.append(
                TriagedFinding(
                    analyzer="external",
                    finding_id=f["id"],
                    resource=resource,
                    resource_type=rtype,
                    detail=detail,
                    status=f.get("status", "ACTIVE"),
                    suggested_action=action,
                )
            )
    return out


def list_unused_findings(client, analyzer_arn: str) -> list[TriagedFinding]:
    out: list[TriagedFinding] = []
    paginator = client.get_paginator("list_findings_v2")
    for page in paginator.paginate(
        analyzerArn=analyzer_arn,
        filter={"status": {"eq": ["ACTIVE"]}},
    ):
        for f in page.get("findings", []):
            ftype = f.get("findingType", "UnusedPermission")
            resource = f.get("resource", "(unknown)")
            # Unused findings are least-privilege debt: a role/user/permission
            # nobody has touched in UNUSED_WINDOW_DAYS days.
            detail = f"{ftype}: no use in {UNUSED_WINDOW_DAYS}d"
            action = "REMEDIATE: remove the unused role/permission, or justify why it must stay."
            out.append(
                TriagedFinding(
                    analyzer="unused",
                    finding_id=f["id"],
                    resource=resource,
                    resource_type=f.get("resourceType", "AWS::IAM::Role"),
                    detail=detail,
                    status=f.get("status", "ACTIVE"),
                    suggested_action=action,
                )
            )
    return out


def print_report(profile: str, findings: list[TriagedFinding]) -> None:
    external = [f for f in findings if f.analyzer == "external"]
    unused = [f for f in findings if f.analyzer == "unused"]

    print("\n" + "=" * 78)
    print(f"ACCESS ANALYZER TRIAGE REPORT — profile={profile}")
    print("=" * 78)
    print(f"  external-access findings (resources reachable from outside): {len(external)}")
    print(f"  unused-access findings   (least-privilege debt):             {len(unused)}")
    print("-" * 78)

    if not findings:
        print("  CLEAN. No active findings. (This is the mini-project target.)")
        print("=" * 78)
        return

    print(f"  {'#':<3} {'TYPE':<9} {'RESOURCE':<42} ACTION")
    print("-" * 78)
    for i, f in enumerate(findings, start=1):
        res = (f.resource[:39] + "...") if len(f.resource) > 42 else f.resource
        print(f"  {i:<3} {f.analyzer:<9} {res:<42} {f.suggested_action}")
        print(f"      detail   : {f.detail}")
        print(f"      finding  : {f.finding_id}")
        print(f"      JUSTIFY  : __________________________________________  (fill in)")
    print("=" * 78)
    print(
        "  For each finding: ARCHIVE (intended) with a written reason, or REMEDIATE.\n"
        "  Archive in the console/CLI:\n"
        "    aws accessanalyzer update-findings --analyzer-arn <arn> \\\n"
        "      --ids <id> --status ARCHIVED"
    )


def teardown(client) -> None:
    for name in (EXTERNAL_ANALYZER_NAME, UNUSED_ANALYZER_NAME):
        try:
            client.delete_analyzer(analyzerName=name)
            print(f"  deleted analyzer: {name}")
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="AWS named profile")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--teardown",
        action="store_true",
        help="Delete the analyzers this script created and exit.",
    )
    args = parser.parse_args()

    client = get_client(args.profile, args.region)

    if args.teardown:
        print(f"Tearing down analyzers in profile={args.profile} ...")
        teardown(client)
        return 0

    print(f"Ensuring analyzers exist in profile={args.profile}, region={args.region} ...")
    ext_arn = ensure_analyzer(client, EXTERNAL_ANALYZER_NAME, "ACCOUNT")
    unused_arn = ensure_analyzer(client, UNUSED_ANALYZER_NAME, "ACCOUNT_UNUSED_ACCESS")

    print("Waiting for the external analyzer to finish its first scan ...")
    wait_for_findings(client, ext_arn)

    findings: list[TriagedFinding] = []
    try:
        findings += list_external_findings(client, ext_arn)
        findings += list_unused_findings(client, unused_arn)
    except ClientError as e:
        # Unused-access findings can lag the analyzer's first scan by minutes.
        print(f"  note: {e.response['Error']['Code']} while listing — re-run shortly.")

    print_report(args.profile, findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
