# Week 9 Homework

Six practice problems that revisit the week's topics. The full set should take about **5.5 hours**. Work in your Week 9 Git repository so each problem produces at least one commit you can point to later.

Each problem includes a **problem statement**, **acceptance criteria**, a **hint**, and an **estimated time**.

---

## Problem 1 — Write the access-pattern table for a new domain

**Problem statement.** Pick a domain that is *not* the SaaS one — a ride-sharing app, a ticketing system, a recipe site, whatever you like — with at least four entity types and one many-to-many relationship. Enumerate **at least ten access patterns** (the operations the app performs, reads and writes). Then design a single-table `PK`/`SK` schema plus at most two overloaded GSIs that serve every pattern with a single `GetItem` or `Query`. Produce the access-pattern → key-condition table.

**Acceptance criteria.**

- `notes/access-patterns.md` lists ≥ 10 access patterns and the entity types.
- Each pattern maps to an exact key condition on the base table or a GSI — no `Scan`.
- At least one pattern uses `begins_with` on the sort key; at least one is served by a GSI.
- The many-to-many relationship is modeled (adjacency list or a membership item), and you note how.
- A one-paragraph reflection on which pattern was hardest to model and why.

**Hint.** Group patterns that fetch related items together — they must share a partition. The many-to-many is usually two membership items (one per direction) or one GSI that flips the key.

**Estimated time.** 60 minutes.

---

## Problem 2 — Do the capacity math by hand

**Problem statement.** Compute, by hand (show the arithmetic), the capacity cost of each of the following. Then check three of them against a real call (use `ReturnConsumedCapacity="TOTAL"` against `dynamodb-local`).

1. Writing a 2.5 KB item (normal write).
2. Writing the same 2.5 KB item in a `TransactWriteItems`.
3. A strongly consistent read of an 8 KB item.
4. An eventually consistent read of an 8 KB item.
5. A `Query` returning 30 items of 1.5 KB each, eventually consistent.
6. The minimum number of write shards needed to sustain 3,400 writes/second of 1 KB items on a single logical key.

**Acceptance criteria.**

- `notes/capacity-math.md` shows each answer with the rounding step explicit.
- Three answers are verified against a real `ConsumedCapacity` value, pasted in.
- Problem 6's answer is `ceil(3400/1000) = 4` shards (and you explain why you might round to 5 for headroom).

**Hint.** WCU rounds up per 1 KB; RCU rounds up per 4 KB; eventual reads are half; transactions are 2×; a `Query` is billed on total bytes read, not per item.

**Estimated time.** 45 minutes.

---

## Problem 3 — Build a sparse-index worklist

**Problem statement.** On the SaaS table from exercise 1, add a sparse `GSI2` that models a "comments pending moderation" queue. Flagging a comment sets `GSI2PK = REVIEW#pending` and `GSI2SK = <timestamp>`; clearing it `REMOVE`s those attributes. Write `flag_comment`, `clear_review`, and `list_pending(limit)` (oldest first). Prove that `list_pending` reads *only* flagged comments — seed 100 comments, flag 3, and show the `Query` returns 3 items at low RCU regardless of the 100.

**Acceptance criteria.**

- `GSI2` exists; `flag_comment` / `clear_review` / `list_pending` are implemented.
- `list_pending` is a single `Query` on `GSI2PK=REVIEW#pending`, oldest first, with `0 Scans`.
- A test seeds 100 comments, flags 3, and asserts `list_pending` returns exactly 3 items.
- `clear_review` removes an item from the queue (asserted) by `REMOVE`-ing the GSI2 key.

**Hint.** The index is sparse because unflagged comments never carry `GSI2PK`. `REMOVE GSI2PK, GSI2SK` drops an item out of the index entirely.

**Estimated time.** 60 minutes.

---

## Problem 4 — Optimistic concurrency under contention

**Problem statement.** Implement `update_project_name(project_id, new_name, expected_version)` using a `version` attribute and `ConditionExpression="version = :expected"`. Then write a test that fires two concurrent updates with the *same* `expected_version` and asserts that exactly one succeeds and the other raises `ConditionalCheckFailedException`. Add a retry loop (read-modify-write) that makes the loser eventually succeed.

**Acceptance criteria.**

- `update_project_name` increments `version` and is conditional on the expected version.
- A concurrency test shows exactly one of two simultaneous same-version updates succeeds.
- The retry loop re-reads the current version and retries, and the test shows the loser eventually applies its update.
- `notes/optimistic-concurrency.md` explains in 100 words why this is preferable to a lock.

**Hint.** `from concurrent.futures import ThreadPoolExecutor` to fire the two updates. Catch `ClientError` and check `e.response["Error"]["Code"] == "ConditionalCheckFailedException"`.

**Estimated time.** 60 minutes.

---

## Problem 5 — Streams → Lambda: derive the audit log from the data

**Problem statement.** Wire (against LocalStack or real AWS) a DynamoDB Streams → Lambda fan-out for the SaaS table. The Lambda writes an immutable audit entry for every INSERT/MODIFY/REMOVE, *except* for AuditEntry items themselves (guard against the infinite loop). It must distinguish a TTL-expiry REMOVE from an application delete and record them with different `action` values. Implement `reportBatchItemFailures` and prove a poison record does not block the batch.

**Acceptance criteria.**

- The Lambda is wired via an event-source mapping with `reportBatchItemFailures: true`, `bisectBatchOnError: true`, and a set `batchSize`.
- A mutation to the table produces a matching audit entry (asserted by reading the audit partition after).
- AuditEntry items do not produce audit entries (no infinite loop).
- A TTL-expiry REMOVE is recorded with a distinct `action` (e.g. `ttl.expire`) vs an application delete (`item.delete`); the handler checks `userIdentity.principalId == "dynamodb.amazonaws.com"`.
- A test injects one record that raises and confirms the other records in the batch still commit (their `SequenceNumber`s are not in `batchItemFailures`).

**Hint.** Use `boto3.dynamodb.types.TypeDeserializer` to decode `NewImage`/`OldImage`. Return `{"batchItemFailures": [{"itemIdentifier": <SequenceNumber>}]}` for failed records only.

**Estimated time.** 75 minutes.

---

## Problem 6 — Comparator design note

**Problem statement.** Read the relevant sections of the ScyllaDB, Cassandra, and FoundationDB docs (links in `resources.md`) and the DynamoDB USENIX ATC 2022 paper's abstract and adaptive-capacity section. Write a 300-word design note answering: for the SaaS single-table store, *when* would you migrate off DynamoDB, and *to which* of the three comparators, and what would the migration cost you (operationally and in modeling effort)? Name a concrete threshold (traffic, cost, or requirement) that would trigger the move.

**Acceptance criteria.**

- `notes/comparators.md` is 280–320 words and cites at least two of the linked sources.
- It names a concrete migration trigger (e.g., "sustained spend > $X/mo at >Y% steady utilization where Scylla Alternator's throughput-per-node math wins").
- It correctly distinguishes the three: Scylla = DynamoDB-API-compatible, self-operated, higher throughput-per-node; Cassandra = same modeling philosophy, different API, self-operated; FoundationDB = different (transactional ordered KV) model for when you need cross-key serializable transactions.
- It states what the migration costs (you now run a cluster; modeling effort depends on API compatibility).

**Hint.** The honest answer for most teams is "you don't migrate" — DynamoDB's operational story wins until you are at a scale or price point where running infrastructure pays for itself. Make the threshold concrete.

**Estimated time.** 40 minutes.

---

## Submission

Push the entire `notes/` directory and any code to your Week 9 Git repository. The instructor reviews by:

1. Reading each note in `notes/`.
2. Re-running any code (the sparse-index worklist, the concurrency test, the Streams fan-out) and confirming the assertions pass.
3. Cross-checking the capacity math by hand and against the pasted `ConsumedCapacity` values.

A submission whose `notes/` are present, whose code runs, and whose capacity math is correct is a pass. The most common review-fail is a `Scan` hiding in an access pattern that "should" be a `Query` — grep your own code for it before submitting.

If anything is unclear, post the question in the Week 9 channel before the homework deadline.

---

**References**

- DynamoDB — partition-key best practices: <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html>
- DynamoDB — secondary-index best practices: <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-indexes.html>
- DynamoDB — capacity modes and RCU/WCU: <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWriteCapacityMode.html>
- DynamoDB — Streams: <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html>
- Alex DeBrie — single-table design: <https://www.alexdebrie.com/posts/dynamodb-single-table/>
