# Week 1 — Quiz

Fourteen questions. Take it with your lecture notes closed. Aim for 12/14 before moving to Week 2. Answer key is at the bottom — don't peek.

---

**Q1.** Why does AWS have 200+ services?

- A) AWS designs hundreds of independent products the way a SaaS company would, each with its own roadmap.
- B) AWS exposes infrastructure as primitives behind APIs, then layers conveniences over those primitives, and almost never deprecates anything — so the catalog only grows.
- C) Each service maps one-to-one to a physical data-center component.
- D) Regulators require a separate service per compliance regime.

---

**Q2.** Which set is entirely **global** (no Region scope) services?

- A) S3, DynamoDB, VPC
- B) IAM, Route 53, CloudFront, Organizations
- C) EC2, EBS, subnets
- D) Lambda, RDS, ElastiCache

---

**Q3.** An EBS volume can be attached to:

- A) Any EC2 instance in the same Region.
- B) Any EC2 instance in the same Organization.
- C) An EC2 instance in the **same Availability Zone** as the volume.
- D) Multiple instances across AZs simultaneously, always.

---

**Q4.** Under the AWS Shared Responsibility Model, for an **S3** bucket, which is **always your** responsibility (not AWS's)?

- A) The durability of the stored objects (the "eleven nines").
- B) Patching the operating system the storage service runs on.
- C) The bucket policy, Block Public Access settings, and who has IAM access to the objects.
- D) The physical security of the data center.

---

**Q5.** What is the correct relationship between a Service Control Policy (SCP) and an IAM policy?

- A) An SCP grants permissions that IAM policies cannot.
- B) The effective permission is the **intersection** of what IAM allows and what the SCP permits; an SCP can only cap, never grant.
- C) An IAM policy overrides an SCP when they conflict.
- D) SCPs and IAM policies are the same mechanism with different names.

---

**Q6.** You attach an SCP to the `dev` OU that denies all actions when `aws:RequestedRegion` equals `us-east-1`, with **no carve-out**. What is the most likely unintended consequence?

- A) Nothing — the deny is perfectly scoped.
- B) Legitimate global operations whose control plane runs in `us-east-1` (e.g. requesting a CloudFront ACM certificate, some IAM/Organizations calls) start failing.
- C) The management account also loses `us-east-1` access.
- D) Billing stops working in every Region.

---

**Q7.** Which command tells you *which account and role you are currently operating as*?

- A) `aws iam get-user`
- B) `aws sts get-caller-identity`
- C) `aws organizations describe-organization`
- D) `aws configure list-profiles`

---

**Q8.** How many programmatic access keys should the **root user** have?

- A) Exactly one, rotated quarterly.
- B) Two, for redundancy.
- C) Zero.
- D) As many as the number of CI pipelines that use root.

---

**Q9.** Where does an SSO/IAM Identity Center profile get written, and where do long-lived access keys live?

- A) Both go in `~/.aws/credentials`.
- B) SSO profiles go in `~/.aws/config`; long-lived keys (which we avoid) go in `~/.aws/credentials`.
- C) Both go in `~/.aws/config`.
- D) SSO profiles go in `~/.aws/credentials`; keys go in `~/.aws/config`.

---

**Q10.** Do Service Control Policies apply to the **management account**?

- A) Yes — SCPs apply to every account in the Organization including the management account.
- B) No — SCPs never restrict the management account, by design. This is why you prove a deny from a *member* account.
- C) Only if the management account is inside an OU.
- D) Only for `Deny` statements, not `Allow` statements.

---

**Q11.** You configure three AWS Budgets via CDK. Which Region must the stack deploy to, and why?

- A) Any Region; Budgets is fully Regional.
- B) `us-east-1`, because the Budgets/Billing API is hosted there even though the service is global.
- C) The Region nearest your users, for latency.
- D) `eu-west-1`, because that is the default home Region for billing.

---

**Q12.** When configuring the Cost & Usage Report for the Athena pipeline in this week's challenge, which format minimizes Athena scan cost?

- A) CSV, gzip-compressed.
- B) JSON.
- C) Parquet (columnar), partitioned by month.
- D) Plain CSV, uncompressed.

---

**Q13.** In the Athena CUR table, a cost-allocation tag named `team` appears as which column — and what is the precondition for it to contain data?

- A) `team`; no precondition.
- B) `tag_team`; you must run a Glue crawler first.
- C) `resource_tags_user_team`; the tag must be **activated** as a cost-allocation tag (and carried by real resources), which is not retroactive.
- D) `user:team`; it populates instantly.

---

**Q14.** What is the C19 "prove it" rule for guardrails?

- A) If the SCP exists in the console, the guardrail is done.
- B) A control you have not tested is a control you do not have — you must attempt the blocked action and read the `explicit deny in a service control policy` in the error.
- C) Guardrails are proven by reading the AWS documentation.
- D) A guardrail is proven once `tofu apply` returns no errors.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Primitives behind APIs, conveniences layered over primitives, and a near-zero deprecation rate. That origin story is why the catalog only grows and why ~30 services matter to any given team.
2. **B** — IAM, Route 53, CloudFront, and Organizations are global. S3 buckets, DynamoDB tables, and VPCs are Regional; EC2 instances, EBS volumes, and subnets are zonal.
3. **C** — EBS is a zonal resource. A volume in `eu-west-1a` can only attach to an instance in `eu-west-1a`. (Multi-attach exists for specific io2 cases but is not the general rule, and never crosses AZs.)
4. **C** — Bucket policy, Block Public Access, encryption choice, and IAM access are always yours. Durability and physical security are AWS's. "Your data and your IAM are always yours" is the load-bearing line of the shared responsibility model.
5. **B** — SCPs cap; IAM grants. The effective permission is the intersection. An explicit deny anywhere wins.
6. **B** — Several global services route through `us-east-1`. A blanket region deny breaks them. The production version uses a `NotAction` carve-out for `cloudfront`, `iam`, `route53`, `organizations`, `sts`, etc.
7. **B** — `aws sts get-caller-identity` returns the account id and the ARN of the current principal. Run it before any destructive action.
8. **C** — Zero. Long-lived root access keys are the single worst credential in AWS. `RootAccessKeys` must read `0`.
9. **B** — Modern setups keep SSO profiles in `~/.aws/config` and ideally leave `~/.aws/credentials` empty. Long-lived keys, which this course avoids, are what `credentials` was for.
10. **B** — SCPs never restrict the management account. That is exactly why you must assume into a *member* account under the constrained OU to observe the deny.
11. **B** — The Budgets/Billing API is hosted in `us-east-1`. The stack must target `us-east-1` regardless of where the rest of your infrastructure lives — one of the "us-east-1 is special" cases.
12. **C** — Parquet is columnar, so Athena reads only the columns your query touches; partitioning by month lets you scan a single month. Both slash scan cost versus row-oriented CSV/JSON.
13. **C** — The column is `resource_tags_user_team`. It only contains data for tags you have activated as cost-allocation tags, and activation is not retroactive — plus a resource has to actually carry the tag.
14. **B** — "A control you have not tested is a control you do not have." You attempt the blocked action and read the explicit-deny string. A clean `apply` is not proof; a denied action is.

</details>

---

If you scored under 10, re-read the lectures for the questions you missed. If you scored 12 or higher, you're ready for the [homework](./homework.md) and the [mini-project](./mini-project/README.md).
