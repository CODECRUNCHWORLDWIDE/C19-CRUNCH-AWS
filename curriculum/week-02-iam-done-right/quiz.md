# Week 2 — Quiz

Fourteen questions on production IAM. Take it with your lecture notes closed. Aim for 12/14 before moving to Week 3 — this is the most important week, and the quiz reflects it. Answer key at the bottom; don't peek.

---

**Q1.** In AWS IAM policy evaluation, which statement is true?

- A) An explicit `Allow` overrides an explicit `Deny` if it is more specific.
- B) An explicit `Deny` in any applicable policy overrides every `Allow`.
- C) The most recently attached policy wins.
- D) Resource policies always override identity policies.

---

**Q2.** A principal in account A wants to call `s3:GetObject` on a bucket in account B. For the request to succeed:

- A) Only the identity policy in account A must allow it.
- B) Only the bucket policy in account B must allow it.
- C) Both the identity policy in A and the bucket policy in B must allow it.
- D) Either one allowing it is sufficient, as it is within one Organization.

---

**Q3.** What does a permission boundary do?

- A) Grants the permissions listed in it to the principal.
- B) Caps the principal's effective permissions to the intersection of the boundary and its identity policies; it grants nothing.
- C) Replaces the principal's identity policies entirely.
- D) Applies only to resource-based policies.

---

**Q4.** This statement appears in an identity policy:

```json
{ "Effect": "Allow", "NotAction": ["iam:*"], "Resource": "*" }
```

What does it allow?

- A) Only IAM actions.
- B) Nothing — `NotAction` denies.
- C) Every action in AWS except IAM actions, on every resource.
- D) It is a syntax error.

---

**Q5.** Why is `iam:PassRole` on `"Resource": "*"` dangerous?

- A) It lets the principal pass any role to any service, enabling privilege escalation (e.g. launch a Lambda/EC2 with an admin role).
- B) It does nothing without `sts:AssumeRole`.
- C) It only affects roles the principal already owns.
- D) It is harmless; `PassRole` cannot escalate privileges.

---

**Q6.** You set up a role for a third-party SaaS vendor to assume. The vendor serves many customers from one AWS account. Which condition is mandatory to prevent the confused-deputy problem?

- A) `aws:RequestedRegion`
- B) `aws:MultiFactorAuthPresent`
- C) `sts:ExternalId`
- D) `aws:SecureTransport`

---

**Q7.** A policy conditions a grant on `"StringEquals": { "aws:username": "deploy-bot" }`, but the caller authenticates as an assumed-role session (a CI role via OIDC). What happens?

- A) The condition matches because the role's name contains `deploy-bot`.
- B) `aws:username` is not populated for role sessions, so the condition does not match and the statement does not apply.
- C) It throws an error at evaluation time.
- D) It matches any principal.

---

**Q8.** Which condition key restricts access to principals inside your own AWS Organization?

- A) `aws:SourceAccount`
- B) `aws:PrincipalOrgID`
- C) `aws:userid`
- D) `aws:ResourceTag`

---

**Q9.** A `Deny` statement targets `arn:aws:s3:::logs` for the action `s3:DeleteObject`, while a broad `Allow s3:*` covers everything. Can objects in the `logs` bucket be deleted?

- A) No — the deny blocks it.
- B) Yes — `s3:DeleteObject` acts on object ARNs (`logs/*`), not the bucket ARN, so the deny never matches and the allow stands.
- C) No — explicit deny always wins regardless of ARN.
- D) Only if Block Public Access is off.

---

**Q10.** This SCP denies all actions when `aws:RequestedRegion` is not `eu-west-1`. What breaks?

- A) Nothing; it is a clean region lockdown.
- B) Global services (IAM, CloudFront, Route 53, the STS global endpoint) report `us-east-1`/`aws-global` and get denied, locking the account out of administration.
- C) Only EC2 in other regions.
- D) Billing.

---

**Q11.** ABAC: a policy grants admin to any principal tagged `role=admin`. Developers have `iam:TagRole`. What is the flaw?

- A) None; tag-based conditions are always safe.
- B) Developers can tag a role they control with `role=admin` and escalate, because they control the attribute the condition reads.
- C) `iam:TagRole` cannot set the `role` tag.
- D) The condition only works for users, not roles.

---

**Q12.** Why does a `cdk bootstrap` create *multiple* roles (deploy, file-publishing, CloudFormation execution) instead of one?

- A) To make the bill higher.
- B) So the role the human/CI assumes does not itself hold the powerful resource-creation permissions; those live in the CloudFormation execution role, assumed only by the CloudFormation service.
- C) CDK requires exactly three roles by design with no security reason.
- D) Each AWS region needs its own role.

---

**Q13.** Which IAM Access Analyzer finding type tells you about IAM roles and permissions that have not been used recently?

- A) External-access findings.
- B) Unused-access findings.
- C) Public-access findings.
- D) Drift findings.

---

**Q14.** A role's identity policy allows `s3:*` on `*`. Its permission boundary allows only `s3:GetObject` on `arn:aws:s3:::dev-*/*`. What can the role actually do to S3?

- A) Everything `s3:*` allows, since the identity policy is broader.
- B) Only `s3:GetObject` on `dev-*` objects — the intersection of identity policy and boundary.
- C) Nothing, because the two disagree.
- D) Only what the boundary lists, ignoring the identity policy entirely (so `s3:GetObject` on all buckets).

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Explicit deny wins over everything. This is the single most important rule in IAM; there is no "more specific allow" override.
2. **C** — Cross-account access requires an `Allow` on *both* sides: the identity policy in the calling account and the resource policy in the resource's account. Within a single account, either side allowing is enough; across accounts, both.
3. **B** — A boundary caps; it is the intersection of (identity policy) ∩ (boundary). It never grants on its own. A permission the boundary "allows" but no identity policy grants is still denied.
4. **C** — `Allow` + `NotAction` means "allow everything *except* the listed actions." This grants `AdministratorAccess` minus IAM. The classic `NotAction` trap.
5. **A** — `PassRole` is the permission to hand a role to a service. On `*`, the principal can pass a privileged role (e.g. admin) to a Lambda/EC2 they create and assume it indirectly — a privilege-escalation primitive. Always scope `PassRole` and pin `iam:PassedToService`.
6. **C** — `sts:ExternalId` is the per-customer secret that prevents one of the vendor's customers from tricking the vendor into assuming *your* role. AWS docs treat it as mandatory for the third-party pattern.
7. **B** — `aws:username` is only populated for IAM *user* principals, not assumed-role sessions. The condition silently fails to match. Use `aws:PrincipalArn` or `aws:PrincipalTag` for role sessions.
8. **B** — `aws:PrincipalOrgID` matches when the calling principal belongs to the specified Organization. `aws:SourceAccount` is for service-principal confused-deputy guards, a different purpose.
9. **B** — `s3:DeleteObject` acts on object ARNs (`logs/*`), not the bucket ARN (`logs`). A deny on the bucket ARN never matches the object-level action, so the broad allow stands. ARN granularity matters; explicit deny only wins over the resources it actually matches.
10. **B** — Global services report `us-east-1` or `aws-global` in `aws:RequestedRegion`. A blanket region deny without a global-service carve-out bricks IAM/CloudFront/Route 53/STS-global and locks you out.
11. **B** — A condition is only as strong as the trustworthiness of the attribute it reads. If the principal can set its own tags (`iam:TagRole`), a tag-based grant is self-serviceable escalation. Use IdP-set session tags and deny self-tagging of privileged keys.
12. **B** — Splitting roles means the assumed (deploy) role does not itself carry the dangerous resource-creation/IAM permissions; those live in the CloudFormation execution role, assumed only by the CloudFormation service. A leaked deploy credential then cannot directly create admin roles. (Lecture 2's "three roles for one deploy.")
13. **B** — Unused-access findings surface roles, users, and permissions not used in the configured window. External-access findings surface resources shared outside the account/Org. Two different analyzer types.
14. **B** — Effective permissions are the intersection: identity policy (`s3:*` on `*`) ∩ boundary (`s3:GetObject` on `dev-*/*`) = `s3:GetObject` on `dev-*` objects only. The boundary caps; it does not by itself grant (D is wrong because the identity policy is still required and is narrower in scope here only via intersection).

</details>

---

If you scored under 10, re-read Lecture 1 (evaluation logic) and Lecture 2 (boundaries) for the questions you missed. If you scored 12+, you are ready for the [homework](./homework.md) and the [mini-project](./mini-project/README.md).
