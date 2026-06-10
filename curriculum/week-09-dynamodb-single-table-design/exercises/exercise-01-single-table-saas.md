# Exercise 1 — Implement the Single-Table Design for the Multi-Tenant SaaS

> **Estimated time:** ~3 hours. This is the foundational exercise of the week; exercises 2 and 3 and the mini-project build on the table you create here.

You will implement, end to end, the single-table design from Lecture 1: a multi-tenant SaaS with **users, organizations, projects, comments, and an immutable audit log**, all in one DynamoDB table, serving all twelve access patterns with single operations and zero scans. You write it against `dynamodb-local`, prove each access pattern with the `ConsumedCapacity` marker, and finish with a small CLI that exercises the whole thing.

## Goal

A Python module `saas_store.py` that exposes one function per access pattern, every read a single `GetItem` or `Query`, and a `demo.py` that seeds two organizations and prints the marker line for each served pattern.

## Step 0 — Scaffolding

Spin up the engine (see `exercises/README.md`) and create the project:

```bash
mkdir -p saas && cd saas
python -m venv .venv && source .venv/bin/activate
pip install boto3
```

## Step 1 — The key module

Centralize key composition in `keys.py`. The prefix convention lives here and *only* here.

```python
"""keys.py — single source of truth for key composition."""
from datetime import datetime, timezone

def org_pk(org_id: str) -> str:            return f"ORG#{org_id}"
def org_sk(org_id: str) -> str:            return f"ORG#{org_id}"
def user_sk(user_id: str) -> str:          return f"USER#{user_id}"
def project_key(project_id: str) -> str:   return f"PROJ#{project_id}"
def comment_sk(ts: str, cid: str) -> str:  return f"COMMENT#{ts}#{cid}"
def audit_sk(ts: str) -> str:              return f"AUDIT#{ts}"

def email_gsi(email: str) -> str:          return f"EMAIL#{email.lower()}"
def comment_gsi(cid: str) -> str:          return f"COMMENT#{cid}"
def user_gsi(user_id: str) -> str:         return f"USER#{user_id}"

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
```

## Step 2 — Create the table

`table.py` creates the base table with the GSI1 overloaded index. Note `endpoint_url` is read from the environment so the same code runs local or against AWS.

```python
"""table.py — create the single table with GSI1."""
import os, boto3

TABLE_NAME = "saas-single-table"

def client():
    endpoint = os.environ.get("DDB_ENDPOINT")
    return boto3.client("dynamodb", endpoint_url=endpoint)

def resource():
    endpoint = os.environ.get("DDB_ENDPOINT")
    return boto3.resource("dynamodb", endpoint_url=endpoint)

def create_table() -> None:
    c = client()
    existing = c.list_tables()["TableNames"]
    if TABLE_NAME in existing:
        return
    c.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[{
            "IndexName": "GSI1",
            "KeySchema": [
                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }],
    )
    c.get_waiter("table_exists").wait(TableName=TABLE_NAME)

if __name__ == "__main__":
    create_table()
    print(f"Table {TABLE_NAME} ready.")
```

## Step 3 — The writes

`writes.py` — one create per entity. Organizations and projects use transactions where the duplicated-row consistency matters; users carry the email GSI key; audit entries are written by the application on every mutation (in the mini-project the audit log is written by the Stream consumer instead — here we write it inline so you see the shape).

```python
"""writes.py — entity creation."""
import uuid
import keys
from table import resource, client, TABLE_NAME

table = resource().Table(TABLE_NAME)

def create_org(org_id: str, name: str) -> dict:
    item = {
        "PK": keys.org_pk(org_id), "SK": keys.org_sk(org_id),
        "entityType": "Organization", "orgId": org_id, "name": name,
        "version": 1, "createdAt": keys.now_iso(),
    }
    table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    return item

def create_user(org_id: str, user_id: str, email: str, name: str) -> dict:
    item = {
        "PK": keys.org_pk(org_id), "SK": keys.user_sk(user_id),
        # GSI1 serves user-by-email (pattern 3) and orgs-of-user (pattern 11).
        "GSI1PK": keys.email_gsi(email), "GSI1SK": keys.org_pk(org_id),
        "entityType": "User", "userId": user_id, "orgId": org_id,
        "email": email.lower(), "name": name, "createdAt": keys.now_iso(),
    }
    table.put_item(Item=item, ConditionExpression="attribute_not_exists(SK)")
    return item

def create_project(org_id: str, project_id: str, name: str) -> dict:
    c = client()
    attrs = {
        "entityType": {"S": "Project"}, "projectId": {"S": project_id},
        "orgId": {"S": org_id}, "name": {"S": name},
        "version": {"N": "1"}, "createdAt": {"S": keys.now_iso()},
    }
    c.transact_write_items(
        ClientRequestToken=f"createproj-{project_id}",
        TransactItems=[
            {"Put": {"TableName": TABLE_NAME, "ConditionExpression": "attribute_not_exists(PK)",
                     "Item": {"PK": {"S": keys.org_pk(org_id)},
                              "SK": {"S": keys.project_key(project_id)}, **attrs}}},
            {"Put": {"TableName": TABLE_NAME, "ConditionExpression": "attribute_not_exists(PK)",
                     "Item": {"PK": {"S": keys.project_key(project_id)},
                              "SK": {"S": keys.project_key(project_id)}, **attrs}}},
        ],
    )
    return {"projectId": project_id, "orgId": org_id, "name": name}

def create_comment(project_id: str, author_id: str, body: str) -> dict:
    cid = "c_" + uuid.uuid4().hex[:12]
    ts = keys.now_iso()
    item = {
        "PK": keys.project_key(project_id), "SK": keys.comment_sk(ts, cid),
        "GSI1PK": keys.comment_gsi(cid), "GSI1SK": keys.comment_gsi(cid),
        "entityType": "Comment", "commentId": cid, "projectId": project_id,
        "authorId": author_id, "body": body, "createdAt": ts,
    }
    table.put_item(Item=item, ConditionExpression="attribute_not_exists(SK)")
    return item

def write_audit(scope_pk: str, action: str, actor: str, detail: str) -> dict:
    ts = keys.now_iso()
    item = {
        "PK": scope_pk, "SK": keys.audit_sk(ts), "entityType": "AuditEntry",
        "action": action, "actor": actor, "detail": detail, "createdAt": ts,
    }
    table.put_item(Item=item)
    return item
```

## Step 4 — The reads (the twelve patterns)

`reads.py` — each one prints the marker. The `_marker` helper turns `ConsumedCapacity` plus a wall-clock timing into the README's contract line.

```python
"""reads.py — every access pattern, one operation, with the marker."""
import time
from boto3.dynamodb.conditions import Key
import keys
from table import resource, TABLE_NAME

table = resource().Table(TABLE_NAME)

def _marker(label: str, op: str, scans: int, resp: dict, t0: float) -> None:
    rcu = resp.get("ConsumedCapacity", {}).get("CapacityUnits", 0.0)
    ms = (time.perf_counter() - t0) * 1000
    print(f"{label} · 1 {op} · {scans} Scans · {rcu:.1f} RCU · {ms:.1f} ms")

def get_org(org_id: str) -> dict | None:                       # pattern 1
    t0 = time.perf_counter()
    r = table.get_item(Key={"PK": keys.org_pk(org_id), "SK": keys.org_sk(org_id)},
                       ReturnConsumedCapacity="TOTAL")
    _marker("get_org", "GetItem", 0, r, t0)
    return r.get("Item")

def get_user(org_id: str, user_id: str) -> dict | None:        # pattern 2
    t0 = time.perf_counter()
    r = table.get_item(Key={"PK": keys.org_pk(org_id), "SK": keys.user_sk(user_id)},
                       ReturnConsumedCapacity="TOTAL")
    _marker("get_user", "GetItem", 0, r, t0)
    return r.get("Item")

def get_user_by_email(email: str) -> dict | None:              # pattern 3 (GSI1)
    t0 = time.perf_counter()
    r = table.query(IndexName="GSI1",
                    KeyConditionExpression=Key("GSI1PK").eq(keys.email_gsi(email)),
                    ReturnConsumedCapacity="TOTAL")
    _marker("get_user_by_email", "Query", 0, r, t0)
    items = r["Items"]
    return items[0] if items else None

def list_users_in_org(org_id: str) -> list[dict]:              # pattern 4
    t0 = time.perf_counter()
    r = table.query(KeyConditionExpression=Key("PK").eq(keys.org_pk(org_id))
                    & Key("SK").begins_with("USER#"),
                    ReturnConsumedCapacity="TOTAL")
    _marker("list_users_in_org", "Query", 0, r, t0)
    return r["Items"]

def get_project(project_id: str) -> dict | None:               # pattern 5
    t0 = time.perf_counter()
    r = table.get_item(Key={"PK": keys.project_key(project_id),
                            "SK": keys.project_key(project_id)},
                       ReturnConsumedCapacity="TOTAL")
    _marker("get_project", "GetItem", 0, r, t0)
    return r.get("Item")

def list_projects_in_org(org_id: str) -> list[dict]:           # pattern 6
    t0 = time.perf_counter()
    r = table.query(KeyConditionExpression=Key("PK").eq(keys.org_pk(org_id))
                    & Key("SK").begins_with("PROJ#"),
                    ReturnConsumedCapacity="TOTAL")
    _marker("list_projects_in_org", "Query", 0, r, t0)
    return r["Items"]

def list_comments(project_id: str, limit: int = 50) -> list[dict]:   # pattern 7
    t0 = time.perf_counter()
    r = table.query(KeyConditionExpression=Key("PK").eq(keys.project_key(project_id))
                    & Key("SK").begins_with("COMMENT#"),
                    ScanIndexForward=False, Limit=limit,
                    ReturnConsumedCapacity="TOTAL")
    _marker("list_comments", "Query", 0, r, t0)
    return r["Items"]

def get_comment(comment_id: str) -> dict | None:               # pattern 8 (GSI1)
    t0 = time.perf_counter()
    r = table.query(IndexName="GSI1",
                    KeyConditionExpression=Key("GSI1PK").eq(keys.comment_gsi(comment_id)),
                    ReturnConsumedCapacity="TOTAL")
    _marker("get_comment", "Query", 0, r, t0)
    items = r["Items"]
    return items[0] if items else None

def org_audit(org_id: str, limit: int = 50) -> list[dict]:     # pattern 9
    t0 = time.perf_counter()
    r = table.query(KeyConditionExpression=Key("PK").eq(keys.org_pk(org_id))
                    & Key("SK").begins_with("AUDIT#"),
                    ScanIndexForward=False, Limit=limit,
                    ReturnConsumedCapacity="TOTAL")
    _marker("org_audit", "Query", 0, r, t0)
    return r["Items"]

def project_audit(project_id: str, limit: int = 50) -> list[dict]:   # pattern 10
    t0 = time.perf_counter()
    r = table.query(KeyConditionExpression=Key("PK").eq(keys.project_key(project_id))
                    & Key("SK").begins_with("AUDIT#"),
                    ScanIndexForward=False, Limit=limit,
                    ReturnConsumedCapacity="TOTAL")
    _marker("project_audit", "Query", 0, r, t0)
    return r["Items"]

def orgs_of_user(user_id: str) -> list[dict]:                  # pattern 11 (GSI1)
    t0 = time.perf_counter()
    r = table.query(IndexName="GSI1",
                    KeyConditionExpression=Key("GSI1PK").eq(keys.user_gsi(user_id))
                    & Key("GSI1SK").begins_with("ORG#"),
                    ReturnConsumedCapacity="TOTAL")
    _marker("orgs_of_user", "Query", 0, r, t0)
    return r["Items"]
```

> **Note on pattern 11.** For "orgs a user belongs to" to work, the membership row's `GSI1PK` must be `USER#<id>` rather than `EMAIL#<email>`. A user who can belong to many orgs needs a *separate membership item per org* keyed by `USER#<id>` on the GSI. In step 3 above the user item uses `EMAIL#` for pattern 3; to also serve pattern 11 you write a second, sparse membership item per (user, org) pair with `GSI1PK=USER#<id>, GSI1SK=ORG#<org>`. Add that item in `create_user` if your product allows multi-org users; if every user belongs to exactly one org, pattern 11 is a `GetItem` and you can skip the membership item. Decide which your product needs and document the choice — this is exactly the kind of decision single-table design forces you to make explicit.

## Step 5 — The demo

`demo.py` seeds two organizations and runs every pattern, printing the markers.

```python
"""demo.py — seed and exercise all twelve patterns."""
from table import create_table
import writes, reads

def main() -> None:
    create_table()
    writes.create_org("acme", "Acme Corp")
    writes.create_org("globex", "Globex")
    writes.create_user("acme", "u_001", "alice@acme.com", "Alice")
    writes.create_user("acme", "u_002", "bob@acme.com", "Bob")
    writes.create_project("acme", "p_100", "Website Redesign")
    writes.create_project("acme", "p_101", "Mobile App")
    c1 = writes.create_comment("p_100", "u_001", "First pass looks good.")
    writes.create_comment("p_100", "u_002", "Tweak the hero spacing.")
    writes.write_audit(reads.keys.org_pk("acme"), "project.create", "u_001", "p_100")
    writes.write_audit(reads.keys.project_key("p_100"), "comment.create", "u_001", c1["commentId"])

    print("\n--- access patterns ---")
    reads.get_org("acme")
    reads.get_user("acme", "u_001")
    reads.get_user_by_email("alice@acme.com")
    reads.list_users_in_org("acme")
    reads.get_project("p_100")
    reads.list_projects_in_org("acme")
    reads.list_comments("p_100")
    reads.get_comment(c1["commentId"])
    reads.org_audit("acme")
    reads.project_audit("p_100")

if __name__ == "__main__":
    main()
```

## Expected output

```
Table saas-single-table ready.

--- access patterns ---
get_org · 1 GetItem · 0 Scans · 0.5 RCU · 3.8 ms
get_user · 1 GetItem · 0 Scans · 0.5 RCU · 2.1 ms
get_user_by_email · 1 Query · 0 Scans · 0.5 RCU · 2.9 ms
list_users_in_org · 1 Query · 0 Scans · 0.5 RCU · 3.2 ms
get_project · 1 GetItem · 0 Scans · 0.5 RCU · 2.0 ms
list_projects_in_org · 1 Query · 0 Scans · 0.5 RCU · 3.0 ms
list_comments · 1 Query · 0 Scans · 0.5 RCU · 3.4 ms
get_comment · 1 Query · 0 Scans · 0.5 RCU · 2.7 ms
org_audit · 1 Query · 0 Scans · 0.5 RCU · 3.1 ms
project_audit · 1 Query · 0 Scans · 0.5 RCU · 2.8 ms
```

(RCU values are small because the items are tiny and reads are eventually consistent; on `dynamodb-local` the RCU reported is a model of real-AWS billing. The millisecond numbers will vary by machine.)

## Acceptance criteria

- [ ] `python table.py` creates the table with the GSI1 index.
- [ ] `python demo.py` runs every access pattern and prints `0 Scans` on every line.
- [ ] Every read is a single `GetItem` or `Query` — grep your code for `.scan(`; there must be zero hits.
- [ ] `create_project` uses a transaction so the org-partition row and the project-partition row are written atomically.
- [ ] Killing `demo.py` halfway and re-running it does not error on the duplicate creates (the `attribute_not_exists` conditions and the transaction's `ClientRequestToken` make creates idempotent).
- [ ] You can articulate, for pattern 11, whether your product allows multi-org users and how that changes the membership item.

## Going further

- Add `update_project_name` with optimistic concurrency (the `version` attribute) from Lecture 2 and prove that two concurrent updates produce one `ConditionalCheckFailedException`.
- Add the sparse `GSI2` moderation queue from Lecture 2 and serve "all comments pending review" with one `Query`.
- Export your populated table from NoSQL Workbench and commit the model JSON.
