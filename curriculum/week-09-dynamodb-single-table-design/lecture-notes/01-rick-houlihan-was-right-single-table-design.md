# Lecture 1 — Rick Houlihan Was Right: The Single-Table Design for a Multi-Tenant CRUD App, Drawn Live

> **Reading time:** ~75 minutes. **Hands-on time:** ~75 minutes (you draw the table in NoSQL Workbench and deploy it with CDK).

This is the lecture where you unlearn the relational reflex. If you have spent any time with Postgres — and after Week 8 you have — your instinct when you see "users, organizations, projects, comments, an audit log" is to draw five tables, add foreign keys, and let the query planner join them at read time. That instinct is correct for Postgres and *wrong* for DynamoDB, and the entire difficulty of this week is in holding both of those statements in your head at once without flinching.

The framing is **Rick Houlihan was right**. Houlihan ran the NoSQL practice at AWS and gave a series of re:Invent talks (DAT401 in 2018, DAT403 in 2019, DAT410 in 2020) that converted a generation of engineers from "one table per entity, just like SQL" to "one table, modeled around your access patterns." The talks are still the best thing on the topic; watch one this week. The thesis is short: **in DynamoDB you do not model your data, you model your queries.** You write down every access pattern your application needs, you design a key schema that serves each one with a single `GetItem` or `Query`, and the table's *shape* falls out of that exercise. The entities are an implementation detail. The access patterns are the spec.

By the end of this lecture you can take the Week 8 SaaS domain — five entities, a multi-tenant boundary, an audit trail — and produce a single-table design where every read your application performs is one round trip against a key condition, with zero `Scan` operations and zero client-side joins. You will draw it in NoSQL Workbench, write the CDK that deploys it, and write the first few access patterns in Python with `boto3`.

## 1.1 — Why one table, and why it feels wrong

The relational model optimizes for *write-time flexibility*. You normalize so that each fact lives in exactly one place, you add foreign keys so the database enforces referential integrity, and you defer the cost of assembling a view until read time, where the query planner joins, sorts, and filters on the fly. This is a magnificent trade when you do not know your queries in advance — an analyst can write a `JOIN` you never anticipated and the planner will figure it out. It is a terrible trade when you *do* know your queries and you need them to be fast and cheap at any scale, because a join is a scatter-gather across multiple B-trees and its cost grows with your data.

DynamoDB makes the opposite trade. It optimizes for *read-time predictability*. There are no joins. There is no query planner. There is a hash function that maps your partition key onto a physical storage node, and a sorted index within that node keyed by your sort key. A `Query` against a partition key reads a contiguous run of items from one node, in sort-key order, in single-digit milliseconds, and the cost is proportional to the data you read — *not* to the size of the table. A 10-item `Query` costs the same whether the table holds a thousand items or a hundred billion. That is the property you are buying. The price is that you must pre-compute, at write time, the layout that makes each read a single contiguous run. There is no planner to bail you out at read time.

The single-table pattern is the consequence. If every access pattern must be a `Query` against one partition, and you have multiple entity types that need to be fetched together (an organization *and* its projects, a project *and* its comments), then those entities must live in the same partition — which means they must live in the same table, because a partition is a table-local concept. You cannot `Query` across two tables. So: **one table, many entity types, keys engineered so that items you read together sort together.** That is single-table design in one sentence.

A second, quieter reason: each DynamoDB table is a billing and operational unit. On-demand capacity, autoscaling, alarms, backups, Streams, Global-Table replication — all of it is per-table. Five tables is five of everything. One table is one. For a service with a handful of related entities, the operational simplicity alone justifies the pattern before you even get to the read-cost argument.

This is not a universal law. Single-table design is the right default for the OLTP workloads DynamoDB is built for — known access patterns, high request rates, predictable latency. It is *not* right when your access patterns are unknown or change weekly (use Postgres), when you need ad-hoc analytics (use a data lake, which is Week 11), or when two entity types share no access patterns at all (then two tables is honest, not heretical). The discipline is to derive the answer from the patterns, not to apply the pattern dogmatically.

## 1.2 — The data model, precisely

Three nouns: **tables**, **items**, **attributes**. A table holds items. An item is a collection of attributes, up to 400 KB total. An attribute is a name and a typed value (`S` string, `N` number, `B` binary, `BOOL`, `NULL`, `M` map, `L` list, `SS`/`NS`/`BS` sets). There is no schema beyond the primary key — two items in the same table can have completely different attributes. That schemalessness is what lets one table hold five entity types.

The **primary key** uniquely identifies each item. It comes in two shapes:

- **Simple primary key:** a partition key (PK) alone. The partition key is hashed; items are spread across physical partitions by that hash. `GetItem` by PK is your only key-based read.
- **Composite primary key:** a partition key (PK) *plus* a sort key (SK). Items with the same PK live in the same partition, stored sorted by SK. This is the shape you want for single-table design, every time. `Query` by PK returns all items in that partition, optionally narrowed by an SK condition (`begins_with`, `between`, `>`, `<`, `=`).

The partition key is sometimes called the *hash key* and the sort key the *range key* — the AWS API uses `HASH` and `RANGE` as the `KeyType` values, so you will see both vocabularies. They mean the same thing.

The single-table trick that confuses everyone the first time: **you give the partition and sort key generic names** — `PK` and `SK` — instead of meaningful ones like `OrgId` or `ProjectId`. This is *key overloading*. Because the table is schemaless, a `PK` of `ORG#acme` on one item and `PK` of `USER#u_123` on another are both fine; the attribute is just called `PK` and holds a string. You distinguish entity types by an *entity prefix* convention (`ORG#`, `USER#`, `PROJ#`, `COMMENT#`, `AUDIT#`) baked into the key value. The prefix is data, not schema. This is the single most disorienting idea for relational engineers and the single most important one to internalize: **the key is a string you compose, and you compose it to control physical layout.**

## 1.3 — Access patterns first: write them down

Houlihan's method, and ours: before you touch a key, you enumerate every read and write your application performs. Not "the data we have" — the *operations* the application issues. For the Week 8 multi-tenant SaaS, here is the complete list. Each tenant is an organization; users belong to an organization; projects belong to an organization; comments belong to a project; the audit log records every mutation.

| # | Access pattern | Type |
|---|----------------|------|
| 1 | Get an organization by id | Read |
| 2 | Get a user by id | Read |
| 3 | Get a user by email (login) | Read |
| 4 | List all users in an organization | Read |
| 5 | Get a project by id | Read |
| 6 | List all projects in an organization | Read |
| 7 | List all comments on a project, newest first | Read |
| 8 | Get a single comment by id | Read |
| 9 | List the audit log for an organization, newest first | Read |
| 10 | List the audit log for a single project, newest first | Read |
| 11 | List all organizations a user belongs to (a user can be in many) | Read |
| 12 | Create / update / delete each entity | Write |

Twelve patterns. Notice what is *not* here: "list all comments across all projects," "find every project created last Tuesday," "full-text search the audit log." Those are analytics queries; they do not belong in DynamoDB and we will not serve them here. If your product needs them, you stream the table into a data lake (Week 11) and query there. Keeping the pattern list honest is half the battle — every pattern you add costs a key design decision, and patterns you do not have cost nothing.

## 1.4 — Deriving the keys

Now we design `PK`/`SK` so each pattern is one operation. The method: group patterns that fetch related items together, because items fetched together must share a partition.

**The org partition.** Patterns 1, 4, 6, 9 are all "things scoped to one organization." Put the organization metadata item, its users, its projects, and its audit log in the **same partition**, keyed by the org id. Then a single `Query` on `PK = ORG#acme` returns the org and everything under it; an `SK` `begins_with` narrows to just the users, just the projects, or just the audit entries.

```
PK              SK                       (entity)
ORG#acme        ORG#acme                 organization metadata
ORG#acme        USER#u_001               user (membership row)
ORG#acme        USER#u_002               user (membership row)
ORG#acme        PROJ#p_100               project
ORG#acme        PROJ#p_101               project
ORG#acme        AUDIT#2026-06-09T...     audit entry
```

The org metadata item uses `SK = ORG#acme` (the same value as PK) so it sorts first and is easy to fetch alone with `GetItem`. Users sort under `USER#`, projects under `PROJ#`, audit entries under `AUDIT#` followed by an ISO-8601 timestamp so they sort chronologically. Pattern 4 (list users in org) is `Query(PK=ORG#acme, SK begins_with USER#)`. Pattern 6 (list projects) is `begins_with PROJ#`. Pattern 9 (org audit log, newest first) is `begins_with AUDIT#` with `ScanIndexForward=False`. Four patterns, one partition, zero scans.

**The project partition.** Patterns 7, 8, 10 are scoped to one project — its comments and its audit entries. A project's comments can be numerous, so we give each project its *own* partition keyed by project id, so a busy project does not bloat the org partition:

```
PK              SK                       (entity)
PROJ#p_100      PROJ#p_100               project detail (duplicate of the row in the org partition)
PROJ#p_100      COMMENT#2026-06-09T...   comment
PROJ#p_100      COMMENT#2026-06-09T...   comment
PROJ#p_100      AUDIT#2026-06-09T...     project-scoped audit entry
```

Pattern 7 (comments newest first) is `Query(PK=PROJ#p_100, SK begins_with COMMENT#, ScanIndexForward=False)`. Pattern 10 (project audit) is `begins_with AUDIT#`. The project row appears in *two* partitions — once under `ORG#acme` (so the org's project list includes it) and once under `PROJ#p_100` (as the anchor of the project's own partition). That duplication is deliberate and normal in DynamoDB; you keep both copies consistent with a transaction (Lecture 2 and Thursday's material).

**Get-by-id.** Patterns 1, 5, 8 are `GetItem` on the exact key. Org: `GetItem(PK=ORG#acme, SK=ORG#acme)`. Project: `GetItem(PK=PROJ#p_100, SK=PROJ#p_100)`. Comment by id is the awkward one — a comment's SK is a timestamp, not its id, so you cannot `GetItem` it by id directly. Either you encode the comment id *into* the SK (`COMMENT#<ts>#<id>`) and accept that get-by-id needs the timestamp too, or you serve it from a GSI (Lecture 2). We will use the GSI.

That leaves patterns 3 (user by email) and 11 (orgs a user belongs to). Neither fits the base table's key. Both are served by **Global Secondary Indexes**, which is the whole of Lecture 2. For now, note that the base table serves 1, 2, 4, 5, 6, 7, 9, 10 directly, and we owe a GSI to 3, 8, and 11.

## 1.5 — The access-pattern table, completed

The artifact you produce — and the artifact a reviewer asks for first — is the access-pattern table mapping each pattern to its exact key condition. This is the deliverable. If you cannot fill in the "Key condition" column for every row with a `GetItem` or a `Query`, you have not finished modeling.

| # | Pattern | Index | Key condition |
|---|---------|-------|---------------|
| 1 | Get org by id | base | `GetItem(PK=ORG#<id>, SK=ORG#<id>)` |
| 2 | Get user by id | base | `GetItem(PK=ORG#<org>, SK=USER#<id>)` |
| 3 | Get user by email | GSI1 | `Query(GSI1PK=EMAIL#<email>)` |
| 4 | List users in org | base | `Query(PK=ORG#<org>, SK begins_with USER#)` |
| 5 | Get project by id | base | `GetItem(PK=PROJ#<id>, SK=PROJ#<id>)` |
| 6 | List projects in org | base | `Query(PK=ORG#<org>, SK begins_with PROJ#)` |
| 7 | List comments on project, newest first | base | `Query(PK=PROJ#<id>, SK begins_with COMMENT#, desc)` |
| 8 | Get comment by id | GSI1 | `Query(GSI1PK=COMMENT#<id>)` |
| 9 | Org audit log, newest first | base | `Query(PK=ORG#<org>, SK begins_with AUDIT#, desc)` |
| 10 | Project audit log, newest first | base | `Query(PK=PROJ#<id>, SK begins_with AUDIT#, desc)` |
| 11 | Orgs a user belongs to | GSI1 | `Query(GSI1PK=USER#<id>, GSI1SK begins_with ORG#)` |
| 12 | Mutations | base | `PutItem` / `UpdateItem` / `DeleteItem` / `TransactWriteItems` |

Every row is one operation. No scans. That is the bar.

## 1.6 — Drawing it in NoSQL Workbench

Before you write code, draw the table in **NoSQL Workbench for DynamoDB** (free; install link is in `resources.md`). Workbench lets you define the `PK`/`SK` schema, add facets for each entity type, populate sample items, and *visualize* the GSIs as separate sorted views. Seeing the data sorted under each partition is the moment single-table design clicks. Create a data model, add the facets for Organization, User, Project, Comment, and AuditEntry, populate three orgs' worth of sample data, and switch to the "Visualizer" tab to watch the items sort. Export the model JSON into your repo — it is a reviewable artifact and Workbench can commit a populated table straight to a `dynamodb-local` instance for the exercises.

## 1.7 — Deploying the table with CDK

Here is the base table in CDK v2 (TypeScript), using `TableV2` — the modern construct that is Global-Tables-aware and defaults to the right things. We define the base table now; the GSI is added in Lecture 2, but the construct call shows where it goes.

```typescript
import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import {
  TableV2,
  AttributeType,
  Billing,
  StreamViewType,
  ProjectionType,
} from 'aws-cdk-lib/aws-dynamodb';

export class SaasTableStack extends cdk.Stack {
  public readonly table: TableV2;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.table = new TableV2(this, 'SaasTable', {
      tableName: 'saas-single-table',
      partitionKey: { name: 'PK', type: AttributeType.STRING },
      sortKey: { name: 'SK', type: AttributeType.STRING },
      // Start on-demand. The Friday challenge switches this to provisioned
      // with autoscaling and measures the cost delta.
      billing: Billing.onDemand(),
      // NEW_AND_OLD_IMAGES so the Streams -> Lambda fan-out (Thursday) can
      // see both the before and after state of every mutation.
      dynamoStream: StreamViewType.NEW_AND_OLD_IMAGES,
      // TTL: items carrying an `expiresAt` epoch-seconds attribute get
      // garbage-collected by DynamoDB within ~48h. We TTL stale audit rows.
      timeToLiveAttribute: 'expiresAt',
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.DESTROY, // dev only; RETAIN in prod
      globalSecondaryIndexes: [
        {
          indexName: 'GSI1',
          partitionKey: { name: 'GSI1PK', type: AttributeType.STRING },
          sortKey: { name: 'GSI1SK', type: AttributeType.STRING },
          projectionType: ProjectionType.ALL,
        },
      ],
    });

    new cdk.CfnOutput(this, 'TableName', { value: this.table.tableName });
    new cdk.CfnOutput(this, 'TableArn', { value: this.table.tableArn });
  }
}
```

The CloudFormation equivalent, for literacy — note that the modern resource type is `AWS::DynamoDB::GlobalTable`, not the legacy `AWS::DynamoDB::Table`, even for a single-region table:

```yaml
Resources:
  SaasTable:
    Type: AWS::DynamoDB::GlobalTable
    Properties:
      TableName: saas-single-table
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - { AttributeName: PK, AttributeType: S }
        - { AttributeName: SK, AttributeType: S }
        - { AttributeName: GSI1PK, AttributeType: S }
        - { AttributeName: GSI1SK, AttributeType: S }
      KeySchema:
        - { AttributeName: PK, KeyType: HASH }
        - { AttributeName: SK, KeyType: RANGE }
      GlobalSecondaryIndexes:
        - IndexName: GSI1
          KeySchema:
            - { AttributeName: GSI1PK, KeyType: HASH }
            - { AttributeName: GSI1SK, KeyType: RANGE }
          Projection: { ProjectionType: ALL }
      StreamSpecification:
        StreamViewType: NEW_AND_OLD_IMAGES
      TimeToLiveSpecification:
        AttributeName: expiresAt
        Enabled: true
      Replicas:
        - Region: !Ref AWS::Region
          PointInTimeRecoverySpecification:
            PointInTimeRecoveryEnabled: true
```

And the OpenTofu form, for the cross-cloud crowd:

```hcl
resource "aws_dynamodb_table" "saas" {
  name         = "saas-single-table"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute { name = "PK"     type = "S" }
  attribute { name = "SK"     type = "S" }
  attribute { name = "GSI1PK" type = "S" }
  attribute { name = "GSI1SK" type = "S" }

  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  point_in_time_recovery { enabled = true }
}
```

Three tools, one table. Use CDK as the primary; the CloudFormation and OpenTofu forms are here so that when a reviewer asks "what does this look like without the L2 construct," you can answer.

## 1.8 — Writing items: composing the keys in code

The keys are strings you build. Centralize that string-building in one module so the prefix convention lives in exactly one place — scattering `f"ORG#{org_id}"` across your handlers is how single-table designs rot. Here is the key module and the create-comment write in Python with `boto3`:

```python
"""keys.py — the single source of truth for key composition."""
from datetime import datetime, timezone

def org_pk(org_id: str) -> str:
    return f"ORG#{org_id}"

def user_sk(user_id: str) -> str:
    return f"USER#{user_id}"

def project_pk(project_id: str) -> str:
    return f"PROJ#{project_id}"

def comment_sk(created_at: str, comment_id: str) -> str:
    # Timestamp first so comments sort chronologically; id appended so the
    # SK is unique even when two comments share a millisecond.
    return f"COMMENT#{created_at}#{comment_id}"

def audit_sk(created_at: str) -> str:
    return f"AUDIT#{created_at}"

def now_iso() -> str:
    # Millisecond-precision ISO-8601, UTC, lexicographically sortable.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
```

```python
"""writes.py — creating a comment, with the GSI1 keys populated for get-by-id."""
import boto3, uuid
import keys

ddb = boto3.resource("dynamodb")
table = ddb.Table("saas-single-table")

def create_comment(project_id: str, author_id: str, body: str) -> dict:
    comment_id = "c_" + uuid.uuid4().hex[:12]
    created_at = keys.now_iso()
    item = {
        "PK": keys.project_pk(project_id),
        "SK": keys.comment_sk(created_at, comment_id),
        # GSI1 lets us GetItem-by-id (access pattern 8): GSI1PK = COMMENT#<id>.
        "GSI1PK": f"COMMENT#{comment_id}",
        "GSI1SK": f"COMMENT#{comment_id}",
        "entityType": "Comment",
        "commentId": comment_id,
        "projectId": project_id,
        "authorId": author_id,
        "body": body,
        "createdAt": created_at,
    }
    # Conditional write: refuse to overwrite an item with the same key.
    # The probability of an id collision is negligible, but the guard is free.
    table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(PK)",
    )
    return item
```

## 1.9 — Reading items: the access patterns in code

Now the reads. Each one is a single `Query` or `GetItem`. Note `KeyConditionExpression` with `begins_with`, and `ScanIndexForward=False` to get newest-first.

```python
"""reads.py — the access patterns, one operation each."""
import boto3
from boto3.dynamodb.conditions import Key
import keys

ddb = boto3.resource("dynamodb")
table = ddb.Table("saas-single-table")

def list_users_in_org(org_id: str) -> list[dict]:
    # Access pattern 4: one Query, zero scans.
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(keys.org_pk(org_id))
        & Key("SK").begins_with("USER#")
    )
    return resp["Items"]

def list_projects_in_org(org_id: str) -> list[dict]:
    # Access pattern 6.
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(keys.org_pk(org_id))
        & Key("SK").begins_with("PROJ#")
    )
    return resp["Items"]

def list_comments_newest_first(project_id: str, limit: int = 50) -> list[dict]:
    # Access pattern 7: ScanIndexForward=False reads the sorted partition
    # in descending SK order, which is reverse-chronological.
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(keys.project_pk(project_id))
        & Key("SK").begins_with("COMMENT#"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return resp["Items"]

def get_org(org_id: str) -> dict | None:
    # Access pattern 1: a single GetItem.
    resp = table.get_item(Key={"PK": keys.org_pk(org_id), "SK": keys.org_pk(org_id)})
    return resp.get("Item")
```

Run `list_comments_newest_first("p_100")` against a populated `dynamodb-local`, capture the `ConsumedCapacity` (pass `ReturnConsumedCapacity="TOTAL"`), and you have produced the marker the README promises:

```
Access pattern served · 1 Query · 0 Scans · 2.5 RCU · 4.1 ms
```

That line is the contract. If serving a pattern needs a `Scan`, a client-side filter over a large result set, or two round trips, you have not finished modeling it. A `Scan` in your hot path is a design bug, not a performance bug.

## 1.10 — Multi-tenancy: the partition key *is* the tenant boundary

Multi-tenancy in this design is not a feature you add; it is a property of the key. Every item that belongs to organization `acme` has `acme` in its partition key, directly (`ORG#acme`) or transitively (a project's `PROJ#p_100` partition belongs to `acme` because the project row in the org partition says so). This gives you two things for free:

1. **Tenant isolation in IAM.** You can write an IAM policy with a `dynamodb:LeadingKeys` condition that restricts a principal to partition keys beginning with their tenant id. A per-tenant Lambda role can be locked to `ORG#acme*` so a bug cannot read another tenant's data. We wire this in the mini-project.
2. **Tenant-scoped queries by construction.** Because every read starts from a tenant-scoped partition key, you cannot *accidentally* return cross-tenant data — there is no `WHERE org_id = ?` to forget. The org id is structurally part of every key.

The `dynamodb:LeadingKeys` condition only works against the *partition* key, which is one more reason the tenant id belongs at the front of the partition key. Design for the isolation boundary you want to enforce in IAM, not just the queries you want to run.

## 1.11 — Where this goes

You now have a base table that serves eight of the twelve access patterns with single operations, a key module, and the read/write code for the common paths. Three patterns (user-by-email, comment-by-id, orgs-a-user-belongs-to) need a GSI; one relationship (the duplicated project row) needs a transaction to stay consistent; and the whole thing needs to survive a hot partition. That is Lecture 2 and the rest of the week.

The deliverable from this lecture is the access-pattern table, the NoSQL Workbench model, and the deployed base table with the read/write code for patterns 1, 4, 6, 7. Get those working against `dynamodb-local` before Tuesday. The hardest mental model in the AWS catalog is mostly muscle memory once you have drawn it once — so draw it.

---

*Next: Lecture 2 — Defeating the Hot Partition. GSIs vs LSIs, sparse indexes, write-sharding, and the capacity-unit math that tells you which mode to run.*
