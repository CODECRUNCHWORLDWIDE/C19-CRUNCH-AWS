#!/usr/bin/env python3
"""
Exercise 2 — Read the optimization recommendations AWS already computed for you,
compute the Savings Plan commitment break-even, and quantify a Graviton move.

Estimated time: ~75 minutes.
Cost: ~free. This script only READS recommendations via the Cost Explorer,
      Savings Plans, and Compute Optimizer APIs. It does NOT purchase a Savings
      Plan (that is a real 1- or 3-year financial commitment -- never do it from
      a lab script). The homework discusses purchasing; here you only analyze.

WHAT THIS DOES
--------------
  1. Pulls AWS's own SAVINGS PLAN purchase recommendation (Cost Explorer's
     get_savings_plans_purchase_recommendation) and prints the proposed
     hourly commitment, the estimated monthly savings, and the projected
     utilization -- then computes the break-even and a commitment-risk note.
  2. Pulls COMPUTE OPTIMIZER rightsizing recommendations for EC2 instances and
     Lambda functions, listing the over-provisioned resources and the estimated
     monthly savings of acting on each.
  3. Computes a GRAVITON (arm64) price/performance comparison from the public
     on-demand prices you supply, showing the monthly delta of moving a fleet
     from an x86 family to its Graviton equivalent.

The headline outputs are three numbers you carry into the cost report and the
Friday challenge: the SP break-even utilization, the largest rightsizing win,
and the Graviton monthly saving.

HOW TO RUN
----------
    python -m venv .venv && source .venv/bin/activate
    pip install boto3
    export REGION=us-east-1     # Cost Explorer / Savings Plans are us-east-1 endpoints
    python exercise-02-savings-plan-rightsizing-graviton.py

PREREQUISITES
-------------
  - Cost Explorer is enabled on the account (it is, if you've used it once).
  - Compute Optimizer is OPTED IN. If you've never opted in, run:
        aws compute-optimizer update-enrollment-status --status Active
    and wait up to ~24h for the first recommendations to populate.
  - Some usage history (a few days of EC2/Lambda) so the recommenders have data.
    On a brand-new account these may return empty -- the script handles that and
    still runs the Graviton math, which needs no account data.

ACCEPTANCE CRITERIA
-------------------
  [ ] The script prints AWS's Savings Plan recommendation (or notes none) AND a
      break-even utilization you computed, not just AWS's number.
  [ ] It lists at least the structure of Compute Optimizer rightsizing findings
      (or notes none yet) with estimated monthly savings.
  [ ] It prints a Graviton x86-vs-arm64 monthly delta for the supplied fleet.
  [ ] You can explain, in one sentence each, the commitment-risk and the
      rightsize-before-commit ordering caveat from Lecture 1.

SMOKE OUTPUT (your numbers will differ)
---------------------------------------
    === Savings Plan recommendation (COMPUTE_SP, 1yr, NO_UPFRONT) ===
    AWS proposes committing:           $0.412/hr
    Estimated monthly savings:         $128.40  (~31% off the covered usage)
    Estimated avg utilization:         96.4%
    Your break-even utilization:       ~69.0%  (below this, you waste commitment)
    Commitment risk if steady-state -20%: ~$59.3/mo of committed-but-idle spend

    === Compute Optimizer: over-provisioned EC2 ===
    i-0abc...  m5.2xlarge -> m5.large   (~75% / $211.30/mo)

    === Graviton move: m7i.xlarge fleet (10) -> m7g.xlarge ===
    x86  on-demand:  $0.2016/hr  -> $1,471.7/mo
    arm  on-demand:  $0.1632/hr  -> $1,191.4/mo
    monthly saving:  $280.3  (~19.0%)   (before any perf/throughput difference)
"""

from __future__ import annotations

import os

import boto3

REGION = os.environ.get("REGION", "us-east-1")

HOURS_PER_MONTH = 730  # AWS's standard month for cost math

ce = boto3.client("ce", region_name=REGION)
co = boto3.client("compute-optimizer", region_name=REGION)


# ---------------------------------------------------------------------------
# 1) Savings Plan recommendation + your own break-even
# ---------------------------------------------------------------------------
def savings_plan_analysis() -> None:
    print("=== Savings Plan recommendation (COMPUTE_SP, 1yr, NO_UPFRONT) ===")
    try:
        resp = ce.get_savings_plans_purchase_recommendation(
            SavingsPlansType="COMPUTE_SP",
            TermInYears="ONE_YEAR",
            PaymentOption="NO_UPFRONT",
            LookbackPeriodInDays="THIRTY_DAYS",
        )
    except Exception as exc:  # noqa: BLE001 - we want to keep going to the Graviton math
        print(f"  (could not fetch recommendation: {exc})")
        print("  This is normal on a new/low-usage account. Skipping to rightsizing.\n")
        return

    detail = resp.get("SavingsPlansPurchaseRecommendation", {})
    summary = detail.get("SavingsPlansPurchaseRecommendationSummary", {})
    if not summary:
        print("  AWS returned no recommendation (insufficient usage history).")
        print("  On a real steady-state account this would propose an $/hr commitment.\n")
        # Still demonstrate the break-even arithmetic with illustrative numbers:
        _explain_break_even(hourly_commit=0.412, discount_pct=31.0)
        return

    hourly = float(summary.get("HourlyCommitmentToPurchase", 0) or 0)
    monthly_savings = float(summary.get("EstimatedMonthlySavingsAmount", 0) or 0)
    savings_pct = float(summary.get("EstimatedSavingsPercentage", 0) or 0)
    utilization = float(summary.get("EstimatedAverageUtilization", 0) or 0)

    print(f"  AWS proposes committing:           ${hourly:.3f}/hr")
    print(f"  Estimated monthly savings:         ${monthly_savings:.2f}  "
          f"(~{savings_pct:.0f}% off the covered usage)")
    print(f"  Estimated avg utilization:         {utilization:.1f}%")
    _explain_break_even(hourly_commit=hourly, discount_pct=savings_pct)


def _explain_break_even(hourly_commit: float, discount_pct: float) -> None:
    """
    The break-even utilization: a Savings Plan bills the committed $/hr whether or
    not you use it. Below some utilization, the wasted (idle) commitment costs more
    than you saved on the used portion, and you'd have been better on-demand.

    discounted_rate = on_demand * (1 - d).  You pay `commit` per hour regardless.
    You save (on_demand - discounted_rate) per UTILIZED hour. You waste `commit`
    per UNUTILIZED hour. Break-even utilization u solves:
        savings_on_used = waste_on_idle
        u * (on_demand - discounted) = (1 - u) * commit
    With commit == discounted (you commit at the discounted rate) and
    on_demand = commit / (1 - d):
        u * (commit/(1-d) - commit) = (1 - u) * commit
        u * (d/(1-d))               = (1 - u)
        u                          = (1 - d)
    => break-even utilization is simply (1 - discount). Neat and worth knowing.
    """
    d = discount_pct / 100.0
    if d <= 0:
        print("  (no discount figure available to compute break-even)\n")
        return
    break_even_util = (1 - d) * 100
    print(f"  Your break-even utilization:       ~{break_even_util:.1f}%  "
          f"(below this, you waste commitment)")
    # Commitment risk if steady-state drops 20% below the commitment:
    monthly_commit = hourly_commit * HOURS_PER_MONTH
    risk = monthly_commit * 0.20
    print(f"  Commitment risk if steady-state -20%: ~${risk:.1f}/mo of committed-but-idle spend")
    print("  Caveat (Lecture 1): commit ~80-90% of the OBSERVED FLOOR, not the average,")
    print("  and RIGHTSIZE FIRST so you don't commit to soon-to-shrink capacity.\n")


# ---------------------------------------------------------------------------
# 2) Compute Optimizer rightsizing
# ---------------------------------------------------------------------------
def rightsizing_analysis() -> None:
    print("=== Compute Optimizer: over-provisioned EC2 ===")
    try:
        resp = co.get_ec2_instance_recommendations(
            filters=[{"name": "Finding", "values": ["Overprovisioned"]}],
            maxResults=10,
        )
    except co.exceptions.OptInRequiredException:
        print("  Compute Optimizer is not opted in. Run:")
        print("    aws compute-optimizer update-enrollment-status --status Active")
        print("  then wait up to ~24h for recommendations.\n")
        return
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not fetch EC2 recommendations: {exc})\n")
        return

    recs = resp.get("instanceRecommendations", [])
    if not recs:
        print("  No over-provisioned EC2 instances found (good, or not enough history).")
    for rec in recs:
        current = rec["currentInstanceType"]
        options = rec.get("recommendationOptions", [])
        if not options:
            continue
        best = options[0]
        target = best["instanceType"]
        opp = best.get("savingsOpportunity", {})
        pct = opp.get("savingsOpportunityPercentage", 0)
        usd = opp.get("estimatedMonthlySavings", {}).get("value", 0)
        iid = rec["instanceArn"].split("/")[-1]
        print(f"  {iid}  {current} -> {target}   (~{pct:.0f}% / ${usd:.2f}/mo)")
    print("  CAVEAT: Compute Optimizer is blind to MEMORY unless the CloudWatch agent")
    print("  reports it -- a memory-blind downsize can OOM you. Enable memory metrics")
    print("  before trusting a memory-sensitive recommendation.\n")

    # Lambda rightsizing is a separate call -- show its shape too.
    try:
        lresp = co.get_lambda_function_recommendations(maxResults=10)
        lrecs = lresp.get("lambdaFunctionRecommendations", [])
        print("=== Compute Optimizer: Lambda memory rightsizing ===")
        if not lrecs:
            print("  No Lambda recommendations yet.")
        for r in lrecs:
            name = r["functionArn"].split(":")[-1]
            finding = r.get("finding", "?")
            opts = r.get("memorySizeRecommendationOptions", [])
            tgt = opts[0]["memorySize"] if opts else "?"
            print(f"  {name}: {finding}, current {r.get('currentMemorySize')}MB -> {tgt}MB")
        print()
    except Exception as exc:  # noqa: BLE001
        print(f"  (Lambda recommendations unavailable: {exc})\n")


# ---------------------------------------------------------------------------
# 3) Graviton (arm64) price/performance move -- pure arithmetic, no account data
# ---------------------------------------------------------------------------
def graviton_analysis(
    x86_type: str = "m7i.xlarge",
    x86_hourly: float = 0.2016,   # verify on the pricing page; illustrative
    arm_type: str = "m7g.xlarge",
    arm_hourly: float = 0.1632,   # verify; Graviton is typically ~15-20% cheaper
    fleet_size: int = 10,
) -> None:
    print(f"=== Graviton move: {x86_type} fleet ({fleet_size}) -> {arm_type} ===")
    x86_monthly = x86_hourly * HOURS_PER_MONTH * fleet_size
    arm_monthly = arm_hourly * HOURS_PER_MONTH * fleet_size
    saving = x86_monthly - arm_monthly
    pct = (saving / x86_monthly * 100) if x86_monthly else 0
    print(f"  x86  on-demand:  ${x86_hourly:.4f}/hr  -> ${x86_monthly:,.1f}/mo")
    print(f"  arm  on-demand:  ${arm_hourly:.4f}/hr  -> ${arm_monthly:,.1f}/mo")
    print(f"  monthly saving:  ${saving:,.1f}  (~{pct:.1f}%)   "
          f"(before any perf/throughput difference)")
    print("  REMEMBER: the price delta is only half the story. Graviton often also")
    print("  delivers MORE throughput per dollar, so measure price-PER-REQUEST after")
    print("  a multi-arch rebuild (Week 7) and real traffic, not just instance price.\n")


def main() -> None:
    print(f"Region={REGION}  HoursPerMonth={HOURS_PER_MONTH}\n")
    savings_plan_analysis()
    rightsizing_analysis()
    graviton_analysis()
    print("Done. Carry three numbers into the cost report:")
    print("  1) the SP break-even utilization,")
    print("  2) the largest rightsizing monthly win,")
    print("  3) the Graviton monthly saving for your fleet.")


if __name__ == "__main__":
    main()
