# Week 13 Homework

Five problems that revisit and extend the week's topics. The full set should take about **5 hours**. Work in your Week 13 Git repository so each problem produces at least one commit you can point to later. Several problems produce numbers (RTO, RPO, the warm-standby premium) that belong in your cost report and your capstone — keep them.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — Read the key policy out loud, then break it

**Problem statement.** Below is a KMS key policy. Two things are wrong with it for a production CMK. Find both, explain why each is wrong, and write a corrected version.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Everything",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::111122223333:role/app-and-admin" },
      "Action": "kms:*",
      "Resource": "*"
    }
  ]
}
```

**Acceptance criteria.**

- A committed `notes/key-policy-review.md` naming **both** flaws: (1) there is no IAM-delegation (`:root` `kms:*`) statement, so *no IAM policy* in the account can grant on the key — only this one named role works; and (2) a single role both administers *and* uses the key (no admin/user separation), which is the KMS equivalent of `Resource: "*"` for blast radius.
- A corrected policy with three statements: an IAM-delegation statement, a key-administrators statement (manage, not use), and a key-users statement (use, not manage).
- Two sentences on why separating admin from usage limits blast radius.

**Hint.** Exercise 2's `key_policy()` function is a correct three-statement template. Lecture 1 §1.2 explains why the `:root` statement is a delegation, not a blanket grant.

**Estimated time.** 45 minutes.

---

## Problem 2 — Prove the cross-Region decrypt (and explain the DR consequence)

**Problem statement.** Using your Exercise-2 multi-Region key, write a short boto3 script (or extend the exercise) that encrypts a string with the **primary** key in `us-east-1` and decrypts the same ciphertext with the **replica** key in `us-west-2`. Then write two sentences explaining what would happen to S3 Cross-Region Replication if the key were *not* multi-Region.

**Acceptance criteria.**

- A committed `notes/cross-region-decrypt.py` (or a captured run log) showing the round-trip succeeds across Regions.
- A committed `notes/crr-consequence.md` stating that a Region-locked key would replicate the object but leave it **undecryptable** in the DR Region (the most common silent DR failure), and that the fix is `replicaKmsKeyId` pointing at a multi-Region replica.
- The script asserts the round-tripped plaintext equals the original.

**Hint.** Exercise 2 already does the round-trip; this problem is making you articulate the *DR consequence*, which is the load-bearing reason the multi-Region key exists. Lecture 2 §2.3 (S3 CRR) is the reference.

**Estimated time.** 45 minutes.

---

## Problem 3 — The finding-disposition table

**Problem statement.** From your Exercise-1 security baseline, produce a finding-disposition table covering every **Critical** and **High** finding across GuardDuty, Security Hub, Macie, and Inspector. For each, record the source, the finding, the severity, the disposition (FIXED or ACCEPTED), and the action taken or the reason for acceptance.

**Acceptance criteria.**

- A committed `notes/finding-disposition.md` with one row per Critical/High finding and no finding left without a disposition.
- At least one finding marked FIXED with the concrete remediation (turned on a control, deleted a bucket, would rebuild on a patched base).
- At least one finding marked ACCEPTED with a *defensible* reason (sample finding, lab-only image, not reachable in our usage) — not "ignored."
- A closing sentence on the difference between *suppressing* a finding (tuning known noise) and *ignoring* one (the thing that ends up in a breach report).

**Hint.** The template is in Exercise 1 Step 5. The senior nuance from Lecture 1 §1.4: Inspector tells you what is *vulnerable*, not what is *exploitable in your context* — triage with judgment, document the call, never silently ignore.

**Estimated time.** 1 hour.

---

## Problem 4 — Pick the posture, with a dollar figure

**Problem statement.** For your capstone, choose a DR posture (backup/restore, pilot light, warm standby, or active/active) and **defend it with numbers**. Using the pricing pages (cite the date you pulled them), produce:

1. The target RTO and RPO the capstone requires, stated as numbers and justified by the workload.
2. The **monthly cost** of your chosen posture's DR footprint (the warm-standby premium: Aurora secondary + replicated DynamoDB write units + second-Region S3 + any warm compute).
3. The monthly cost of the *next posture up* (faster recovery) and the *next posture down* (cheaper), so the choice is bracketed.
4. A one-paragraph justification: why the chosen posture is the **cheapest** one that meets the target RTO/RPO.

**Acceptance criteria.**

- A committed `notes/dr-posture.md` with all four items and the arithmetic shown.
- Prices cited with the date pulled.
- The posture choice is the *cheapest* that meets the stated RTO/RPO — not the fastest available (that would be waste) and not one that misses the target.
- The warm-standby premium is a real monthly dollar figure, not "some extra cost."

**Hint.** Lecture 2 §2.2 gives the cost-vs-recovery curve; §2.4 derives the capstone's likely warm-standby choice. The honest framing is "what RTO/RPO does this *actually* need, and what is the cheapest posture that meets it" — a reviewer calls active/active for an internal tool waste.

**Estimated time.** 1 hour.

---

## Problem 5 — Reflection: the cost of each nine

**Problem statement.** Write a 350–450 word reflection at `notes/week-13-reflection.md` answering:

1. Your Friday drill produced a measured RTO and RPO. Did either *miss* its target? If so, what is the cheapest change that would close the gap, and is it worth it? If not, do you believe the numbers — i.e. did you drill hard enough to trust them?
2. The week's managed services each have an open-source comparator (Falco/Wazuh for GuardDuty, Trivy/Grype for Inspector, Vault for Secrets Manager). Pick the *one* place in your stack where you'd most seriously consider the open-source alternative, and say what you'd gain and lose.
3. "RTO and RPO are numbers, not adjectives." Before this week, would your DR story have had numbers in it? What changed?
4. One thing this week didn't cover that you now want to learn (active-active write conflict resolution? automated failover orchestration? incident response playbooks?).

**Acceptance criteria.**

- File exists, 350–450 words, each numbered question in its own paragraph.
- Committed.

**Hint.** This is for *you*. The honest answer to Q1 (a tighter RTO means a more sensitive health check and more false-positive failovers; a tighter Aurora RPO means active-active write-forwarding at much higher cost) is exactly the senior nuance — every nine of recovery has a price, and knowing it is the skill.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 45 min |
| 2 | 45 min |
| 3 | 1 h 0 min |
| 4 | 1 h 0 min |
| 5 | 30 min |
| **Total** | **~4 h 0 min** |

*(The schedule budgets 5h for homework to leave slack for Problem 4's pricing research, which always takes longer than you think the first time you read a DR pricing page honestly.)*

---

## Rubric

Graded out of 20.

| Criterion | Points | What earns full marks |
|---|---:|---|
| **KMS correctness (P1, P2)** | 6 | Both key-policy flaws found and correctly explained; the corrected policy separates admin from users and includes the IAM delegation; the cross-Region decrypt round-trips and the CRR consequence is articulated. |
| **Security triage (P3)** | 4 | Every Critical/High has a disposition; FIXED items name the remediation; ACCEPTED items have defensible reasons; the suppress-vs-ignore distinction is drawn. |
| **DR reasoning with numbers (P4)** | 6 | Target RTO/RPO stated and justified; the chosen posture's monthly cost is a real figure with cited prices; the choice is the cheapest that meets the target, bracketed by the postures above and below. |
| **Reflection honesty (P5)** | 2 | Engages genuinely with the cost-of-each-nine trade-off and the missed-target nuance, not platitudes. |
| **Hygiene** | 2 | All commits present, files where specified, nothing left billing (no orphaned Aurora secondary, no DynamoDB replica). |

A pass is 14/20. Anything below means re-read Lecture 2's posture-and-cost frame and re-run Problem 4 with real pricing — that arithmetic, and the RTO/RPO numbers from your drill, are the week's load-bearing skill and the capstone's `DR` pillar depends on them.

When you've finished all five, push your repo and open the [mini-project](./mini-project/README.md) if you haven't already — it assembles this week's pieces into the capstone's Security and DR foundation.
