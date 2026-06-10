# Lecture 1 — The Security Stack: KMS, Secrets, GuardDuty/Security Hub, and the Edge

> **Reading time:** ~80 minutes. **Hands-on time:** ~60 minutes (you turn the detective stack on and read your first real findings).

This is the lecture that turns "we have IAM and encryption on" into "we have a security *baseline*." Encryption-at-rest and least-privilege IAM (Weeks 2 and 6) are necessary and not sufficient. A production account also needs to *detect* what is going wrong, *aggregate* its posture into one place, *manage* its secrets without baking them into env vars, and *defend* its edge from the traffic that least-privilege IAM never sees. By the end of this lecture you will understand KMS deeply enough to author a key policy that passes a Week-2-style review, choose Secrets Manager or Parameter Store on the merits, stand up the GuardDuty → Security Hub detection-and-posture pairing, and place the edge controls — WAF, Shield, Network Firewall, ACM — where they belong. The thread running through all of it: **security is layered, and each layer answers a different question.** KMS answers "is the data readable if someone steals the bytes?" GuardDuty answers "is something behaving like an attacker right now?" WAF answers "should this HTTP request even reach my app?" You need all three, and they do not substitute for one another.

## 1.1 — KMS is envelope encryption, and that one fact explains everything

A junior engineer thinks KMS is "the thing that encrypts my S3 bucket." That picture is missing the mechanism, and the mechanism is the whole design. KMS almost never encrypts your data directly. It encrypts a *key* that encrypts your data. This is **envelope encryption**, and it is why KMS scales to encrypting petabytes while a single KMS key never sees more than a few kilobytes.

Here is the flow when S3 (or EBS, or RDS) writes an encrypted object:

1. The service calls KMS `GenerateDataKey` against your customer-managed key (CMK).
2. KMS returns *two* things: a fresh 256-bit data key in **plaintext**, and the same data key **encrypted** under your CMK.
3. The service encrypts your actual data with the plaintext data key (fast, local, AES-256), then **throws the plaintext data key away** and stores the *encrypted* data key alongside the ciphertext.
4. To decrypt later, the service hands the encrypted data key back to KMS `Decrypt`, KMS returns the plaintext data key (after checking your IAM/key-policy permission), and the service decrypts the data locally.

```
   Write path                                  Read path
   ──────────                                  ─────────
   data ──┐                                    encrypted data ──┐
          │  encrypt with plaintext data key            decrypt with plaintext data key
   KMS GenerateDataKey(CMK)                     KMS Decrypt(encrypted data key, CMK)
     ├─ plaintext data key  ──► use, then discard   ◄── returns plaintext data key
     └─ encrypted data key  ──► store next to data ──► hand back to KMS on read
```

Three consequences fall out of this that you must internalize:

- **The CMK never touches your data.** It only ever encrypts/decrypts small data keys. This is why one CMK can protect an unbounded amount of data, and why KMS is cheap (you pay per *API call* and per key-month, not per byte).
- **Permission is checked at `Decrypt` time.** If a principal cannot call `kms:Decrypt` on the CMK, it cannot read the data *even if it has `s3:GetObject`.* This is the layered-security payoff: KMS is a second lock that IAM-on-the-bucket alone does not open. Revoke a principal's KMS access and the encrypted data is bytes-shaped noise to them.
- **Deleting the CMK destroys the data, irrecoverably.** Without the CMK you cannot decrypt the data keys, so you cannot decrypt anything. This is why KMS makes key *deletion* a scheduled operation with a mandatory 7–30 day waiting window. Treat a CMK delete the way you treat `DROP DATABASE`.

### AWS-managed keys vs customer-managed keys

KMS gives you two kinds of symmetric key, and the difference is *who controls the policy*:

- **AWS-managed keys** (alias `aws/s3`, `aws/rds`, `aws/secretsmanager`, …) are created and managed by AWS. They are free for storage, rotate automatically every year, and require zero setup — but **you cannot edit their key policy.** They grant access to the owning service for your account and nothing more. Fine for "encrypt this, I don't need to control who else can decrypt."
- **Customer-managed keys (CMKs)** are keys *you* create. You write the key policy, you decide rotation, you can share them cross-account, you can make them multi-Region (Lecture 2), and you pay $1/key/month plus API calls. You reach for a CMK the moment you need: a key policy you control, cross-account access, multi-Region replication, granular `kms:ViaService` conditions, or an audit story that says "we own the keys."

The production default for anything that matters — the data lake, the DB, secrets — is a **CMK**, precisely because the control points (policy, rotation, cross-account, multi-Region) are exactly the things a security review asks about. The capstone uses CMKs everywhere for this reason.

### Automatic rotation

A CMK can rotate its backing key material automatically once a year (you can also rotate on a custom 90-day-to-yearly schedule now). Rotation generates new key material but keeps the *same key ID and ARN* — old data stays decryptable with the retained old material, new data uses the new material. It is transparent and you should turn it on:

```typescript
import * as kms from 'aws-cdk-lib/aws-kms';

const dataKey = new kms.Key(this, 'DataKey', {
  alias: 'capstone/data',
  description: 'CMK for the capstone data lake and DB encryption',
  enableKeyRotation: true,           // annual automatic rotation; do this for every CMK
  // In prod, RETAIN so a stack delete can never orphan-then-delete the key.
  removalPolicy: cdk.RemovalPolicy.RETAIN,
});
```

## 1.2 — Key policies: the part everyone misreads

Here is the single most misunderstood fact about KMS, and it costs teams a debugging afternoon every time. **For a KMS key, the key policy is the root of trust — not IAM.** A KMS key policy is a *resource* policy (like an S3 bucket policy or an SQS queue policy), and unlike most resource policies, KMS evaluates it as *authoritative*: an IAM policy granting `kms:Decrypt` does **nothing** unless the key policy *also* delegates authority to IAM.

That delegation is what the famous default key-policy statement does:

```json
{
  "Sid": "EnableIAMUserPermissions",
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::111122223333:root" },
  "Action": "kms:*",
  "Resource": "*"
}
```

People read `"Action": "kms:*"` on `"Principal": root` and panic — "this grants everyone everything!" It does not. `arn:aws:iam::111122223333:root` means "the account as a whole," and granting it `kms:*` means "**defer to IAM** for principals in this account." Without this statement, *no IAM policy in the account can grant KMS access to this key* — the key is only usable by principals named explicitly in the key policy. With it, you can manage access the normal IAM way. It is a delegation, not a blanket grant. Read it correctly and you understand KMS access control.

A production key policy separates two roles that should never be the same principal:

- **Key administrators** — can manage the key (change policy, schedule deletion, enable rotation) but **cannot use it** to encrypt/decrypt.
- **Key users** — can `Encrypt`/`Decrypt`/`GenerateDataKey` but **cannot administer** the key.

```typescript
const dataKey = new kms.Key(this, 'DataKey', {
  alias: 'capstone/data',
  enableKeyRotation: true,
  // 'admins' can manage but not use; 'grant*' methods add usage for specific principals.
  admins: [new iam.Role(this, 'KeyAdminRole', {
    assumedBy: new iam.AccountRootPrincipal(),   // assumable only by your break-glass admins
  })],
});

// Key USERS are granted usage explicitly and narrowly:
dataKey.grantEncryptDecrypt(lakeWriterRole);     // the Firehose/app role that writes the lake
dataKey.grantDecrypt(analyticsReaderRole);       // the read-only analytics role
```

The separation matters because it limits blast radius: if the analytics-reader role is compromised, the attacker can read data but cannot rotate or delete the key or grant themselves more. A key policy where one role both administers and uses the key is the KMS equivalent of `Resource: "*"` — it will (correctly) fail a review.

### `kms:ViaService` — the condition that scopes a key to a service

You often want "this key may only be used *via S3*, never directly by a principal calling KMS." The `kms:ViaService` condition does exactly that:

```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::111122223333:role/lake-writer" },
  "Action": ["kms:Encrypt", "kms:GenerateDataKey"],
  "Resource": "*",
  "Condition": {
    "StringEquals": { "kms:ViaService": "s3.us-east-1.amazonaws.com" }
  }
}
```

Now the `lake-writer` role can encrypt *through S3* but cannot call `kms:Encrypt` directly to encrypt arbitrary blobs. It is least-privilege applied to the *path*, not just the principal.

### Grants — the programmatic alternative

A **grant** is a temporary, programmatic permission on a key that a service creates on your behalf — for example, when you attach an encrypted EBS volume, EC2 creates a grant so the instance can decrypt it, then retires the grant when the volume detaches. You rarely author grants by hand, but you must recognize them: when you see `kms:CreateGrant` in a service role's policy, it is the service saying "let me make temporary key-usage permissions as I need them." Grants vs key-policy edits: use a **key-policy** statement for durable, named principals; let services use **grants** for ephemeral, attach-time access.

## 1.3 — Secrets Manager vs Parameter Store

Both store configuration and secrets. The decision is not religious; it is four axes.

| Axis | Secrets Manager | SSM Parameter Store |
|---|---|---|
| **Rotation** | Built-in, Lambda-backed, scheduled | None (you build it) |
| **Cost** | ~$0.40/secret/month + API calls | **Free** for Standard params; Advanced ~$0.05/param/month |
| **Size limit** | 64 KB | 4 KB (Standard), 8 KB (Advanced) |
| **Cross-account** | Resource policy on the secret | Via RAM/KMS, clunkier |
| **Native integrations** | RDS/Aurora, Redshift auto-rotation | Wide read access from SSM-aware services |

The decision rule that holds 95% of the time:

- **A database password, an API key for a third party, anything that should rotate** → **Secrets Manager.** The built-in, RDS-integrated rotation is the feature you are paying $0.40/month for, and it is worth it. A DB password that nobody can rotate without downtime is a liability; Secrets Manager + RDS rotation makes rotation a non-event.
- **A feature flag, a config value, a non-secret parameter, a secret you will rotate yourself rarely** → **Parameter Store.** It is free at Standard tier, and `SecureString` parameters are still KMS-encrypted. Do not pay Secrets Manager prices for `LOG_LEVEL=info`.

Here is a Secrets Manager secret with automatic rotation for a database credential, in CDK:

```typescript
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';

// A generated secret (CDK never puts the value in the template / CloudFormation state).
const dbSecret = new secretsmanager.Secret(this, 'DbSecret', {
  secretName: 'capstone/aurora/app',
  encryptionKey: dataKey,              // CMK, not the default aws/secretsmanager key
  generateSecretString: {
    secretStringTemplate: JSON.stringify({ username: 'app' }),
    generateStringKey: 'password',     // CDK fills 'password' with a random value
    excludePunctuation: true,
    passwordLength: 32,
  },
});

// Hand the secret to the Aurora cluster and turn on managed rotation every 30 days.
dbSecret.addRotationSchedule('Rotate', {
  hostedRotation: secretsmanager.HostedRotation.postgreSqlSingleUser(),
  automaticallyAfter: cdk.Duration.days(30),
});
```

Note `secretStringTemplate` + `generateSecretString`: the actual password is generated by CloudFormation at deploy time and **never appears in your source, your synthesized template, or your CloudFormation drift output.** A secret you hard-code in CDK is not a secret. This pattern is the only acceptable way to seed one.

## 1.4 — The detective stack: GuardDuty, Security Hub, Macie, Inspector

KMS and IAM are *preventive* — they stop bad things. The detective stack tells you when something bad is *happening anyway*, because prevention is never perfect. Four services, four questions.

### GuardDuty — "is something behaving like an attacker?"

GuardDuty is managed threat detection. It continuously analyzes three data sources **with no agent and no setup beyond turning it on**:

1. **CloudTrail** — management events (and optionally S3 data events). Catches "an IAM user from a Tor exit node called `CreateUser`," "a key was disabled," "an unusual API was invoked."
2. **VPC Flow Logs** — network metadata. Catches "your EC2 instance is talking to a known crypto-mining pool," "outbound traffic to a C2 server's IP."
3. **DNS query logs** — Catches "a host is resolving algorithmically-generated domain names" (DGA, a malware signature).

On top of those core sources, GuardDuty has opt-in **protection plans** that each add a data source for a specific surface: **EKS Runtime Monitoring** (syscall-level container threats via a managed agent), **S3 Protection** (S3 data-event analysis), **RDS Protection** (anomalous login analysis), **Lambda Protection** (network monitoring of function activity), and **Malware Protection** (scans EBS volumes attached to suspect instances). You enable the plans you need; each adds cost (read the pricing page) and surface coverage.

GuardDuty emits **findings** with a type (e.g. `UnauthorizedAccess:EC2/SSHBruteForce`, `CryptoCurrency:EC2/BitcoinTool.B!DNS`), a severity (Low/Medium/High), and the evidence. The senior move is to enable it **org-wide via a delegated administrator** — you designate one account (usually a security/audit account, *not* the management account) as the GuardDuty admin, and it auto-enrolls every member account. This is the same delegated-admin pattern Security Hub, Macie, and Inspector all use:

```typescript
import * as guardduty from 'aws-cdk-lib/aws-guardduty';

// In the delegated-admin (security) account:
const detector = new guardduty.CfnDetector(this, 'Detector', {
  enable: true,
  findingPublishingFrequency: 'FIFTEEN_MINUTES',   // how often findings export to EventBridge/SecurityHub
  dataSources: {
    s3Logs: { enable: true },
    kubernetes: { auditLogs: { enable: true } },
    malwareProtection: {
      scanEc2InstanceWithFindings: { ebsVolumes: true },
    },
  },
});
```

A finding alone does nothing; you route it. The production pattern is **GuardDuty finding → EventBridge rule → SNS/Lambda → ticket or auto-remediation.** A High-severity `SSHBruteForce` finding can fire a Lambda that adds the source IP to a WAF block list or a NACL deny — closing the loop from detection to response. You will not build full auto-remediation this week, but you will route findings to a destination, because a finding nobody reads is theater.

### Security Hub — "what is my overall posture, in one place?"

GuardDuty finds threats; Inspector finds vulnerabilities; Macie finds exposed data; Config finds misconfigurations. Without aggregation you have four consoles and no single picture. **Security Hub is the aggregator.** It does two jobs:

1. **Runs compliance standards as continuous controls.** Enable the **AWS Foundational Security Best Practices (FSBP)** standard and the **CIS AWS Foundations Benchmark**, and Security Hub continuously checks dozens-to-hundreds of controls — "is S3 Block Public Access on?", "is CloudTrail encrypted?", "do IAM users have unused credentials?" — and scores you.
2. **Ingests findings from the other services** in a normalized format (**ASFF — AWS Security Finding Format**) so GuardDuty threats, Inspector CVEs, and Macie PII findings all land in one searchable, severity-sorted view, with cross-Region aggregation so you have *one* pane for *all* Regions.

```typescript
import * as securityhub from 'aws-cdk-lib/aws-securityhub';

new securityhub.CfnHub(this, 'Hub', {
  // Enabling the hub turns on default standards; you tune which ones in the console/CLI.
  controlFindingGenerator: 'SECURITY_CONTROL',     // the consolidated-control finding model
});
```

The triage workflow you run Tuesday: open Security Hub, filter findings by `SeverityLabel = CRITICAL` then `HIGH`, and for each one either **fix it** (turn on the control, patch the CVE, lock the bucket) or **suppress with a documented reason** (the finding is a known, accepted risk). The deliverable is a finding-disposition table: every Critical and High has a "fixed" or "accepted because X" next to it. An unread Critical finding is the line item that ends up in a breach postmortem.

### Macie — "is there sensitive data where it shouldn't be?"

Macie is managed sensitive-data discovery for **S3**. It uses managed data identifiers (credit-card numbers, SSNs, AWS secret keys, names, addresses) and your custom regex identifiers to scan objects and report what PII lives where. You run a **sensitive-data discovery job** against a bucket (or a prefix), and it produces findings like "this object contains 412 credit-card numbers."

The catch is cost: **Macie bills per GB inspected.** Pointing a discovery job at a multi-terabyte lake is a real bill. The right pattern is to *sample* — scope the job to a prefix or use Macie's automated sampling — for ongoing monitoring, and run full scans deliberately. This week you point Macie at a small sample prefix of the data lake, not the whole thing.

### Inspector — "what CVEs am I running?"

Inspector is continuous vulnerability scanning for **ECR container images, EC2 instances, and Lambda functions**. For the EKS/container story, the path runs through ECR: Inspector scans every image you push, maps installed packages to known CVEs, and emits findings with a severity and a fix version. Turn it on, push your capstone images, and Inspector tells you "your base image has a Critical OpenSSL CVE; upgrade to X."

```bash
# Org-wide enable for the three scan types (run in the delegated-admin account):
aws inspector2 enable --resource-types ECR EC2 LAMBDA --account-ids <member-account-ids>
```

The triage is the same shape as Security Hub's: list Critical/High findings, and for each either rebuild the image on a patched base (the fix) or suppress with a justification (the CVE is not reachable in your usage). The senior framing: **Inspector tells you what's vulnerable; it does not tell you what's exploitable in *your* context.** A Critical CVE in a library you never call is lower real risk than a Medium in your request path. Triage with that judgment, but never *ignore* — document the call.

## 1.5 — The edge: WAF, Shield, Network Firewall, ACM

The detective stack watches what happens inside. The edge controls decide what gets *in*. Four tools, three layers.

### WAF — Layer 7, "should this HTTP request reach my app?"

AWS WAF is a web application firewall you attach to CloudFront, an ALB, or API Gateway. It inspects HTTP requests and allows/blocks/counts them based on rules. You almost never write a WAF from scratch — you start from **AWS managed rule groups**:

- **Core rule set (CRS)** — the OWASP-style baseline (bad inputs, common injection patterns).
- **Known bad inputs** — exploit signatures.
- **SQL database** — SQL-injection patterns.
- **IP reputation / Anonymous IP** — block known-bad and anonymizing-proxy IPs.

On top of the managed baseline you add *your* rules — most commonly a **rate-based rule** to blunt brute-force and scraping:

```typescript
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';

new wafv2.CfnWebACL(this, 'WebAcl', {
  scope: 'CLOUDFRONT',                 // 'REGIONAL' for ALB/API Gateway
  defaultAction: { allow: {} },
  visibilityConfig: {
    cloudWatchMetricsEnabled: true,
    metricName: 'capstoneWebAcl',
    sampledRequestsEnabled: true,
  },
  rules: [
    {
      name: 'AWSManagedCommonRules',
      priority: 0,
      overrideAction: { none: {} },
      statement: {
        managedRuleGroupStatement: {
          vendorName: 'AWS',
          name: 'AWSManagedRulesCommonRuleSet',
        },
      },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'commonRules',
        sampledRequestsEnabled: true,
      },
    },
    {
      name: 'RateLimit',
      priority: 1,
      action: { block: {} },           // block IPs exceeding the limit
      statement: {
        rateBasedStatement: {
          limit: 2000,                 // requests per 5-minute window per source IP
          aggregateKeyType: 'IP',
        },
      },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'rateLimit',
        sampledRequestsEnabled: true,
      },
    },
  ],
});
```

The capstone's WAF is exactly this shape: managed common rules + a custom rate-based rule. You will prove the rate rule fires by hammering the endpoint with `curl` until you see `403`s and a `RateLimit` metric in CloudWatch.

### Shield — Layer 3/4, DDoS

**Shield Standard** is free, always on, and protects every AWS account against common volumetric (L3/L4) DDoS automatically. You already have it; you did nothing. **Shield Advanced** ($3,000/month, 1-year commitment per organization) adds: the **DDoS Response Team** (humans who help you during an attack), near-real-time attack visibility, WAF at no extra charge on protected resources, and — the line that often justifies it — **cost protection**, which credits back the scaling charges a DDoS attack would otherwise run up. The honest decision: Shield Advanced is worth it when a DDoS-induced bill spike or downtime would cost *more* than $36k/year, i.e. for real revenue-bearing production at scale. For a course capstone, you *reason* about it and stop at Standard. Knowing *when* it is worth $3k/month is the skill.

### Network Firewall — Layer 3/4/7 inside the VPC

Security Groups and NACLs (Week 4) are stateful/stateless filters on ports and CIDRs. **AWS Network Firewall** is a managed, Suricata-rule-compatible firewall you place in your VPC for deeper inspection — domain-based egress filtering ("instances may only reach `*.amazonaws.com` and `github.com`"), intrusion detection/prevention with signature rules, and stateful flow inspection that SGs/NACLs cannot express. The decision: SGs/NACLs for coarse port/CIDR control (always); Network Firewall when you need *application-aware egress control* or IDS/IPS inside the VPC. It is the control that stops a compromised instance from exfiltrating to an arbitrary domain.

### ACM and ACM Private CA — TLS

**ACM** issues and auto-renews *public* TLS certificates for your CloudFront/ALB/API Gateway, free. You did this in Week 4. **ACM Private CA** is the other half: a managed private certificate authority for *internal* TLS and **mTLS** — service-to-service certs inside your VPC/mesh that you do not want a public CA to issue. The decision: ACM for the public edge (the cert browsers trust); Private CA for internal mutual-TLS between services (the cert your own services trust). The capstone uses ACM for the public CloudFront cert; Private CA appears when the EKS service mesh needs internal mTLS.

## 1.6 — How the layers compose

Step back and see the whole baseline as one picture, each layer answering its own question:

```
   Internet
      │
      ▼  Shield Standard (L3/4 DDoS, free, always on)
   CloudFront ── WAF web ACL (L7: managed rules + rate limit)  ── ACM public TLS
      │
      ▼
   ALB / API Gateway
      │
      ▼  VPC ── Security Groups / NACLs (port/CIDR) ── Network Firewall (egress/IDS)
   EKS / Lambda / Aurora / DynamoDB / S3
      │                                   all encrypted with CMKs (envelope encryption)
      │                                   secrets in Secrets Manager (rotated)
      ▼
   GuardDuty (threats) ─┐
   Inspector (CVEs)     ├─► Security Hub (one posture pane, ASFF) ─► EventBridge ─► respond
   Macie (PII in S3)    ┘
```

Read it top to bottom and the layering is obvious: Shield handles the flood, WAF handles the malicious request, ACM handles the encryption-in-transit, SGs/Network Firewall handle the network, KMS handles encryption-at-rest, Secrets Manager handles the credentials, and the GuardDuty/Inspector/Macie → Security Hub stack watches all of it and tells you when something is wrong. No single layer is the security; the *composition* is.

## 1.7 — Open-source comparators (what you traded away)

- **Falco / Wazuh** replace GuardDuty: run the sensors and rules yourself. You gain control and portability and avoid per-GB analysis fees; you take on operating the detection pipeline, tuning the rules, and storing the events. GuardDuty's value is that the rules are AWS's problem and the data sources need no agent.
- **Trivy / Grype** replace Inspector and improve on it in one way: they scan in *CI*, before the image is pushed, so a vulnerable image never reaches the registry. Inspector scans after the push. Many teams run *both* — Trivy as a CI gate, Inspector as the continuous runtime backstop.
- **HashiCorp Vault** replaces Secrets Manager + ACM Private CA and exceeds both (dynamic secrets, PKI, transit encryption). You give up "AWS runs it" and take on operating a stateful, security-critical HA service. For a small team, Secrets Manager's managed rotation is worth more than Vault's extra power.
- **OPA / Conftest** replace Security Hub's controls in spirit by *preventing* misconfiguration in CI instead of *detecting* it after deploy. The mature posture is both: OPA in the pipeline to stop the bad config, Security Hub in the account to catch what slipped through.

The pattern across all of these: **managed detective/secrets services move you from a you-operate-it world to a someone-else-operates-it world, and you pay per unit of work (per GB analyzed, per secret, per image) instead of per server.** It is the same fixed-vs-variable shape you met with Athena and Bedrock in Week 11, now applied to security.

## 1.8 — What you should be able to do now

After this lecture and the Monday/Tuesday/Wednesday exercises you should be able to:

- Explain envelope encryption and why one CMK can protect petabytes.
- Read the default key policy's root-`kms:*` statement correctly as an IAM *delegation*, not a blanket grant.
- Author a key policy that separates administrators from users, and scope usage with `kms:ViaService`.
- Choose Secrets Manager vs Parameter Store on rotation, cost, and size, and seed a generated secret that never appears in source.
- Enable GuardDuty org-wide via a delegated administrator and name its three core data sources and the protection plans.
- Aggregate posture in Security Hub, enable FSBP/CIS, and triage findings to a documented disposition.
- Scope a Macie discovery job and an Inspector scan, and resolve Critical/High findings.
- Place WAF (L7), Shield (L3/4), Network Firewall (VPC egress/IDS), and ACM/Private CA (TLS) at the right layer, and say when Shield Advanced is worth $3k/month.

## 1.9 — Exercises that go with this lecture

- **Exercise 1 — Security baseline.** Enable GuardDuty/Security Hub/Macie/Inspector, generate a finding, and triage every Critical/High to a documented disposition.
- **Exercise 2 — Multi-region KMS + Secrets rotation.** Author a multi-Region CMK and a rotated secret, and prove both with boto3 (the multi-Region key is the bridge into Lecture 2's encrypted CRR).

Bring your finding-disposition table and your working CMK to Thursday. Lecture 2's encrypted cross-Region replication assumes you have a multi-Region key, and the DR drill assumes the detective stack is already watching the second Region.
