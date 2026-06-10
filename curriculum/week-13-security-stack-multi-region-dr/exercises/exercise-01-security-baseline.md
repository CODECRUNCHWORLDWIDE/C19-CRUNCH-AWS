# Exercise 1 — The Security Baseline: GuardDuty, Security Hub, Macie, Inspector

> **Estimated time:** ~90 minutes. **Cost:** GuardDuty/Security Hub are in their free trial window or cost little; **Macie and Inspector bill by what they inspect** — scope them small (a sample prefix, a few images), not the whole lake/registry.

## Goal

Turn on the four detective controls, generate at least one real finding, aggregate everything into Security Hub, and triage every **Critical** and **High** finding to a documented disposition (fixed or accepted-with-reason). The headline outcome: a `finding-disposition.md` table where no Critical or High is left unread — the artifact that, in a real org, is the difference between "we knew" and a breach postmortem.

This is the "lights on" baseline. The detective stack does not *break* anything; it makes the account honest about what is already wrong.

## Prerequisites

- AWS CLI v2 configured (`aws sts get-caller-identity` returns your account).
- Permissions for GuardDuty, Security Hub, Macie, Inspector, S3, and ECR.
- `jq` installed (for reading CLI JSON output).
- Region `us-east-1` assumed; substitute consistently if you use another.
- If you have an Organization (Weeks 1–2), do this in a **delegated-administrator** account, not the management account. If you are single-account for the lab, that is fine — enable directly.

## Acceptance criteria

- [ ] GuardDuty is enabled with a detector and at least the S3 and Kubernetes data sources on.
- [ ] Security Hub is enabled with the AWS Foundational Security Best Practices standard turned on.
- [ ] At least one GuardDuty finding exists (you generate one with the sample-findings generator).
- [ ] A Macie sensitive-data discovery job has run over a **small sample prefix** and reported on the seeded PII.
- [ ] Inspector is enabled for ECR and has scanned at least one pushed image.
- [ ] A committed `finding-disposition.md` lists every Critical and High finding with a "fixed" or "accepted because X" disposition.

---

## Step 1 — Enable GuardDuty and generate sample findings

GuardDuty needs a *detector* (one per account per Region). Create it, then use the built-in sample-findings generator so you have something to triage without waiting for a real attacker.

```bash
export REGION=us-east-1

# Create the detector with S3 and Kubernetes audit-log data sources on.
DETECTOR_ID=$(aws guardduty create-detector \
  --enable \
  --finding-publishing-frequency FIFTEEN_MINUTES \
  --data-sources '{"S3Logs":{"Enable":true},"Kubernetes":{"AuditLogs":{"Enable":true}}}' \
  --region "$REGION" \
  --query DetectorId --output text)
echo "detector: $DETECTOR_ID"

# Generate sample findings so you can triage immediately (these are clearly labelled [SAMPLE]).
aws guardduty create-sample-findings --detector-id "$DETECTOR_ID" --region "$REGION"

# List what landed (wait ~30s for them to appear).
sleep 30
aws guardduty list-findings --detector-id "$DETECTOR_ID" --region "$REGION" \
  --query 'FindingIds' --output text | tr '\t' '\n' | head
```

Read one finding in full. The `Type`, `Severity`, and `Service.Action` fields are what you triage on:

```bash
FID=$(aws guardduty list-findings --detector-id "$DETECTOR_ID" --region "$REGION" \
  --query 'FindingIds[0]' --output text)

aws guardduty get-findings --detector-id "$DETECTOR_ID" --finding-ids "$FID" --region "$REGION" \
  --query 'Findings[0].{Type:Type, Severity:Severity, Title:Title, Resource:Resource.ResourceType}'
```

You will see types like `UnauthorizedAccess:EC2/SSHBruteForce` or `CryptoCurrency:EC2/BitcoinTool.B!DNS`, each with a numeric severity (a value 7.0–8.9 is High, 4.0–6.9 Medium, 1.0–3.9 Low). Note that GuardDuty needed **no agent** for these — it reads CloudTrail, Flow Logs, and DNS that AWS already has.

## Step 2 — Enable Security Hub and the FSBP standard

Security Hub is the aggregator. Enabling it turns on default standards; explicitly enable the Foundational Security Best Practices standard so it scores your account.

```bash
# Enable the hub (subscribes to GuardDuty/Inspector/Macie findings automatically).
aws securityhub enable-security-hub \
  --enable-default-standards \
  --control-finding-generator SECURITY_CONTROL \
  --region "$REGION"

# Confirm FSBP is enabled (its ARN is account/region-specific; list to see status).
aws securityhub get-enabled-standards --region "$REGION" \
  --query 'StandardsSubscriptions[].{Standard:StandardsArn, Status:StandardsStatus}'
```

Give Security Hub a few minutes to run its controls. Then list the failing controls by severity — this is your posture:

```bash
aws securityhub get-findings --region "$REGION" \
  --filters '{"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}],"SeverityLabel":[{"Value":"CRITICAL","Comparison":"EQUALS"},{"Value":"HIGH","Comparison":"EQUALS"}]}' \
  --query 'Findings[].{Title:Title, Severity:Severity.Label, Resource:Resources[0].Id}' \
  --max-items 50
```

Every row here needs a disposition in Step 5. Common Criticals on a fresh account: root account has no MFA, S3 Block Public Access is off somewhere, CloudTrail is not encrypted, a security group allows `0.0.0.0/0` on port 22.

## Step 3 — Run Macie on a small sample prefix

Macie scans S3 for PII. **Scope it small** — seed a tiny sample file, point a discovery job at just that prefix, and do not let it loose on the whole lake.

```bash
export ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export SAMPLE_BUCKET="c19-wk13-macie-sample-${ACCOUNT}"
aws s3 mb "s3://${SAMPLE_BUCKET}" --region "$REGION"
aws s3api put-public-access-block --bucket "${SAMPLE_BUCKET}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Seed a file with obvious (fake) PII so Macie has something to find.
cat > sample-pii.csv <<'CSV'
name,email,ssn,card
Ada Lovelace,ada@example.com,123-45-6789,4111111111111111
Alan Turing,alan@example.com,987-65-4321,5500005555555559
CSV
aws s3 cp sample-pii.csv "s3://${SAMPLE_BUCKET}/sample/sample-pii.csv"

# Enable Macie, then create a ONE-TIME discovery job scoped to this one bucket.
aws macie2 enable-macie --region "$REGION" 2>/dev/null || echo "macie already enabled"

aws macie2 create-classification-job --region "$REGION" \
  --job-type ONE_TIME \
  --name "c19-wk13-sample-scan" \
  --s3-job-definition "{\"bucketDefinitions\":[{\"accountId\":\"${ACCOUNT}\",\"buckets\":[\"${SAMPLE_BUCKET}\"]}]}"
```

Wait for the job to finish (a one-time job over one tiny file takes a few minutes), then read what it found:

```bash
aws macie2 list-findings --region "$REGION" --query 'findingIds' --output text | tr '\t' '\n' | head
# Then get-findings on an id to see the sensitive-data categories (CREDIT_CARD_NUMBER, US_SSN, etc.)
```

Macie will report the credit-card numbers and SSNs in the seeded file. The lesson: this is how you discover PII that landed in a bucket it should never have — and why you scope the job, because over a real lake this bills per GB.

## Step 4 — Enable Inspector and scan an ECR image

Inspector scans ECR images for CVEs. Enable it for ECR, push an image, and read the findings.

```bash
# Enable Inspector for ECR (and EC2/Lambda if you want; ECR is the container story).
aws inspector2 enable --resource-types ECR --region "$REGION"

# Push an intentionally-old image so there ARE CVEs to find.
aws ecr create-repository --repository-name c19-wk13-scan --region "$REGION" 2>/dev/null || true
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# An old base image will have known CVEs (the point of the exercise).
docker pull debian:11-slim
docker tag debian:11-slim "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/c19-wk13-scan:old"
docker push "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/c19-wk13-scan:old"

# Inspector scans on push; wait a few minutes, then list Critical/High findings.
sleep 120
aws inspector2 list-findings --region "$REGION" \
  --filter-criteria '{"severity":[{"comparison":"EQUALS","value":"CRITICAL"},{"comparison":"EQUALS","value":"HIGH"}]}' \
  --query 'findings[].{Title:title, Severity:severity, Package:packageVulnerabilityDetails.vulnerablePackages[0].name, Fix:packageVulnerabilityDetails.vulnerablePackages[0].fixedInVersion}' \
  --max-results 20
```

Each finding names a vulnerable package and the version that fixes it. The remediation is "rebuild on a patched base image" — in the capstone you would bump the base and re-push. The senior note from the lecture: Inspector tells you what is *vulnerable*, not what is *exploitable in your context*; triage with judgment, but document the call.

## Step 5 — Triage to a disposition table

This is the actual deliverable. For every Critical and High finding across GuardDuty, Security Hub, Macie, and Inspector, write a row in `finding-disposition.md`:

```markdown
# Finding disposition — Week 13 security baseline

| Source | Finding | Severity | Disposition | Action / reason |
|--------|---------|----------|-------------|-----------------|
| SecurityHub | Root account has no MFA | CRITICAL | FIXED | Enabled MFA on root; sealed in runbook |
| SecurityHub | S3 BPA off on bucket X | HIGH | FIXED | Turned on Block Public Access |
| GuardDuty | [SAMPLE] SSHBruteForce | HIGH | ACCEPTED | Sample finding; no real source |
| Macie | CREDIT_CARD_NUMBER in sample-pii.csv | HIGH | FIXED | Deleted sample bucket after exercise |
| Inspector | Critical OpenSSL CVE in debian:11-slim | CRITICAL | ACCEPTED | Lab image only; would rebuild on patched base in capstone |
```

Every Critical and High gets a row. "I didn't see it" is the disposition that ends up in a breach report.

## Cleanup (end-of-session)

The detective controls are cheap to leave on, but Macie/Inspector bill on inspection and the sample bucket holds fake PII — clean up:

```bash
# Delete the Macie sample bucket (it contains seeded PII).
aws s3 rb "s3://${SAMPLE_BUCKET}" --force

# Optionally stop Inspector ECR scanning if you don't want continuous scans billing.
aws inspector2 disable --resource-types ECR --region "$REGION"

# Leave GuardDuty and Security Hub ON for the rest of the week — the DR drill wants the
# second Region watched too, and they're cheap. Disable after Week 13 if you wish:
#   aws guardduty delete-detector --detector-id "$DETECTOR_ID" --region "$REGION"
#   aws securityhub disable-security-hub --region "$REGION"
```

## Inline hints

- *GuardDuty `create-detector` says one already exists* — you (or the account) already have a detector in this Region. Get its id with `aws guardduty list-detectors --query 'DetectorIds[0]' --output text` and use that.
- *Security Hub findings list is empty* — the controls take several minutes to run after enabling. Wait 10 minutes and re-query; the FSBP standard has to evaluate every control.
- *Macie job stuck in `RUNNING`* — even a one-file job takes a few minutes; a job over a large bucket can run for hours (and bill for it). If it is slow, confirm you scoped it to the one small bucket, not the whole account.
- *Inspector returns no findings* — scanning on push can lag a few minutes, and a very minimal image may genuinely have none. Use an intentionally old base (`debian:11-slim`, an old `node`/`python` tag) so there *are* CVEs.
- *`AccessDeniedException` enabling org-wide* — you are in a member account. Either run in the delegated-administrator account or, for the lab, enable single-account directly.
