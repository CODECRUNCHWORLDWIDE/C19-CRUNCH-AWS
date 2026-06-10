# Week 9 — DynamoDB & Single-Table Design

Welcome to the hardest mental model in the entire AWS catalog. Not the most code, not the most services — the hardest *model*. Single-table DynamoDB design is the thing that takes a relational engineer who is fluent in joins, normalization, and `EXPLAIN ANALYZE` and makes them feel like a beginner again for about three days. Then it clicks, and they never look at an access pattern the same way again.

This week we build the transactional data store for the multi-tenant SaaS you sketched in Week 8. Users, organizations, projects, comments, and an immutable audit log — all in **one** DynamoDB table. We will partition and sort it so that every access pattern your application needs is served by a single `Query` or `GetItem`, with no scans, no joins, and no second round trip. Then we will break it on purpose: hammer a single partition until it throttles, watch the `ProvisionedThroughputExceededException` (or the on-demand-mode throttle) light up CloudWatch, and fix it two ways — a GSI for the reverse lookup, and write-sharding to spread the hot partition. By Friday you will have a table that serves every pattern, proves its own hot-partition mitigation, fans out via Streams → Lambda, and ships with a cost report comparing on-demand against provisioned-with-autoscaling at three load profiles.

The framing this week is **Rick Houlihan was right**. Houlihan is the engineer who, while at AWS, gave a series of re:Invent talks (the "Advanced Design Patterns for DynamoDB" sessions, DAT401/DAT403, 2018–2020) that converted a generation of engineers from "one table per entity, just like SQL" to "one table, modeled around access patterns." The single-table approach is counterintuitive, frequently argued-about, and — for the OLTP workloads DynamoDB is built for — correct. We teach it the way he drew it: access patterns first, schema second, and the schema is *derived* from the patterns, never the other way around.

We assume you finished Week 8 (RDS/Aurora) and that you have an instinct for when a relational store is the right call. DynamoDB is not a replacement for Postgres. It is the right tool when you know your access patterns up front, you need single-digit-millisecond latency at any scale, and you are willing to trade ad-hoc query flexibility for predictable performance and cost. This week is about earning that trade deliberately.

## Learning objectives

By the end of this week, you will be able to:

- **Derive** a DynamoDB schema from a written list of access patterns, not the other way around — the single-table discipline.
- **Design** composite primary keys (partition key + sort key) and overloaded keys that pack multiple entity types into one table.
- **Distinguish** Global Secondary Indexes from Local Secondary Indexes and choose the right one (and know why LSIs are almost always the wrong one in 2026).
- **Build** sparse indexes that project only the items carrying a given attribute, and use them to serve "find all the X that are in state Y" queries cheaply.
- **Diagnose** a hot partition from CloudWatch `ThrottledRequests` and `ConsumedWriteCapacityUnits` metrics, and explain *why* DynamoDB throttled even though the table-level capacity was not exhausted.
- **Apply** write-sharding (calculated suffixes) to spread a hot partition key across N physical partitions and confirm the throttling disappears.
- **Implement** conditional writes, optimistic concurrency with a version attribute, and `TransactWriteItems` for all-or-nothing multi-item updates.
- **Wire** DynamoDB Streams to a Lambda fan-out that maintains a denormalized projection and writes the audit log.
- **Compute** RCU/WCU math by hand and decide between on-demand and provisioned-with-autoscaling for a given load profile, with the dollar figures to back it up.
- **Compare** DynamoDB against its open-source comparators — ScyllaDB, Cassandra, FoundationDB — and articulate when you would reach for each.

## Prerequisites

This week assumes you have completed **C19 Weeks 1–8** (IAM, VPC, compute, S3, CDK, RDS/Aurora) and the course-wide prerequisites (C1 Python, C15 DevOps). Specifically:

- You can deploy a CDK stack (`cdk deploy`) and read the synthesized CloudFormation. We define the table in CDK this week; CloudFormation and OpenTofu equivalents are shown for comparison.
- You can write IAM policies. The Streams → Lambda path needs a least-privilege execution role, and we will not hand it to you.
- You have the **Week 8** SaaS domain in your head: the entities (User, Organization, Project, Comment, AuditEvent) and roughly how they relate. We reuse them verbatim. If you skipped Week 8, read its `mini-project/README.md` first.
- You have `awscli v2`, the AWS CDK v2 toolkit (`npm i -g aws-cdk`), Node 20+, Python 3.12+, and either an AWS account on free tier **or** `dynamodb-local` / LocalStack for offline iteration. Most of this week fits inside the DynamoDB free tier; the load tests are the only line item to watch.

You do **not** need prior DynamoDB experience. We start at the data model. If you have used DynamoDB the "one table per entity" way, you will need to unlearn that habit this week, and we will flag exactly where.

## Topics covered

- The DynamoDB data model: tables, items, attributes, the partition key (hash key), the sort key (range key), and the composite primary key.
- Partitions: how DynamoDB hashes the partition key onto physical storage nodes, the 3,000 RCU / 1,000 WCU per-partition ceiling, and why that ceiling is the source of every hot-partition story.
- Single-table design: one table per service, key overloading (`PK`/`SK` generic attribute names), the entity-prefix convention (`ORG#`, `USER#`, `PROJ#`), and adjacency-list modeling for relationships.
- Access-pattern-first modeling: writing the patterns down, building the access-pattern → key-condition table, and deriving the schema from it.
- Global Secondary Indexes (GSIs): independent partition/sort keys, eventual consistency, separate capacity, projection types (`KEYS_ONLY`, `INCLUDE`, `ALL`), and the GSI overloading trick (`GSI1PK`/`GSI1SK`).
- Local Secondary Indexes (LSIs): same partition key, alternate sort key, strong-consistency option, the 10 GB item-collection limit, and why you almost never want one.
- Sparse indexes: indexing only items that carry the index's key attribute, and using that to model queues, "needs-review" lists, and status filters cheaply.
- Write-sharding: calculated and random shard suffixes to defeat hot partitions, the read-side scatter-gather cost, and when sharding is overkill.
- TTL: the `Number` epoch-seconds attribute, the up-to-48-hour deletion window, and TTL deletes flowing through Streams.
- DynamoDB Streams: `NEW_AND_OLD_IMAGES`, shard-per-partition semantics, and the Lambda event-source mapping (batch size, bisect-on-error, parallelization factor, filter criteria).
- Conditional writes: `ConditionExpression`, `attribute_not_exists`, optimistic concurrency with a `version` attribute, and idempotent writes.
- Transactions: `TransactWriteItems` (up to 100 items, all-or-nothing, idempotency token), `TransactGetItems`, and the 2× WCU cost.
- Capacity: RCU/WCU definitions and math, eventually-consistent vs strongly-consistent read cost, on-demand mode, provisioned mode with Application Auto Scaling, and reserved capacity.
- Global Tables (multi-region, active-active, last-writer-wins) and DAX (the write-through microsecond cache) — what they cost and when they earn it.
- Open-source comparators: ScyllaDB (Cassandra-compatible, C++, shard-per-core), Apache Cassandra (the wide-column ancestor), and FoundationDB (the ordered KV store DynamoDB-likes are sometimes built on).

## Weekly schedule

The schedule below adds up to approximately **36 hours**. Treat it as a target, not a contract.

| Day       | Focus                                               | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|-----------------------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | Data model, partitions, single-table, access-pattern derivation |    2h    |    1.5h   |     0h     |    0.5h   |   1h     |     0h       |    0.5h    |     5.5h    |
| Tuesday   | GSIs vs LSIs, sparse indexes, key overloading       |    2h    |    2h     |     0.5h   |    0.5h   |   1h     |     0h       |    0h      |     6h      |
| Wednesday | Hot partitions, write-sharding, RCU/WCU math        |    1h    |    2h     |     1h     |    0.5h   |   1h     |     0h       |    0.5h    |     6h      |
| Thursday  | Streams → Lambda, conditional writes, transactions  |    1h    |    1h     |     0.5h   |    0.5h   |   1h     |     2h       |    0.5h    |     6.5h    |
| Friday    | On-demand vs provisioned cost; mini-project work     |    0h    |    0.5h   |     0.5h   |    0.5h   |   1h     |     3h       |    0h      |     5.5h    |
| Saturday  | Mini-project deep work (Streams fan-out, cost report) |    0h    |    0h     |     0h     |    0h     |   0.5h   |     3h       |    0h      |     3.5h    |
| Sunday    | Quiz, review, polish                                 |    0h    |    0h     |     0h     |    1h     |   0h     |     0.5h     |    0.5h    |     2h      |
| **Total** |                                                     | **6h**   | **7.5h**  | **3h**     | **3.5h**  | **5.5h** | **11.5h**    | **2h**     | **39h**     |

(The total runs a little hot at 39h because the mini-project is the capstone's DynamoDB store and we want you to over-invest here. Trim self-study and Saturday homework if you are tight on time.)

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview (you are here) |
| [resources.md](./resources.md) | Curated AWS docs, the Houlihan talks, the DynamoDB Book, and the comparator projects |
| [lecture-notes/01-rick-houlihan-was-right-single-table-design.md](./lecture-notes/01-rick-houlihan-was-right-single-table-design.md) | The single-table design for the multi-tenant CRUD app, drawn live: access patterns → keys → schema |
| [lecture-notes/02-defeating-the-hot-partition.md](./lecture-notes/02-defeating-the-hot-partition.md) | Write-sharding, sparse indexes, and capacity-unit math; on-demand vs provisioned |
| [exercises/README.md](./exercises/README.md) | Index of the three exercises |
| [exercises/exercise-01-single-table-saas.md](./exercises/exercise-01-single-table-saas.md) | Implement the single-table design for the multi-tenant SaaS CRUD app |
| [exercises/exercise-02-hot-partition-and-gsi.py](./exercises/exercise-02-hot-partition-and-gsi.py) | Hammer one partition key, observe throttling, add a GSI for a reverse lookup |
| [exercises/exercise-03-write-sharding.py](./exercises/exercise-03-write-sharding.py) | Add write-sharding to defeat the hot partition and confirm throttling disappears |
| [challenges/README.md](./challenges/README.md) | Index of weekly challenges |
| [challenges/challenge-01-on-demand-vs-provisioned-cost.md](./challenges/challenge-01-on-demand-vs-provisioned-cost.md) | Switch on-demand → provisioned with autoscaling; measure the cost delta at three load profiles |
| [quiz.md](./quiz.md) | 13 questions with an answer key |
| [homework.md](./homework.md) | Six practice problems with a rubric |
| [mini-project/README.md](./mini-project/README.md) | The multi-tenant single-table store — the capstone's DynamoDB layer |

## The "one query, zero scans" promise

C19 uses a recurring marker in every DynamoDB exercise that ends in working access patterns:

```
Access pattern served · 1 Query · 0 Scans · 2.5 RCU · 4.1 ms
```

If serving an access pattern requires a `Scan`, a client-side filter over a large result set, or more than one round trip, **you have not finished modeling it**. The entire point of single-table design is that every read your application performs is a `GetItem` or a `Query` against a key condition. A `Scan` in your hot path is a design bug, not a performance bug. We treat it as a failing test.

## Where this week fits

This is the third stop in Phase 3 (Data, Events & AI). It compounds directly on:

- **Week 8** — the SaaS domain and the relational comparison. We reuse the same five entities and ask, for each, "would you put this in Postgres or DynamoDB, and why?"
- **Week 10** — the event-driven pipeline consumes this table's Streams. The fan-out you wire on Thursday is the upstream of next week's EventBridge work.
- **Week 13** — multi-region DR turns this table into a Global Table. The keys and access patterns you choose this week determine whether that is a one-line change or a re-model.

The mini-project store is **the capstone's transactional data layer**. Build it like you will run it for a year, because in this course you will.

## Up next

Continue to **Week 10 — Event-Driven: SQS, SNS, EventBridge, Step Functions, Kinesis, MSK** once your mini-project table serves every access pattern, proves its hot-partition mitigation, and emits a Stream a Lambda consumes.

---

*If you find errors in this material, please open an issue or send a PR. Future learners will thank you.*
