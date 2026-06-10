# Week 7 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 8. Answer key at the bottom — don't peek.

---

**Q1.** Why is the lecture's central claim — "your pipeline IAM role is more dangerous than your prod IAM role" — true?

- A) Pipeline roles always have `AdministratorAccess` by default and prod roles do not.
- B) The prod role is scoped to *data*; the pipeline role controls *code and identity* — it can replace the running application and pass roles to it, escalating beyond what any single prod role can do.
- C) Pipeline roles are stored as access keys and prod roles are not.
- D) Prod roles run inside the VPC and pipeline roles run on the public internet.

---

**Q2.** A CodeBuild project's `buildspec.yml` is editable by anyone who can open a pull request against the repo. If the pipeline builds PRs *with the deploy role's credentials available*, what is the risk class, and what is it called?

- A) No risk — CodeBuild sandboxes the build so credentials cannot be exfiltrated.
- B) A poisoned-pipeline-execution (PPE) attack: a malicious PR edits the buildspec to exfiltrate the build/deploy credentials. Build untrusted input (PRs) with a low-privilege role, never the deploy role.
- C) A confused-deputy attack, fixed by adding `aws:SourceArn`.
- D) A privilege-boundary bypass, fixed by deleting the permission boundary.

---

**Q3.** Your pipeline's deploy role has `iam:PassRole` on `Resource: "*"` with no condition. Why is this dangerous, and what is the correct scoping?

- A) It is fine; `iam:PassRole` is read-only.
- B) It lets the pipeline attach *any* role in the account (including admin roles) to a new ECS task or Lambda — privilege escalation. Scope `Resource` to the specific task/execution role ARNs and add `Condition: { StringEquals: { "iam:PassedToService": "ecs-tasks.amazonaws.com" } }`.
- C) It only matters for cross-account; same-account `PassRole` is safe on `*`.
- D) It should be `iam:GetRole` instead.

---

**Q4.** You connect CodePipeline to GitHub with a classic personal access token (PAT) stored in Secrets Manager. Name two concrete problems versus using CodeConnections.

- A) PATs are faster but less secure; no other difference.
- B) A classic PAT is a long-lived bearer credential with broad (often read+write) repo scope that does not auto-expire and is a single secret that, if read by an over-scoped role, grants push access to your source — whereas CodeConnections stores no token in your account, scopes access via a revocable GitHub App, and is gated by `codeconnections:UseConnection`.
- C) PATs cannot trigger on push; CodeConnections can.
- D) CodeConnections is deprecated; PATs are the current recommendation.

---

**Q5.** In an ECS blue/green deployment, how many target groups and listeners are involved, and what does the canary step actually change?

- A) One target group; the canary scales it up.
- B) Two target groups (blue + green) behind one production listener (and optionally a test listener). The canary step modifies the production listener to forward a slice (e.g., 10%) to the green target group and the rest to blue.
- C) One target group per task; the canary creates new ones.
- D) Three target groups; the canary rotates among them.

---

**Q6.** Your ECS service is configured with the default (`ECS`) deployment controller, not `CODE_DEPLOY`. You attach a CodeDeploy blue/green deployment group. What happens?

- A) Blue/green works fine; the controller does not matter.
- B) It does not work — CodeDeploy blue/green for ECS requires the service to use the `CODE_DEPLOY` deployment controller. With the default `ECS` controller you get an in-place rolling deploy, not blue/green.
- C) It silently does all-at-once instead of canary.
- D) ECS automatically switches the controller for you.

---

**Q7.** Your canary alarm uses `treatMissingData: BREACHING` on the green target group's 5XX metric. The deploy starts. What goes wrong?

- A) Nothing — `BREACHING` is the safe default.
- B) A brand-new green target group has no traffic yet, so the 5XX metric reports *no data*. With `BREACHING`, missing data is treated as in-alarm, so the deploy rolls back immediately — a false rollback — before the canary ever takes traffic. Use `NOT_BREACHING`.
- C) The alarm never fires regardless of errors.
- D) The deploy promotes to 100% instantly.

---

**Q8.** You configure an ECS deploy with `Canary10Percent5Minutes` and a 5XX alarm whose evaluation window is 10 minutes (1-minute period, 10 evaluation periods). What is the bug?

- A) No bug; longer alarm windows are more reliable.
- B) The bake window (5 min) is shorter than the alarm's reaction time (~10 min). The canary will promote to 100% before the alarm can possibly fire, so a bad deploy is never caught during the canary. The bake window must exceed the alarm's reaction time, with margin.
- C) `Canary10Percent5Minutes` does not support alarms.
- D) The alarm must use a 5-second period.

---

**Q9.** How does Lambda traffic shifting implement a canary, mechanically?

- A) It launches a second function and load-balances between them.
- B) It uses a weighted alias: the alias (e.g., `prod`) points, say, 90% at the old version and 10% at the new version, then shifts the weight to 0/100 over the bake window. Versions are immutable; the alias weight is the canary.
- C) It modifies an ALB listener like ECS does.
- D) It reroutes via API Gateway stages.

---

**Q10.** What is the difference between a CodeDeploy Lambda *pre-traffic hook* and the rollback *alarm*, and why want both?

- A) They are the same thing with different names.
- B) The pre-traffic hook is a Lambda CodeDeploy invokes *before* shifting any traffic — it actively probes the new version and can abort the deploy before any user is exposed. The alarm watches *production traffic* during the bake window and rolls back *after* the canary has taken a slice. The hook catches "broken at startup"; the alarm catches "breaks under real traffic." You want both layers.
- C) The hook runs after the alarm; they are sequential.
- D) The alarm probes the function and the hook watches metrics.

---

**Q11.** An ECR repository has mutable tags. A deploy references `v1.4.2`. Why is this a supply-chain risk, and what is the fix?

- A) No risk; mutable tags are convenient.
- B) With mutable tags, `v1.4.2` can be overwritten to point at different image bytes with no record that the tag moved — a running task pulls different code on its next restart. Set the repository to `IMMUTABLE` tags and deploy by Git SHA (or by digest), so a tag maps to exactly one image forever.
- C) Mutable tags cost more to store.
- D) The fix is to disable scan-on-push.

---

**Q12.** In a GitHub Actions OIDC trust policy, the `sub` condition is `repo:my-org/*` (a wildcard over all repos in the org). What is the risk?

- A) None; it is scoped to your org.
- B) *Any* repository in `my-org` — including a repo a low-trust contributor can push to, or a newly created repo — can assume the deploy role. Scope `sub` to the specific repo and branch (`repo:my-org/my-repo:ref:refs/heads/main`) or to a protected environment (`repo:my-org/my-repo:environment:prod`). A too-broad `sub` is the most common OIDC misconfiguration.
- C) The wildcard breaks the audience check.
- D) GitHub rejects wildcards in `sub`.

---

**Q13.** Your GitHub Actions workflow fails at the `configure-aws-credentials` step with "Could not load credentials." You have the role ARN correct and the trust policy looks right. What is the most likely missing piece?

- A) The runner needs a stored `AWS_SECRET_ACCESS_KEY`.
- B) The workflow (or job) is missing `permissions: id-token: write`. Without it, GitHub does not mint the OIDC token, so there is no token to exchange — even with a perfect role and trust policy.
- C) You must hardcode GitHub's OIDC thumbprint in the IAM provider.
- D) The region is wrong.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — The asymmetry is that the prod role is scoped to data while the pipeline role controls code and identity, and can `iam:PassRole` to grant a deployed workload elevated privileges. (A) is false — neither role has admin by default in a well-run account; the danger is structural, not a default. See Lecture 1, §1.1.

2. **B** — This is poisoned-pipeline-execution (PPE), the canonical CI/CD supply-chain attack. Build untrusted input (PRs) with a low-privilege role; never make the deploy role's credentials available to a PR build. Lecture 1, §1.1.

3. **B** — A bare `iam:PassRole` on `*` lets the pipeline attach any role (including admin) to a new task — front-door privilege escalation. Scope to the specific role ARNs and add the `iam:PassedToService` condition. Lecture 1, §1.2.

4. **B** — A classic PAT is a long-lived, broad-scope bearer credential with no auto-expiry, leakable by any over-scoped reader; CodeConnections keeps no token in your account, uses a revocable GitHub App, and gates use via `codeconnections:UseConnection`. Lecture 1, §1.4.

5. **B** — Two target groups (blue + green), one production listener (plus an optional test listener). The canary modifies the production listener to forward a slice to green. Lecture 2, §2.2.

6. **B** — CodeDeploy blue/green for ECS requires the `CODE_DEPLOY` deployment controller. With the default `ECS` controller you get a rolling in-place deploy. Lecture 2, §2.2; Exercise 2.

7. **B** — A new green target group reports no data; `BREACHING` treats missing data as in-alarm and triggers an immediate false rollback. Use `NOT_BREACHING`. Lecture 2, §2.3.

8. **B** — The bake window must exceed the alarm's reaction time. A 5-minute canary with a ~10-minute alarm window promotes before the alarm can fire, so bad deploys slip through. Match the window to the alarm reaction time with margin. Lecture 2, §2.3.

9. **B** — Lambda canary = a weighted alias. The alias points X% at old / Y% at new and shifts the weight over the bake window. Versions are immutable; the alias weight is the mechanism. Lecture 2, §2.4.

10. **B** — The pre-traffic hook probes the new version *before* any traffic (can abort before exposure); the alarm watches production traffic *during* the bake (rolls back after the canary slice). Hook catches startup breakage; alarm catches under-traffic breakage. Want both. Lecture 2, §2.4; Exercise 3.

11. **B** — Mutable tags can be silently overwritten to different bytes; a restart pulls different code with no audit trail. Use `IMMUTABLE` tags and deploy by SHA/digest. Lecture 1, §1.6.

12. **B** — A wildcard `sub` lets any repo in the org (including low-trust or new ones) assume the role. Scope to repo + branch or repo + environment. Too-broad `sub` is the most common OIDC misconfiguration. Lecture 2, §2.6; Challenge 1.

13. **B** — Without `permissions: id-token: write`, GitHub does not mint the OIDC token, so the exchange has nothing to present. (C) is a stale-guide trap — AWS no longer requires a hardcoded GitHub OIDC thumbprint. Lecture 2, §2.6; Challenge 1.

</details>

---

If you scored under 9, re-read the lectures for the questions you missed — especially the IAM scoping (Q1–Q4) and the blue/green mechanism (Q5–Q8), which the exercises and mini-project lean on hardest. If you scored 11+, you're ready for the [homework](./homework.md) and the mini-project.
