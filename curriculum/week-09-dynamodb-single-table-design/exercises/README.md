# Week 9 — Exercises

Three exercises that build, break, and fix a single-table DynamoDB design. Do them in order — each depends on the table from the one before. Everything runs against **`dynamodb-local`** (Docker) so you can iterate offline for free; only the load tests benefit from real AWS, and even those work against local with the throttle simulated.

Spin up the engine once:

```bash
docker run -d --name ddb-local -p 8000:8000 amazon/dynamodb-local
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=local
export AWS_SECRET_ACCESS_KEY=local
export DDB_ENDPOINT=http://localhost:8000   # the exercises read this env var
```

Each exercise's code reads `DDB_ENDPOINT`; unset it to run against real AWS instead. Install the one dependency: `pip install boto3`.

| Exercise | File | What you do | Time |
|----------|------|-------------|------|
| 1 | [exercise-01-single-table-saas.md](./exercise-01-single-table-saas.md) | Implement the full single-table design for the multi-tenant SaaS CRUD app: users, organizations, projects, comments, audit log. Serve all twelve access patterns. | ~3h |
| 2 | [exercise-02-hot-partition-and-gsi.py](./exercise-02-hot-partition-and-gsi.py) | Hammer one partition key until it throttles, read the throttle signal, then add a GSI for a reverse-lookup access pattern. Runnable. | ~2h |
| 3 | [exercise-03-write-sharding.py](./exercise-03-write-sharding.py) | Add write-sharding to defeat the hot partition from exercise 2 and confirm the throttling disappears, with before/after numbers. Runnable. | ~2h |

## The bar for every exercise

The recurring marker from the README applies to all three. Every served read prints:

```
Access pattern served · 1 Query · 0 Scans · 2.5 RCU · 4.1 ms
```

A `Scan`, a client-side filter over a large result set, or a second round trip means the pattern is not finished. Treat a `Scan` in the hot path as a failing test.

## Running the runnable exercises

```bash
python exercises/exercise-02-hot-partition-and-gsi.py
python exercises/exercise-03-write-sharding.py
```

Both are self-contained: they create their own table, seed data, run the load, print the numbers, and clean up. Read the docstring at the top of each for the expected output. Solutions and discussion are inline in exercise-01; the runnable files *are* the solutions, annotated.
