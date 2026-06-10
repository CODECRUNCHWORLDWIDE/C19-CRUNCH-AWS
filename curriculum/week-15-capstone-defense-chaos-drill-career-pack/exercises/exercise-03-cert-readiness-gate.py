#!/usr/bin/env python3
"""
Exercise 3 - SAP-C02 / DOP-C02 practice exam + >=70% readiness gate.

A self-contained practice exam scorer for the career pack. The question bank below
is ORIGINAL, modeled on the *style* of the AWS Certified Solutions Architect -
Professional (SAP-C02) and AWS Certified DevOps Engineer - Professional (DOP-C02)
blueprints. It is NOT a copy of any official exam. Each question is tagged with the
blueprint domain it exercises, so the scorer tells you not just whether you cleared
the >=70% gate but WHICH domains are weak, so you know where to study before you
sit the real test. The domains map to the same weeks of C19 that taught them.

USAGE
  python3 exercise-03-cert-readiness-gate.py             # interactive, all questions
  python3 exercise-03-cert-readiness-gate.py --domain reliability   # one domain only
  python3 exercise-03-cert-readiness-gate.py --exam sap  # SAP-C02 domains only
  python3 exercise-03-cert-readiness-gate.py --exam dop  # DOP-C02 domains only
  python3 exercise-03-cert-readiness-gate.py --review    # print answers+rationale, no quiz
  python3 exercise-03-cert-readiness-gate.py --self-test # verify the bank is consistent

GATE
  Prints "READINESS GATE: PASS" iff score >= 70%. Otherwise PARTIAL/FAIL with a
  per-domain breakdown and a study plan pointing at your two weakest domains and
  the C19 weeks that cover them.

No AWS access or network required. Pure standard library.
"""

from __future__ import annotations

import argparse
import dataclasses
import random
import sys
import textwrap

PASS_THRESHOLD = 0.70

# Which exam each domain belongs to, and the C19 weeks that cover it.
DOMAIN_META = {
    "org-complexity":   ("sap", "Weeks 1, 2, 4 - Organizations, SCPs, IAM, multi-account, networking"),
    "new-solutions":    ("sap", "Weeks 5, 8, 9, 10, 11 - compute/data/event design choices"),
    "continuous-improve": ("sap", "Weeks 12, 13, 14 - observability, security, DR, FinOps"),
    "migration":        ("sap", "Weeks 6, 8 - storage and database migration/modernization"),
    "sdlc-automation":  ("dop", "Weeks 3, 7 - CDK, CodePipeline, CodeDeploy, OIDC CI"),
    "iac":              ("dop", "Week 3 - CloudFormation/CDK, drift, reproducible infra"),
    "reliability":      ("dop", "Weeks 13, 15 - multi-region DR, chaos, RTO/RPO"),
    "monitoring":       ("dop", "Week 12 - CloudWatch, X-Ray, OpenTelemetry, SLO alarms"),
    "incident-response": ("dop", "Week 15 - postmortems, runbooks, on-call"),
    "security":         ("dop", "Weeks 2, 13 - IAM, KMS, GuardDuty, least privilege"),
}


@dataclasses.dataclass(frozen=True)
class Question:
    domain: str
    prompt: str
    options: tuple[str, ...]  # A, B, C, D
    answer: int               # 0-based index of the correct option
    rationale: str


# --------------------------------------------------------------------------- #
# Question bank. Domains mirror the SAP-C02 + DOP-C02 blueprints.
# --------------------------------------------------------------------------- #
BANK: list[Question] = [
    Question(
        domain="org-complexity",
        prompt=(
            "You must guarantee that no account in the 'dev' OU can ever launch resources "
            "in us-east-1, regardless of any IAM policy an account admin writes. What "
            "enforces this at the organization level?"
        ),
        options=(
            "An IAM policy attached to every role in the dev accounts.",
            "A Service Control Policy on the dev OU denying actions when "
            "aws:RequestedRegion equals us-east-1.",
            "A permission boundary on the dev account root user.",
            "A VPC endpoint policy in each dev account.",
        ),
        answer=1,
        rationale=(
            "An SCP on the OU is the only control an account admin cannot override; it sets "
            "the maximum permissions for every principal in the accounts below it. IAM "
            "policies (A) and permission boundaries (C) are per-account and can be changed by "
            "an account admin. (Week 1.)"
        ),
    ),
    Question(
        domain="org-complexity",
        prompt=(
            "A developer role must be able to do almost anything in the dev account EXCEPT "
            "write IAM, delete KMS keys, or touch production S3 buckets - and this limit must "
            "hold even if someone attaches an over-broad inline policy to the role. What do you use?"
        ),
        options=(
            "A permission boundary attached to the role that denies those actions.",
            "A wider IAM policy and a code review.",
            "An SCP denying all S3 access org-wide.",
            "A resource policy on the IAM service.",
        ),
        answer=0,
        rationale=(
            "A permission boundary caps the effective permissions of a principal regardless of "
            "what identity policies grant - the intersection of the boundary and the policy "
            "applies. This is the only safe way to delegate. (Week 2.)"
        ),
    ),
    Question(
        domain="new-solutions",
        prompt=(
            "A feature needs synchronous, single-digit-millisecond inference on the request "
            "path at steady high traffic. Cost matters. Which serving choice fits best?"
        ),
        options=(
            "A Bedrock on-demand call per request.",
            "A SageMaker real-time endpoint with >=2 instances across AZs.",
            "A SageMaker batch transform job triggered per request.",
            "A SageMaker serverless endpoint.",
        ),
        answer=1,
        rationale=(
            "Steady high traffic + synchronous + low latency = a real-time endpoint, and >=2 "
            "instances removes the single-AZ SPOF. Bedrock per-token (A) is cheaper only below "
            "the break-even traffic; batch (C) is offline; serverless (D) has cold starts. (Week 11.)"
        ),
    ),
    Question(
        domain="new-solutions",
        prompt=(
            "You need at-least-once event delivery with retries, a dead-letter path for poison "
            "messages, and the ability to replay past events for reprocessing. Which combination?"
        ),
        options=(
            "SNS fan-out only.",
            "EventBridge (with archive/replay) routing to SQS queues that have DLQs.",
            "A single Lambda polling DynamoDB.",
            "Kinesis Data Streams with no consumer checkpointing.",
        ),
        answer=1,
        rationale=(
            "EventBridge gives routing plus archive-and-replay; SQS gives retry with a DLQ for "
            "poison messages. Together they meet all three requirements. (Week 10.)"
        ),
    ),
    Question(
        domain="continuous-improve",
        prompt=(
            "You run a 99.9% availability SLO. You want to be paged when the error budget is "
            "being consumed fast enough to exhaust it soon, but NOT for every brief blip. What do you build?"
        ),
        options=(
            "A static alarm at 1 error per minute.",
            "A multi-window burn-rate alarm (e.g. fast 1h window + slow 6h window).",
            "A daily email of the error count.",
            "A CloudTrail trail on the API.",
        ),
        answer=1,
        rationale=(
            "Multi-window burn-rate alarms page only when the budget is burning fast across both "
            "a short and a long window, suppressing noise while catching real budget exhaustion. (Week 12.)"
        ),
    ),
    Question(
        domain="continuous-improve",
        prompt=(
            "Your steady-state compute baseline is predictable and will run regardless. You want "
            "the largest cost reduction with the least operational change. What do you commit?"
        ),
        options=(
            "Spot instances for the always-on baseline.",
            "A Compute Savings Plan sized to the steady-state baseline, plus moving the baseline to Graviton.",
            "Reserved Instances for a specific instance type you may outgrow.",
            "Nothing - on-demand is fine.",
        ),
        answer=1,
        rationale=(
            "A Compute Savings Plan discounts the committed baseline across instance families/Regions "
            "(more flexible than RIs), and Graviton adds ~20% price/performance at near-zero code change. "
            "Spot (A) is wrong for an always-on baseline you cannot have reclaimed. (Week 14.)"
        ),
    ),
    Question(
        domain="migration",
        prompt=(
            "You are moving a lake from millions of small JSON files queried by Athena to a layout "
            "that minimizes bytes scanned. Which change reduces scan cost the MOST?"
        ),
        options=(
            "Enable S3 Transfer Acceleration.",
            "Partition by date and convert to Parquet, then query with a partition filter.",
            "Move the bucket to a colder storage class.",
            "Increase the Athena query timeout.",
        ),
        answer=1,
        rationale=(
            "Athena bills per byte scanned. Partitioning prunes prefixes; Parquet prunes columns and "
            "row groups. Storage class (C) and timeout (D) do not reduce bytes scanned. (Week 11.)"
        ),
    ),
    Question(
        domain="migration",
        prompt=(
            "You must move a self-managed PostgreSQL database to AWS with multi-AZ failover, read "
            "replicas, and the option to scale storage automatically, while keeping Postgres compatibility. "
            "What is the idiomatic target?"
        ),
        options=(
            "DynamoDB single-table.",
            "Aurora PostgreSQL (multi-AZ writer + read replicas), optionally Serverless v2.",
            "Redshift.",
            "A single large EC2 instance running Postgres.",
        ),
        answer=1,
        rationale=(
            "Aurora PostgreSQL keeps Postgres compatibility while giving a distributed storage layer, "
            "fast failover, read replicas, and auto-scaling storage. DynamoDB (A) is not relational; "
            "Redshift (C) is a warehouse, not an OLTP target. (Week 8.)"
        ),
    ),
    Question(
        domain="sdlc-automation",
        prompt=(
            "Your GitHub Actions pipeline deploys to AWS. You want NO long-lived AWS keys in CI and "
            "the ability to lock the trust to one repo and branch. What do you configure?"
        ),
        options=(
            "An IAM user with an access key stored as a GitHub secret.",
            "GitHub OIDC federation: an IAM role with a trust policy on token.actions.githubusercontent.com "
            "conditioned on the repo/branch sub claim.",
            "Root account credentials in the workflow.",
            "A shared key rotated monthly by a cron job.",
        ),
        answer=1,
        rationale=(
            "OIDC federation issues short-lived credentials per run and lets the trust policy's sub "
            "condition restrict which repo and branch may assume the role. No static keys exist to leak. (Week 7.)"
        ),
    ),
    Question(
        domain="sdlc-automation",
        prompt=(
            "You want an ECS Fargate deploy to shift 10% of traffic to the new version, watch a "
            "CloudWatch alarm, and roll back automatically if it fires. Which deployment style?"
        ),
        options=(
            "In-place all-at-once.",
            "CodeDeploy blue/green with a canary traffic shift and an alarm-based automatic rollback.",
            "Manual SSH and restart.",
            "Delete the service and recreate it.",
        ),
        answer=1,
        rationale=(
            "Blue/green with a canary shifts a small slice first; tying rollback to a CloudWatch alarm "
            "bounds the blast radius of a bad deploy to the canary. (Week 7.)"
        ),
    ),
    Question(
        domain="iac",
        prompt=(
            "A teammate changed a security group in the console and now the deployed stack no longer "
            "matches the CDK code. How do you detect this systematically?"
        ),
        options=(
            "Re-read every resource by hand each morning.",
            "Run CloudFormation drift detection on the stack and review the drifted resources.",
            "Delete the stack and redeploy.",
            "Turn off console access entirely and hope.",
        ),
        answer=1,
        rationale=(
            "CloudFormation drift detection compares the live resources to the template and reports "
            "what diverged - the systematic way to catch out-of-band changes. (Week 3.)"
        ),
    ),
    Question(
        domain="iac",
        prompt=(
            "You define a chaos experiment as code so it lives in the capstone monorepo and deploys "
            "with the rest of the infrastructure. Which CDK construct expresses a FIS experiment template?"
        ),
        options=(
            "aws-cdk-lib/aws-lambda Function.",
            "aws-cdk-lib/aws-fis CfnExperimentTemplate.",
            "aws-cdk-lib/aws-s3 Bucket.",
            "There is no IaC for FIS; it is console-only.",
        ),
        answer=1,
        rationale=(
            "CfnExperimentTemplate in aws-fis declares the actions, targets, stop conditions, and role "
            "as code, so the experiment is reproducible and version-controlled. (Weeks 3, 15.)"
        ),
    ),
    Question(
        domain="reliability",
        prompt=(
            "You want to PROVE your capstone meets a 5-minute RTO for an AZ outage, not just claim it. "
            "What is the AWS-native way to inject the fault safely?"
        ),
        options=(
            "Manually terminate random instances in production and watch.",
            "An AWS Fault Injection Service experiment (e.g. the AZ Availability Power scenario) with a "
            "CloudWatch-alarm stop condition, run against a non-prod copy, measuring recovery time.",
            "Lower the health-check interval and hope it fails over.",
            "Read the Aurora docs and assume the documented failover time.",
        ),
        answer=1,
        rationale=(
            "FIS injects a real, bounded fault with a stop-condition seatbelt and an auto-revert, so you "
            "MEASURE the recovery rather than guess it. A measured RTO beats a documented one in any review. (Week 15.)"
        ),
    ),
    Question(
        domain="reliability",
        prompt=(
            "Your RPO target is 1 minute across Regions. What most directly determines your actual RPO "
            "for the analytical (Aurora) store?"
        ),
        options=(
            "The CloudFront cache TTL.",
            "The Aurora cross-region read-replica replication lag.",
            "The DynamoDB on-demand burst limit.",
            "The Lambda reserved concurrency.",
        ),
        answer=1,
        rationale=(
            "RPO is the data-loss window; for a cross-region replica it is bounded by the replication lag "
            "at the moment of failure. You must measure that lag to defend the RPO number. (Week 13.)"
        ),
    ),
    Question(
        domain="monitoring",
        prompt=(
            "You want vendor-neutral instrumentation that emits the same traces and metrics whether the "
            "code runs on EKS or Lambda, with X-Ray and CloudWatch as backends. What do you adopt?"
        ),
        options=(
            "Proprietary CloudWatch agent only, with no traces.",
            "OpenTelemetry via the ADOT collector (DaemonSet on EKS, extension on Lambda), exporting to X-Ray and CloudWatch.",
            "Print statements parsed by a regex in Logs Insights.",
            "A third-party APM agent on every host with no standard.",
        ),
        answer=1,
        rationale=(
            "OpenTelemetry is the vendor-neutral standard; ADOT is AWS's distribution of the collector. "
            "It runs as a DaemonSet on EKS and a Lambda extension, exporting to AWS backends. (Week 12.)"
        ),
    ),
    Question(
        domain="monitoring",
        prompt=(
            "During the Lambda concurrency-exhaustion drill, which signal best confirms the throttle became "
            "BACK-PRESSURE rather than data loss?"
        ),
        options=(
            "The Lambda Invocations metric stayed flat.",
            "The Lambda Throttles metric rose AND the async DLQ / on-failure destination caught the excess, "
            "which then drained after the load dropped.",
            "The billing dashboard updated.",
            "CPU utilization on the function host increased.",
        ),
        answer=1,
        rationale=(
            "Throttles rising shows the ceiling was hit; the DLQ/destination catching and later draining the "
            "excess shows the events were held and reprocessed, not lost. (Weeks 12, 15.)"
        ),
    ),
    Question(
        domain="incident-response",
        prompt=(
            "In a blameless postmortem, an operator ran a command that deleted production data. What is the "
            "correct ROOT cause?"
        ),
        options=(
            "The operator's mistake - assign them remediation training.",
            "The system allowed a destructive command to reach production with no guardrail, confirmation, or "
            "least-privilege boundary - that missing guardrail is the systemic root.",
            "Bad luck.",
            "The time of day the command was run.",
        ),
        answer=1,
        rationale=(
            "Blameless postmortems never stop at 'human error'. If a human could destroy prod, the system that "
            "permitted it without a guardrail is the fixable root cause, and the action item is the guardrail. (Week 15.)"
        ),
    ),
    Question(
        domain="incident-response",
        prompt=(
            "Which property must EVERY action item in a postmortem have to be a commitment rather than a wish?"
        ),
        options=(
            "A severity color.",
            "A named owner, a due date, and a tag (accept / mitigate-now / mitigate-later).",
            "A link to the slide deck.",
            "Approval from three managers.",
        ),
        answer=1,
        rationale=(
            "An owner, a date, and a disposition tag turn an observation into an accountable commitment. "
            "Unowned, undated action items never get done. (Week 15.)"
        ),
    ),
    Question(
        domain="security",
        prompt=(
            "A Lambda calls exactly one SageMaker endpoint and one Bedrock model. Which IAM policy passes a "
            "least-privilege review?"
        ),
        options=(
            "Action sagemaker:* and bedrock:* on Resource *.",
            "sagemaker:InvokeEndpoint on the one endpoint ARN, and bedrock:InvokeModel on the one foundation-model "
            "ARN plus its inference-profile ARN.",
            "Action * on Resource *.",
            "AdministratorAccess attached to the function role.",
        ),
        answer=1,
        rationale=(
            "Least privilege grants the specific actions on the specific resource ARNs. Converse against an "
            "inference profile needs invoke on BOTH the model and the profile ARN - a common gotcha. The "
            "wildcard options fail any IAM review. (Weeks 2, 11.)"
        ),
    ),
    Question(
        domain="security",
        prompt=(
            "You want org-wide threat detection from VPC Flow Logs, DNS logs, and CloudTrail, with findings "
            "aggregated centrally, plus PII scanning on the data-lake bucket. Which services?"
        ),
        options=(
            "Only CloudTrail.",
            "GuardDuty (threat detection) + Security Hub (aggregation) + Macie (S3 PII scanning).",
            "Only a bucket policy.",
            "WAF alone.",
        ),
        answer=1,
        rationale=(
            "GuardDuty consumes Flow Logs/DNS/CloudTrail for threat detection, Security Hub aggregates posture "
            "and findings, and Macie scans S3 for PII. (Week 13.)"
        ),
    ),
]


# --------------------------------------------------------------------------- #
# Scoring + reporting
# --------------------------------------------------------------------------- #
def select(bank: list[Question], domain: str | None, exam: str | None) -> list[Question]:
    qs = bank
    if domain:
        qs = [q for q in qs if q.domain == domain]
    if exam:
        qs = [q for q in qs if DOMAIN_META.get(q.domain, ("", ""))[0] == exam]
    if not qs:
        raise SystemExit(f"No questions for domain={domain!r} exam={exam!r}.")
    return qs


def ask(q: Question) -> bool:
    print("\n" + textwrap.fill(q.prompt, width=88))
    letters = "ABCD"
    for i, opt in enumerate(q.options):
        print(f"  {letters[i]}) " + textwrap.fill(opt, width=84, subsequent_indent="     "))
    while True:
        raw = input("Your answer [A-D] (or 'q' to quit): ").strip().upper()
        if raw == "Q":
            raise KeyboardInterrupt
        if raw in letters[: len(q.options)]:
            chosen = letters.index(raw)
            correct = chosen == q.answer
            print("  Correct." if correct else f"  Incorrect. Answer: {letters[q.answer]}.")
            print("  " + textwrap.fill(q.rationale, width=84, subsequent_indent="  "))
            return correct
        print("  Please enter A, B, C, or D.")


def report(results: dict[str, list[bool]]) -> None:
    total = sum(len(v) for v in results.values())
    correct = sum(sum(v) for v in results.values())
    pct = correct / total if total else 0.0
    print("\n" + "=" * 60)
    print(f"SCORE: {correct}/{total} = {pct:.0%}")
    print("=" * 60)
    print("Per-domain breakdown:")
    ranked = []
    for domain, res in sorted(results.items()):
        dpct = sum(res) / len(res) if res else 0.0
        exam = DOMAIN_META.get(domain, ("?", ""))[0].upper()
        print(f"  [{exam:>3}] {domain:<20} {sum(res)}/{len(res)}  ({dpct:.0%})")
        ranked.append((dpct, domain))
    print()
    if pct >= PASS_THRESHOLD:
        print("READINESS GATE: PASS  (>=70%). Sit the real exam soon while it's fresh.")
    else:
        print(f"READINESS GATE: {'PARTIAL' if pct >= 0.5 else 'FAIL'}  (need >=70%).")
    # Study plan: the two weakest domains.
    ranked.sort()
    weak = [d for _, d in ranked[:2]]
    print("\nStudy plan - your two weakest domains:")
    for d in weak:
        weeks = DOMAIN_META.get(d, ("", "no mapping"))[1]
        print(f"  * {d}: re-study {weeks}")


def self_test() -> int:
    problems = 0
    for i, q in enumerate(BANK):
        if not (0 <= q.answer < len(q.options)):
            print(f"Q{i}: answer index out of range"); problems += 1
        if len(q.options) != 4:
            print(f"Q{i}: expected 4 options, got {len(q.options)}"); problems += 1
        if q.domain not in DOMAIN_META:
            print(f"Q{i}: unknown domain {q.domain!r}"); problems += 1
        if not q.rationale.strip():
            print(f"Q{i}: empty rationale"); problems += 1
    domains = {q.domain for q in BANK}
    print(f"Bank: {len(BANK)} questions across {len(domains)} domains.")
    print("self-test: OK" if problems == 0 else f"self-test: {problems} problem(s)")
    return 1 if problems else 0


def review() -> None:
    letters = "ABCD"
    for q in BANK:
        print(f"\n[{q.domain}] " + textwrap.fill(q.prompt, width=86))
        print(f"  Answer: {letters[q.answer]}) {q.options[q.answer]}")
        print("  " + textwrap.fill(q.rationale, width=84, subsequent_indent="  "))


def main() -> None:
    parser = argparse.ArgumentParser(description="SAP-C02 / DOP-C02 readiness gate.")
    parser.add_argument("--domain", help="restrict to one domain")
    parser.add_argument("--exam", choices=["sap", "dop"], help="restrict to one exam's domains")
    parser.add_argument("--review", action="store_true", help="print answers + rationale, no quiz")
    parser.add_argument("--self-test", action="store_true", help="verify the bank is consistent")
    parser.add_argument("--seed", type=int, default=None, help="shuffle seed for reproducibility")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())
    if args.review:
        review()
        return

    qs = select(BANK, args.domain, args.exam)
    rng = random.Random(args.seed)
    rng.shuffle(qs)

    results: dict[str, list[bool]] = {}
    try:
        for q in qs:
            results.setdefault(q.domain, []).append(ask(q))
    except KeyboardInterrupt:
        print("\n(quit early - scoring what you answered)")
    if any(results.values()) or results:
        report(results)


if __name__ == "__main__":
    main()
