# Mini-Project — The Multi-Tenant Single-Table Store (the Capstone's DynamoDB Layer)

> Deliver the multi-tenant single-table design with **all access patterns served**, **hot-partition mitigation proven**, **Streams → Lambda fan-out wired**, and an **on-demand-vs-provisioned cost report**. This is the capstone's transactional data store. It compounds directly on the Week-8 mid-program SaaS design and is reused in Weeks 10 and 13. Build it like you will run it for a year, because in this course you will.

This is the week's capstone-grade deliverable. It assembles everything from both lectures and all three exercises into one production-shaped artifact: a CDK-deployed single table that serves every access pattern of the multi-tenant SaaS, a proven hot-partition mitigation, a Streams → Lambda fan-out that maintains a denormalized projection and writes the immutable audit log, and a cost report comparing billing modes. The capstone (Weeks 13–15) uses *this exact table* as its DynamoDB store, its Streams feed Week 10's EventBridge pipeline, and Week 13 promotes it to a Global Table. The keys you choose here determine whether those later weeks are one-line changes or full re-models, so model carefully.

**Estimated time:** ~11.5 hours (split across Thursday, Friday, Saturday in the suggested schedule). It is the single biggest time sink of the week, and intentionally so.

---

## What you will build

A CDK monorepo (TypeScript primary; the Stream-handler Lambda in Python) that deploys, from `cdk deploy --all`:

1. **One DynamoDB table**, `saas-single-table`, with `PK`/`SK` composite keys, an overloaded `GSI1` for reverse lookups, a sparse `GSI2` for a moderation/worklist queue, Streams enabled (`NEW_AND_OLD_IMAGES`), and a TTL attribute. Modeled around the twelve access patterns from Lecture 1.
2. **A data-access library** (`packages/store/`) in TypeScript exposing one method per access pattern, every read a single `GetItem` or `Query`, key composition centralized in one module. This is the same surface as exercise 1, hardened: conditional writes everywhere, optimistic concurrency on mutable entities, transactions for the duplicated project row.
3. **A Streams → Lambda fan-out** (`packages/fanout/`, Python) that consumes every change and:
   - Writes the **immutable audit log** entry for the change (so the audit log is a side effect of the data, not something handlers must remember to call).
   - Maintains a **denormalized projection** — a per-org "activity feed" item updated on every project/comment change so the UI's dashboard is a single `Query`.
   - Reports **partial batch failures** so a poison record does not block the shard.
4. **Hot-partition mitigation** for the audit log: write-sharded across N partitions, with a documented N derived from the capacity math, and a load test that *proves* the throttle disappears (the exercise-3 pattern, run against your table).
5. **A cost report** (`docs/cost-report.md`) from Challenge 1, recommending a billing mode per load profile.
6. **Per-tenant IAM isolation:** the fan-out Lambda's execution role and a sample per-tenant read role use a `dynamodb:LeadingKeys` condition so a principal cannot read another tenant's partition.

You ship **one CDK app** with these stacks/packages:

- `lib/table-stack.ts` — the table, GSIs, Streams, TTL, billing mode.
- `lib/fanout-stack.ts` — the Stream-consumer Lambda, its event-source mapping with the production knobs, and its least-privilege role.
- `packages/store/` — the TypeScript data-access library + unit tests.
- `packages/fanout/` — the Python Lambda handler + unit tests.
- `scripts/loadtest.py` — the hot-partition prove-out (sharded vs unsharded).
- `docs/access-patterns.md` — the access-pattern → key-condition table.
- `docs/cost-report.md` — the billing-mode recommendation.

---

## Rules

- **You may** use the AWS CDK, `boto3`, `@aws-sdk/client-dynamodb`, `@aws-sdk/lib-dynamodb`, AWS Lambda Powertools (Python), and the standard test frameworks (`vitest`/`jest` for TS, `pytest` for Python).
- **You may NOT** use a higher-level "single-table ORM" that hides the key design (no `electrodb`, no `dynamodb-toolbox` for the graded surface). The whole point is that *you* compose the keys. You may reference how those libraries work; you may not delegate the modeling to them. (If you want to add an ElectroDB variant as a *bonus*, fine — but the graded store must be hand-rolled.)
- **Every read is a single `GetItem` or `Query`.** Grep your store for `.scan(` / `ScanCommand`; there must be zero hits in the access-pattern code.
- Develop against `dynamodb-local`; deploy the integration test to real AWS (or LocalStack for the Streams → Lambda path). Most of this fits in the DynamoDB free tier; the load test is the line item to watch.
- Tag every resource with `team`, `service`, `environment` (this is a course-wide FinOps rule and the capstone enforces it).
- `RemovalPolicy.DESTROY` is acceptable for the dev table; note in your README that production would be `RETAIN` with point-in-time recovery on.

---

## The access patterns you must serve

All twelve from Lecture 1, plus two the mini-project adds. Reproduce this table in `docs/access-patterns.md` with the exact key condition for each:

| # | Pattern | Index | Operation |
|---|---------|-------|-----------|
| 1 | Get org by id | base | `GetItem` |
| 2 | Get user by id | base | `GetItem` |
| 3 | Get user by email | GSI1 | `Query` |
| 4 | List users in org | base | `Query begins_with USER#` |
| 5 | Get project by id | base | `GetItem` |
| 6 | List projects in org | base | `Query begins_with PROJ#` |
| 7 | List comments on project, newest first | base | `Query begins_with COMMENT#, desc` |
| 8 | Get comment by id | GSI1 | `Query` |
| 9 | Org audit log, newest first | base (sharded) | scatter `Query` × N, merge |
| 10 | Project audit log, newest first | base | `Query begins_with AUDIT#, desc` |
| 11 | Orgs a user belongs to | GSI1 | `Query` |
| 12 | Org activity feed (denormalized projection) | base | `GetItem` or `Query begins_with FEED#` |
| 13 | Comments pending moderation (sparse worklist) | GSI2 | `Query GSI2PK=REVIEW#pending` |
| 14 | Mutations (create/update/delete) | base | `Put`/`Update`/`Delete`/`TransactWrite` |

Pattern 12 (activity feed) and 13 (moderation worklist) are *maintained by the fan-out*, not written by handlers — that is the point of wiring Streams.

---

## Architecture

```
                          write/read (one op each, no scans)
   App handlers ────────────────────────────────────────────►  saas-single-table
        │                                                          │   │   │
        │  TransactWriteItems for the duplicated project row       │  GSI1 GSI2
        │                                                          │  (reverse) (sparse worklist)
        ▼                                                          ▼
   optimistic concurrency (version attr)                    DynamoDB Streams
                                                            NEW_AND_OLD_IMAGES
                                                                   │
                                                                   ▼
                                                       Fan-out Lambda (Python)
                                                       ├─ write immutable audit entry
                                                       ├─ update org activity-feed projection
                                                       └─ report partial-batch failures
```

The fan-out is the keystone. By making the audit log and the activity feed *side effects of the Stream* rather than things every handler must remember to write, you get correctness for free: there is no code path that mutates data without also producing the audit trail, because the audit trail is downstream of the data change itself.

---

## Acceptance criteria

The rubric is below; each box maps to a deliverable. Total 100 points; 70 to pass, 80 for the certificate.

### Access patterns served (30%)

- [ ] All fourteen access patterns are implemented in `packages/store/` and `packages/fanout/`.
- [ ] An integration test exercises each pattern against a deployed table (or `dynamodb-local`) and asserts the result is correct.
- [ ] Every read prints (or logs) the marker `… · 1 {GetItem|Query} · 0 Scans · X RCU · Y ms`. Patterns 9 and 13 are the only multi-call reads (sharded scatter, sparse worklist) and they are documented as such.
- [ ] `grep -r "ScanCommand\|\.scan(" packages/store` returns zero hits in the access-pattern code.
- [ ] `docs/access-patterns.md` contains the full table with exact key conditions.

### Hot-partition mitigation proven (20%)

- [ ] The audit log is write-sharded; `N` is chosen from the capacity math and the choice is documented.
- [ ] `scripts/loadtest.py` runs the unsharded vs sharded comparison against your table and outputs before/after throttle rates showing the throttle collapse.
- [ ] The CloudWatch diagnosis is documented: which metrics (`ThrottledRequests`, `WriteThrottleEvents`, `ConsumedWriteCapacityUnits`) tell the hot-partition story and how.

### Streams → Lambda fan-out wired (25%)

- [ ] The table has Streams enabled with `NEW_AND_OLD_IMAGES`.
- [ ] The fan-out Lambda is deployed with an event-source mapping that sets `batchSize`, `bisectBatchOnError`, `reportBatchItemFailures`, and a sensible `parallelizationFactor`.
- [ ] The fan-out writes the immutable audit entry for every INSERT/MODIFY/REMOVE.
- [ ] The fan-out maintains the org activity-feed projection (pattern 12).
- [ ] The handler distinguishes a TTL-expiry REMOVE (`userIdentity.principalId == dynamodb.amazonaws.com`) from an application delete and records them differently.
- [ ] A test injects a poison record and confirms the rest of the batch commits (partial-batch-failure handling works).

### Cost report (15%)

- [ ] `docs/cost-report.md` is the Challenge 1 deliverable: three profiles, both modes, arithmetic shown, per-profile recommendation, the lifecycle conclusion.
- [ ] The table is deployed in the mode the report recommends for the mini-project's assumed profile, and the IaC reflects it.

### Engineering quality (10%)

- [ ] `cdk deploy --all` deploys the whole thing from zero.
- [ ] Key composition lives in exactly one module; no inline `ORG#` string-building scattered in handlers.
- [ ] The fan-out role and a sample per-tenant read role use `dynamodb:LeadingKeys` for tenant isolation, and a test proves a cross-tenant read is denied.
- [ ] Every resource is tagged `team`/`service`/`environment`.
- [ ] Unit tests pass (`pytest`, `vitest`/`jest`); the README explains how to run them.

---

## Suggested build order

1. **Thursday (lecture + 2h):** Stand up the CDK table stack. Port your exercise-1 store to TypeScript in `packages/store/`. Get patterns 1–11 passing against `dynamodb-local`.
2. **Friday (3h):** Wire the Streams → Lambda fan-out. Make the audit log (pattern 9/10) and the activity feed (pattern 12) side effects of the Stream. Write the partial-batch-failure handling and its test.
3. **Saturday (3h):** Add the sparse GSI2 moderation worklist (pattern 13). Run `scripts/loadtest.py` to prove the hot-partition mitigation. Write `docs/cost-report.md` (from Challenge 1). Add the `dynamodb:LeadingKeys` tenant isolation and its denial test. Polish the README.

---

## The fan-out handler skeleton

Start from this and fill it in. It is the keystone deliverable; the audit log and activity feed must be *derived* from the Stream, not written by handlers.

```python
"""packages/fanout/handler.py — Streams -> Lambda fan-out."""
import os
import boto3
from boto3.dynamodb.types import TypeDeserializer

_d = TypeDeserializer()
_table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

def _img(image: dict | None) -> dict | None:
    return None if image is None else {k: _d.deserialize(v) for k, v in image.items()}

def handler(event, _ctx):
    failures = []
    for record in event["Records"]:
        try:
            name = record["eventName"]                       # INSERT|MODIFY|REMOVE
            new = _img(record["dynamodb"].get("NewImage"))
            old = _img(record["dynamodb"].get("OldImage"))
            via_ttl = (record.get("userIdentity", {}).get("principalId")
                       == "dynamodb.amazonaws.com")
            entity = (new or old or {}).get("entityType")

            if entity == "AuditEntry":
                continue  # never audit the audit log (infinite loop guard)

            _write_audit(name, new, old, via_ttl)
            if entity in ("Project", "Comment"):
                _update_activity_feed(name, new, old)
        except Exception:
            failures.append({"itemIdentifier": record["dynamodb"]["SequenceNumber"]})
    return {"batchItemFailures": failures}

def _write_audit(name, new, old, via_ttl):
    ...  # write PK=ORG#<org>, SK=AUDIT#<ts> (sharded) describing the change

def _update_activity_feed(name, new, old):
    ...  # upsert PK=ORG#<org>, SK=FEED#<ts> the projection pattern 12 reads
```

Replace the `...` with real implementations — the grading runs your fan-out against injected Stream records and checks the audit entry and feed item appear.

---

## How this compounds

- **Week 8** gave you the SaaS domain and the relational comparison. This store is the DynamoDB half of that design; for each entity you should be able to say why it lives in DynamoDB rather than Aurora.
- **Week 10** consumes this table's Streams. The fan-out Lambda you wire here is the upstream of next week's EventBridge pipeline — when you add EventBridge in Week 10, the fan-out *publishes* to the bus instead of (or in addition to) updating the projection inline.
- **Week 13** promotes this table to a **Global Table** for multi-region DR. If your keys are region-agnostic (they should be — no region baked into a key), it is a one-line CDK change. If not, you re-model. This is why Lecture 2 told you to design for Global Tables now.
- **The capstone** uses this table verbatim as its transactional store and includes a chaos drill that forces a hot partition and proves the mitigation — the same `scripts/loadtest.py` you write here.

Ship it like you will run it for a year.
