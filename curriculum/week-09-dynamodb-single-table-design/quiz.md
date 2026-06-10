# Week 9 — Quiz

Thirteen questions. Take it with your lecture notes closed. Aim for 11/13 before moving to Week 10. Answer key at the bottom — don't peek.

---

**Q1.** What is the correct order of design steps in single-table DynamoDB modeling?

- A) Model the entities and their relationships, then derive the queries the application will need.
- B) Write down the access patterns, then derive a key schema that serves each one with a single operation.
- C) Normalize to third normal form, then denormalize the hot paths.
- D) Create one table per entity, then add GSIs to join across them.

---

**Q2.** A single physical DynamoDB partition can serve at most:

- A) 1,000 RCU and 3,000 WCU per second.
- B) 3,000 RCU and 1,000 WCU per second, up to 10 GB of data.
- C) Unlimited RCU/WCU as long as the table is in on-demand mode.
- D) 40,000 RCU and 40,000 WCU per second (the table default).

---

**Q3.** You write a 6 KB item in a normal (non-transactional) write. How many WCU does it cost?

- A) 6 WCU (round up to the next KB).
- B) 2 WCU (round up to the next 4 KB).
- C) 12 WCU (6 KB × 2 for the index).
- D) 1 WCU (writes are always 1 WCU).

---

**Q4.** An *eventually consistent* read of a 10 KB item costs how many RCU?

- A) 3 RCU (ceil(10/4) blocks).
- B) 1.5 RCU (ceil(10/4) = 3 blocks × 0.5 for eventual consistency).
- C) 10 RCU (1 per KB).
- D) 0.5 RCU (eventual reads are always 0.5).

---

**Q5.** Your table is provisioned for 40,000 WCU and sits at 4% utilization table-wide, yet writes to one partition key are throttling. What is happening, and what is the fix?

- A) The table is under-provisioned; raise it to 80,000 WCU.
- B) All writes hash to one partition, which is pinned at its 1,000 WCU per-partition ceiling. Adaptive capacity cannot split a single key value. Write-shard the key across N partitions.
- C) DynamoDB is broken; open a support ticket.
- D) Switch to on-demand mode, which has no per-partition limit.

---

**Q6.** Which statement about Global Secondary Indexes (GSIs) is **true**?

- A) GSIs can be read strongly consistently.
- B) GSIs must be created at table-creation time and can never be added later.
- C) A GSI is eventually consistent, has its own capacity, and a throttled GSI can back-pressure writes to the base table.
- D) A GSI shares the base table's partition key.

---

**Q7.** Why are Local Secondary Indexes (LSIs) almost always the wrong choice in 2026?

- A) They are slower than GSIs in every case.
- B) They must be created at table-creation time, can never be added or removed, and bind the item collection to a 10 GB limit — none of which a GSI does.
- C) They cost more than GSIs per read.
- D) They cannot be queried with `begins_with`.

---

**Q8.** What makes a GSI *sparse*, and what is it good for?

- A) Setting the GSI's projection to `KEYS_ONLY`; it is good for saving storage.
- B) Writing the GSI's key attribute onto only *some* items, so the index contains only those items; it is good for "find the few items in state X" worklists and status filters with no scan.
- C) Enabling TTL on the index; it is good for auto-expiring stale rows.
- D) Provisioning the GSI with low capacity; it is good for cost control.

---

**Q9.** You shard a write-hot key with a *random* suffix `0..9`. What is the read-side consequence?

- A) None; reads are unaffected.
- B) To read all items for the logical key you must `Query` all 10 shards (scatter) and merge the results (gather) — one read becomes ten.
- C) Reads become strongly consistent automatically.
- D) The GSI is required to read sharded data.

---

**Q10.** A TTL attribute must hold:

- A) An ISO-8601 timestamp string.
- B) A Number of epoch *seconds* (not milliseconds); the item is deleted within ~48 hours of that time, for free, and the delete flows through Streams.
- C) A boolean `expired` flag DynamoDB toggles.
- D) The number of seconds to live, counted from item creation.

---

**Q11.** You need to write a project row into two partitions (the org partition and the project's own partition) such that either both writes succeed or neither does, and a retried call must not double-apply. Which API and option?

- A) Two separate `PutItem` calls in a `try/except`.
- B) `BatchWriteItem` with both items.
- C) `TransactWriteItems` with both `Put`s and a `ClientRequestToken` for idempotency.
- D) `UpdateItem` with a `ConditionExpression`.

---

**Q12.** For a constant 500-WCU-24/7 workload, which billing mode is cheaper and roughly by how much?

- A) On-demand, because it scales to zero.
- B) Provisioned (with autoscaling), by roughly 7× — and ~15× once reserved capacity is added — because high, steady utilization is exactly what provisioned is priced for.
- C) They cost the same; the mode only affects management overhead.
- D) On-demand, by roughly 7×, because per-request pricing is always cheaper.

---

**Q13.** Which open-source comparator speaks the DynamoDB API directly (so the same single-table model runs against it), and what is the trade you make by choosing it?

- A) Apache Cassandra; the trade is weaker consistency.
- B) FoundationDB; the trade is you lose transactions.
- C) ScyllaDB via its Alternator mode; the trade is you now operate the cluster yourself in exchange for higher throughput-per-node and escaping DynamoDB's pricing at extreme scale.
- D) Redis; the trade is durability.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **B** — Single-table design is access-pattern-first. You enumerate the queries, then derive a key schema where each is one operation. The entities are an implementation detail; the patterns are the spec. (A) is the relational reflex and is wrong for DynamoDB.

2. **B** — 3,000 RCU, 1,000 WCU, and 10 GB per physical partition. This ceiling is the source of every hot-partition story. Note (A) inverts the RCU/WCU figures — a common trap.

3. **A** — WCU rounds up per 1 KB. A 6 KB write is 6 WCU. (B) is the *RCU* rounding (per 4 KB). A *transactional* 6 KB write would be 12 WCU (2×), but the question says non-transactional.

4. **B** — RCU rounds up per 4 KB: `ceil(10/4) = 3` blocks. A strongly consistent read would be 3 RCU; an eventually consistent read is half: `3 × 0.5 = 1.5 RCU`.

5. **B** — Classic hot partition. The table has spare capacity but one partition key is pinned at its per-partition ceiling. Adaptive capacity cannot split a single key value across partitions, so the fix is write-sharding. (D) is wrong: on-demand has the same per-partition ceiling — it throttles too.

6. **C** — GSIs are eventually consistent, have independent capacity, and a throttled GSI back-pressures the base table (a real outage source). (A) is false (GSIs can't be strongly consistent), (B) describes LSIs, (D) describes LSIs.

7. **B** — LSIs are create-time-only, immutable, and impose the 10 GB item-collection limit. Their one advantage (strong consistency on an alternate sort key) rarely justifies those constraints; use a GSI.

8. **B** — A sparse index contains only items that carry its key attribute. Writing the key on only some items (and `REMOVE`-ing it to drop them out) gives you a self-cleaning worklist/status-filter queried with no scan and no cost for the items not in the index.

9. **B** — Random sharding lifts the write ceiling to N× but forces a scatter-gather on reads: you `Query` all N shards and merge. This is why you shard write-heavy, rarely-fully-read keys (audit logs) and not keys you read in full constantly.

10. **B** — TTL is a Number of epoch *seconds*. Milliseconds is the classic bug (your items would "expire" ~50,000 years out). Deletion is best-effort within ~48h, free, and flows through Streams as a REMOVE with `userIdentity.principalId == dynamodb.amazonaws.com`.

11. **C** — `TransactWriteItems` gives all-or-nothing across up to 100 items; the `ClientRequestToken` makes a retried call idempotent. `BatchWriteItem` (B) is *not* atomic — individual writes can fail independently.

12. **B** — Provisioned-with-autoscaling wins ~7× on steady high-utilization load (`~$237/mo` vs `~$1,642/mo` for WCU alone), and reserved capacity pushes it to ~15×. On-demand wins on spiky/idle load, not steady load.

13. **C** — ScyllaDB's Alternator mode speaks the DynamoDB API, so your single-table model ports over. The trade: you operate the cluster (nodes, repair, compaction) in exchange for far higher throughput-per-node and escaping DynamoDB's per-request pricing at extreme scale. Cassandra shares the *modeling* philosophy but not the API; FoundationDB is a different (transactional ordered KV) model entirely.

</details>

---

If you scored under 9, re-read the lectures for the questions you missed — especially the capacity math (Q3, Q4, Q12) and the index trade-offs (Q6, Q7, Q8). If you scored 12 or 13, you're ready for the [homework](./homework.md) and the mini-project.
