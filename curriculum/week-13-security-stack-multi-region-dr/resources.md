# Week 13 — Resources

Everything here is free to read. AWS documentation is open. The re:Invent talks are on YouTube. The open-source projects are public on GitHub. We link a few paid books at the chapter level only where the free docs genuinely fall short.

Two scheduling notes that will save you a day. First: **enable GuardDuty, Security Hub, and Inspector on Monday or Tuesday morning.** They take a little while to ingest enough telemetry to produce findings — GuardDuty needs CloudTrail and VPC Flow Log history to chew on, and Inspector's first ECR scan can lag. Turn them on early so by Friday they have something to show. Second: **do not enable Shield Advanced.** It is a $3,000/month, 1-year-minimum commitment per organization. This week you reason about it; you do not buy it. The lab stops at Shield Standard (free) and a WAF rate-limit rule.

## Required reading (work it into your week)

- **AWS KMS — concepts** (AWS-managed vs customer-managed keys, key policies, grants, the data-key/envelope-encryption model):
  <https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html>
- **AWS KMS — multi-Region keys** (the primary/replica model that makes encrypted CRR work):
  <https://docs.aws.amazon.com/kms/latest/developerguide/multi-region-keys-overview.html>
- **Secrets Manager vs Parameter Store** — the decision, from AWS Prescriptive Guidance:
  <https://docs.aws.amazon.com/prescriptive-guidance/latest/secure-sensitive-data-secrets-manager-terraform/secrets-manager-vs-parameter-store.html>
- **GuardDuty — how it uses data sources** (Flow Logs, DNS, CloudTrail) and the protection plans:
  <https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_data-sources.html>
- **Security Hub — standards and controls** (FSBP, CIS, the ASFF finding format):
  <https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-standards.html>
- **AWS WAF — managed rule groups** (the AWS-managed baseline you start from):
  <https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-list.html>
- **Disaster recovery options in the cloud** — *the* canonical four-postures paper (backup/restore, pilot light, warm standby, multi-site active/active), with RTO/RPO framing:
  <https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html>

## Pricing pages (read these as dollars, not docs)

You cannot do this week's DR-posture decision frame without the numbers. Open these and write the figures into your cost report:

- **GuardDuty pricing** — per-GB of analyzed CloudTrail/VPC/DNS events, plus per-plan (EKS Runtime, S3, RDS, Lambda, Malware Protection):
  <https://aws.amazon.com/guardduty/pricing/>
- **Macie pricing** — per-bucket evaluation plus per-GB inspected by a sensitive-data discovery job (the line that bites on a real lake):
  <https://aws.amazon.com/macie/pricing/>
- **Inspector pricing** — per-instance/-image/-function scanned per month:
  <https://aws.amazon.com/inspector/pricing/>
- **Shield Advanced pricing** — $3,000/month, 1-year commitment, per organization, plus data-transfer-out fees (the number you reason about, do not buy):
  <https://aws.amazon.com/shield/pricing/>
- **KMS pricing** — per-CMK-month and per-10,000 API requests; multi-Region replicas bill per key:
  <https://aws.amazon.com/kms/pricing/>
- **Aurora Global Database pricing** — the cross-Region replicated-write I/O and the standby Region's instance cost (the warm-standby line item):
  <https://aws.amazon.com/rds/aurora/pricing/>
- **DynamoDB Global Tables pricing** — replicated write request units (rWCU) across Regions:
  <https://aws.amazon.com/dynamodb/pricing/on-demand/>
- **Route 53 pricing** — hosted-zone-month plus per-health-check (basic vs with extra features):
  <https://aws.amazon.com/route53/pricing/>

## AWS docs you will reach for during the build

- **KMS — key policies** (the administrator-vs-user split that everyone misreads):
  <https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html>
- **KMS — grants** (the programmatic, temporary alternative to a key-policy edit):
  <https://docs.aws.amazon.com/kms/latest/developerguide/grants.html>
- **Secrets Manager — rotation** (the Lambda-backed rotation contract and the four-step rotation function):
  <https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html>
- **GuardDuty — delegated administrator** (org-wide enablement without using the management account):
  <https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_organizations.html>
- **Macie — running a sensitive-data discovery job**:
  <https://docs.aws.amazon.com/macie/latest/user/discovery-jobs.html>
- **Inspector — Amazon ECR image scanning** (the EKS/container vulnerability angle):
  <https://docs.aws.amazon.com/inspector/latest/user/scanning-ecr.html>
- **DynamoDB — Global Tables** (multi-active, last-writer-wins, the version-2019.11.21 model):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html>
- **Aurora — Global Database** (the storage-level replication, managed planned/unplanned failover):
  <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html>
- **S3 — Cross-Region Replication** and **replicating encrypted objects (SSE-KMS)**:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html>
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-config-for-kms-objects.html>
- **Route 53 — health checks and DNS failover**:
  <https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover.html>
- **ACM Private CA — overview** (internal TLS/mTLS):
  <https://docs.aws.amazon.com/privateca/latest/userguide/PcaWelcome.html>

## CDK / IaC reference

- **AWS CDK — `aws-kms`** (the `Key` L2, `MultiRegionKey`, alias, rotation):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_kms-readme.html>
- **AWS CDK — `aws-secretsmanager`** (the `Secret` L2, `HostedRotation`, `addRotationSchedule`):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_secretsmanager-readme.html>
- **AWS CDK — `aws-guardduty`** (`CfnDetector`, organization config — L1 only in 2026):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_guardduty-readme.html>
- **AWS CDK — `aws-wafv2`** (`CfnWebACL` with managed rule-group statements and a rate-based rule):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_wafv2-readme.html>
- **AWS CDK — `aws-route53`** (`CfnHealthCheck`, `CfnRecordSet` with failover routing policy):
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53-readme.html>
- **OpenTofu / Terraform AWS provider** — `aws_kms_replica_key`, `aws_guardduty_detector`, `aws_dynamodb_table` (with `replica` blocks), `aws_rds_global_cluster`, `aws_route53_health_check`:
  <https://search.opentofu.org/provider/hashicorp/aws/latest>

## re:Invent and AWS talks (free, on YouTube)

- **"Building a multi-Region disaster recovery strategy on AWS"** — the four-postures talk with live failover demos. Search the AWS Events channel for the most recent year's ARC-track DR session:
  <https://www.youtube.com/@AWSEventsChannel>
- **"A deep dive into AWS KMS"** — envelope encryption, multi-Region keys, key policies (annual SEC-track deep dive; pick the latest):
  <https://www.youtube.com/@AWSEventsChannel>
- **"Threat detection and incident response with Amazon GuardDuty and Security Hub"** — the detection-and-posture pairing from the horse's mouth:
  <https://www.youtube.com/@AWSEventsChannel>
- **"Scaling threat detection and response on AWS"** — GuardDuty + Detective + Security Hub at org scale:
  <https://www.youtube.com/@AWSEventsChannel>

*(re:Invent session IDs change yearly; the channel is stable. Filter by the most recent year and the SEC / ARC tracks.)*

## Open-source comparators (know what you traded away)

- **Falco** — runtime threat detection for Kubernetes/Linux from syscalls; the self-hosted alternative to GuardDuty EKS Runtime Monitoring. You run the sensor and the rules; AWS does not. Free, but it is yours to operate:
  <https://falco.org/docs/>
- **Wazuh** — host-based intrusion detection and SIEM; the open alternative to the GuardDuty + Security Hub aggregation story:
  <https://documentation.wazuh.com/current/index.html>
- **Trivy** and **Grype** — image and filesystem vulnerability scanners; the open alternative to Inspector's ECR scanning. Run them in CI and you scan *before* the image is pushed, not after:
  <https://trivy.dev/latest/docs/> · <https://github.com/anchore/grype>
- **HashiCorp Vault** — secrets management, dynamic secrets, and PKI; the open alternative to Secrets Manager + ACM Private CA. More capable, entirely yours to run and patch:
  <https://developer.hashicorp.com/vault/docs>
- **OPA / Conftest** — policy-as-code; the open alternative to Security Hub controls when you want to *prevent* misconfiguration in CI rather than *detect* it after deploy:
  <https://www.openpolicyagent.org/docs/latest/> · <https://www.conftest.dev/>

## Books (chapter-level)

- **AWS Security (Dylan Shields)** — the chapters on KMS, IAM-vs-resource-policies, and detective controls are the best single-source explanation of the KMS key-policy-vs-IAM evaluation that trips everyone up. Borrow it; read the KMS and detective-controls chapters.
- **AWS Well-Architected — Reliability Pillar** (free) — the DR section formalizes RTO/RPO and the four postures with the exact language a reviewer expects:
  <https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html>
- **AWS Well-Architected — Security Pillar** (free) — the detective-controls and data-protection sections map one-to-one to this week's stack:
  <https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html>

## The RTO/RPO and posture reference

This week you commit to **RTO** (Recovery Time Objective — how long until service is back) and **RPO** (Recovery Point Objective — how much data you can afford to lose) numbers, then prove them. The four postures map to rough ranges that you should know cold, and which the lecture derives:

| Posture | Typical RTO | Typical RPO | Relative cost |
|---|---|---|---|
| **Backup & restore** | hours | hours | lowest |
| **Pilot light** | tens of minutes | minutes | low |
| **Warm standby** | minutes | seconds | high |
| **Active/active (multi-site)** | near-zero | near-zero | highest |

The exact numbers depend on *your* data size and automation; the ranges above are the framing. Confirm the current managed-failover RTO claims for Aurora Global Database and the replication-lag characteristics of DynamoDB Global Tables from the live docs before you write your cost report — AWS improves these, and your *achieved* numbers from the Friday drill are what actually count.

## Tools you'll use this week

- **AWS CLI v2** — `aws guardduty list-findings`, `aws securityhub get-findings`, `aws macie2 create-classification-job`, `aws inspector2 list-findings`, `aws kms replicate-key`, `aws route53 get-health-check-status`. Verify with `aws --version` (want `aws-cli/2.x`).
- **Python 3.12+** with `boto3`. A `requirements.txt` ships with each exercise. (Exercises 2 and 3 are boto3-driven.)
- **AWS CDK v2** (TypeScript) — `npx cdk deploy`. The mini-project's infra is CDK, with one stack mirrored in Python per the course's TS-primary/Py-secondary convention.
- **`curl`** — for proving the WAF rate-limit rule and the Route 53 failover flip.
- **`jq`** — for slicing the JSON the GuardDuty/Security Hub/Inspector CLIs return.
- **`dig`** — for watching the Route 53 record flip from primary to secondary during the failover drill.

## Glossary cheat sheet

Keep this open in a tab.

| Term | Plain English |
|------|---------------|
| **CMK (customer-managed key)** | A KMS key *you* create and control the policy on. The alternative is an AWS-managed key (`aws/<service>`) with a policy you can't edit. |
| **Key policy** | The resource policy on a KMS key. It is the *primary* access control — IAM alone cannot grant KMS access unless the key policy delegates to IAM. |
| **Grant** | A programmatic, often temporary KMS permission a service creates on your behalf (e.g. EBS attaching a volume). The alternative to editing the key policy. |
| **Envelope encryption** | Encrypt data with a data key; encrypt the data key with the CMK; store the encrypted data key next to the data. How S3/EBS/RDS all do KMS. |
| **Multi-Region key** | A KMS key with a primary in one Region and replicas in others that share key material, so ciphertext encrypted in Region A decrypts in Region B. |
| **GuardDuty** | Managed threat detection. Reads CloudTrail, VPC Flow Logs, and DNS logs (plus optional plans) and emits findings. No agent for the core sources. |
| **Security Hub** | Posture aggregation. Runs FSBP/CIS controls and ingests GuardDuty/Inspector/Macie findings into one ASFF-formatted view. |
| **Macie** | Managed PII/sensitive-data discovery for S3. Bills per GB inspected; scope it or it gets expensive on a real lake. |
| **Inspector** | Continuous vulnerability (CVE) scanning of ECR images, EC2, and Lambda. The container/EKS vuln story runs through ECR image scans. |
| **WAF web ACL** | The Layer-7 firewall in front of CloudFront/ALB/API Gateway. Managed rule groups + your custom (e.g. rate-based) rules. |
| **Shield Advanced** | Paid DDoS protection with the DDoS Response Team and cost-spike protection. $3k/mo, 1-yr commit. Shield Standard (free) is always on. |
| **RTO** | Recovery Time Objective — how long until service is restored after a disaster. A time budget. |
| **RPO** | Recovery Point Objective — how much data (measured in time) you can afford to lose. A data-loss budget. |
| **Pilot light** | DR posture: core data replicated and minimal infra running cold; you "turn up the lights" on failover. Minutes-to-tens-of-minutes RTO. |
| **Warm standby** | DR posture: a scaled-down but *running* copy in the second Region; scale it up on failover. Minutes RTO, seconds RPO, real steady-state cost. |
| **Active/active** | DR posture: both Regions serve live traffic; failover is just shifting weight. Near-zero RTO/RPO, highest cost and complexity. |
| **DynamoDB Global Table** | A multi-Region, multi-active DynamoDB table with last-writer-wins conflict resolution and sub-second replication. |
| **Aurora Global Database** | An Aurora cluster with a primary Region and read-only secondaries, storage-level replication (typically < 1s lag), managed failover. |

---

*If a link 404s, please open an issue so we can replace it.*
