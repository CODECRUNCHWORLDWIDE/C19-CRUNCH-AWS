# Lecture 1 — The Data-Lakehouse Pattern on AWS, and Why Bedrock Is a Router, Not a Model

> **Reading time:** ~75 minutes. **Hands-on time:** ~60 minutes (you run your first Athena queries and watch the bytes-scanned number move).

This is the lecture that turns "we dump stuff in S3" into "we have a data lake." The difference is not the bucket. The difference is a **catalog**, a **format**, and a **partition layout** chosen on purpose. By the end you will understand the three layers of the lakehouse pattern on AWS, why the Glue Data Catalog is the seam that makes the whole thing composable, why Parquet is non-negotiable, and how Athena's pricing model makes the layout a *dollar* decision and not an aesthetic one. Then we pivot to the inference side and answer the lecture's title question: Bedrock is not a model. It is a router. Understanding that is the difference between using it well and being confused by it.

## 1.1 — "Data lake" is three layers, and only one of them is S3

A junior engineer hears "data lake" and pictures a bucket full of files. That picture is missing two of the three layers, and the two missing ones are where all the engineering lives.

**Layer 1 — Storage.** S3. This is the easy one and the one everyone gets. Your data — raw events, logs, exports, clickstreams — lands in S3 as files. S3 gives you eleven nines of durability, lifecycle tiering (Week 6), and effectively infinite capacity. It is cheap: $0.023/GB/month for Standard, less for the colder tiers. The lake's storage layer is solved by S3 and your Week 6 knowledge. Nothing new here.

**Layer 2 — Format and table layout.** This is where most lakes go wrong. A folder of newline-delimited JSON (NDJSON) is *data in S3*, but it is not a *table*. To make it a table you decide: what file format (JSON? CSV? Parquet? ORC?), what compression (none? Snappy? ZSTD?), what the directory layout encodes (is `dt=2026-06-09/` a partition the query engine understands, or just a folder name?), and whether you want an open *table format* like Apache Iceberg on top to get transactions and schema evolution. The choices here decide whether a query scans 4 GB or 12 MB. They are the subject of Wednesday's exercise and most of this lecture.

**Layer 3 — Catalog.** The Glue Data Catalog. This is the metadata layer: it records that there is a database called `events`, a table called `clicks`, that the table's data lives at `s3://my-lake/clicks/`, that it is Parquet, that it has a column `user_id STRING` and a column `ts TIMESTAMP`, and that it is partitioned by `dt`. **The catalog is the seam.** Athena reads it. Redshift Spectrum reads it. EMR Spark reads it. Glue ETL reads it. QuickSight reads it (through Athena). Lake Formation enforces access on it. You define the table *once* in the catalog and every analytics engine in the account can query the same bytes through it. This is the single most important idea in the AWS data story: **the catalog decouples storage from compute and lets many engines share one table definition.**

```
            ┌──────────────────────────────────────────────┐
            │              Glue Data Catalog                 │   ← Layer 3: metadata seam
            │   db: events                                   │
            │     table: clicks  (Parquet, partitioned dt)   │
            │       location: s3://my-lake/clicks/           │
            └───────────────┬────────────────────────────────┘
            reads through    │  reads through
        ┌────────────────────┼────────────────────┬─────────────────┐
        ▼                    ▼                    ▼                 ▼
    Athena            Redshift Spectrum        EMR Spark        Glue ETL
   (Trino SQL)         (warehouse SQL)       (PySpark)        (transform)
        └────────────────────┴────────────────────┴─────────────────┘
                              │ all read the same bytes
                              ▼
            ┌──────────────────────────────────────────────┐
            │                     S3                          │   ← Layer 1: storage
            │   s3://my-lake/clicks/dt=2026-06-09/*.parquet  │   ← Layer 2: format/layout
            └──────────────────────────────────────────────┘
```

When someone says "we built a lakehouse," they mean: the storage is a lake (S3, open formats, query-in-place), but layer 2 carries warehouse-grade guarantees — ACID transactions, schema evolution, time travel — via an open table format (Iceberg most commonly in 2026, with Delta Lake and Hudi as the other two contenders). The "lake vs warehouse" dichotomy collapsed because Iceberg gave the lake the things only a warehouse used to have. You do not have to use Iceberg on day one — raw Parquet is fine for append-only event data — but you should know that the upgrade path exists and is one `TBLPROPERTIES` line away in Athena.

## 1.2 — How data gets into the lake: Firehose, the Week-10 tap

This week's lake is fed by **Kinesis Data Firehose**, the same delivery stream you wired up in the Week 10 event pipeline. Firehose is the right tool for the "land streaming records into S3 with no code" job: you point a producer at it, it buffers records, and it writes them to S3 in batches. You configure two buffering knobs and a partitioning strategy.

The buffering knobs are a classic latency-vs-efficiency trade-off:

- **Buffer size** — Firehose accumulates up to N MB (1–128 MB) before flushing.
- **Buffer interval** — or up to N seconds (60–900 s), whichever comes first.

Small buffers (1 MB / 60 s) give you fresh data but many tiny files. **Tiny files are the enemy of a query engine.** Athena and Spark both have per-file overhead; a thousand 4 KB files is dramatically slower and more expensive to scan than one 4 MB file. Large buffers (128 MB / 900 s) give you fat, efficient files but stale data — up to 15 minutes behind. For an analytics lake where "an hour behind" is fine, bias toward larger buffers. For a near-real-time dashboard, bias smaller and accept the small-file tax (or compact later). There is no universally right answer; there is a deliberate choice you make based on the freshness SLA.

The partitioning strategy matters because it decides your S3 prefix layout, which decides whether queries can prune. Firehose's **dynamic partitioning** lets you write records to prefixes derived from the record's own fields:

```
s3://my-lake/events/dt=!{partitionKeyFromQuery:dt}/!{firehose:random-string}
```

This produces `s3://my-lake/events/dt=2026-06-09/...`, a Hive-style partition prefix Athena understands natively. The alternative — the default — is Firehose's time-based prefix `YYYY/MM/dd/HH/`, which is *not* Hive-style (`2026/06/09/` is not `dt=2026-06-09/`) and which you then have to teach Athena about with partition projection. Both work; dynamic partitioning costs a small per-GB surcharge and is cleaner. We use the simple time-based prefix in Exercise 1 (to keep cost at zero) and fix the partitioning in Exercise 2.

Here is the Firehose delivery stream as CDK (TypeScript), the shape you will reuse in the mini-project:

```typescript
import { Stack, StackProps, Duration, RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as firehose from 'aws-cdk-lib/aws-kinesisfirehose';

export class LakeIngestStack extends Stack {
  public readonly lakeBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Layer 1: the lake bucket. KMS-managed encryption, versioning off for raw events
    // (versioning a high-volume event lake is a cost trap; you re-ingest, you don't restore).
    this.lakeBucket = new s3.Bucket(this, 'LakeBucket', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.DESTROY, // lab convenience; in prod use RETAIN
      autoDeleteObjects: true,               // lab convenience only
    });

    // Firehose → S3, buffered. The L2 DeliveryStream construct wires the IAM role for us.
    new firehose.DeliveryStream(this, 'EventsStream', {
      destination: new firehose.S3Bucket(this.lakeBucket, {
        dataOutputPrefix: 'events/dt=!{timestamp:yyyy-MM-dd}/',
        errorOutputPrefix: 'errors/!{firehose:error-output-type}/dt=!{timestamp:yyyy-MM-dd}/',
        bufferingInterval: Duration.seconds(60),
        bufferingSize: undefined, // default 5 MB; explicit Size omitted for the lab
      }),
    });
  }
}
```

Note the `errorOutputPrefix`. Firehose writes records it *cannot* deliver (e.g. a failed format conversion) to a separate prefix. If you forget this, failed records vanish silently. Always set it. Note also that the `dataOutputPrefix` uses the `!{timestamp:yyyy-MM-dd}` expression to produce a `dt=` partition — that is the cheap, no-surcharge way to get Hive-style partitions without enabling full dynamic partitioning, and it is what we use in the lab.

## 1.3 — Glue: the catalog, the crawler, and where crawlers lie to you

The Glue Data Catalog is a metastore — conceptually the same Hive Metastore that the Hadoop world has used for fifteen years, except managed and integrated with IAM and Lake Formation. You can populate it three ways:

1. **A crawler** scans S3, infers schema and partitions, and writes the table. Zero code; frequently wrong.
2. **Athena DDL** — you write `CREATE EXTERNAL TABLE ...` by hand. Tedious; exactly right.
3. **IaC** — you declare the table in CDK / CloudFormation / OpenTofu. Tedious to write once; reproducible forever. This is what production does.

The crawler is the gateway drug. It is genuinely useful for *discovery* — point it at an unknown pile of data and it tells you roughly what is in there. But it has failure modes you must know, because every one of them has cost a team a debugging afternoon:

- **It infers `string` for everything ambiguous.** A column of `"2026-06-09"` values gets typed `string`, not `date`, unless every file is unambiguous. You then can't do date math without `CAST`, and worse, partition pruning on a string partition is weaker.
- **It mis-groups files into one table or splits one logical table into many.** The crawler groups by schema similarity and prefix. If two event types share a prefix, it may merge them. If one event type's schema drifts (a new field appears), it may split it. You read the result and fix the grouping with the crawler's "table grouping" settings or by writing the table by hand.
- **It re-runs and *changes your schema* under you.** A crawler on a schedule that re-infers can promote a column from `int` to `string` because one new file had a non-numeric value. Your dashboards break Monday morning. **In production, you crawl once for discovery, then pin the table definition in IaC and turn the crawler off.** A scheduled crawler in production is a foot-gun.
- **It costs money per DPU-hour.** A crawler over millions of objects is not free and not fast.

So the workflow is: crawl to discover (Exercise 1), read the inferred schema critically, then either accept it or replace it with a hand-written / IaC table (Exercise 2 and the mini-project). The crawler is a starting point, not a production dependency.

Here is a crawler in CDK using the L1 `CfnCrawler` (the alpha L2 constructs exist but L1 is what you will see in real codebases):

```typescript
import * as glue from 'aws-cdk-lib/aws-glue';
import * as iam from 'aws-cdk-lib/aws-iam';

const glueRole = new iam.Role(this, 'GlueCrawlerRole', {
  assumedBy: new iam.ServicePrincipal('glue.amazonaws.com'),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSGlueServiceRole'),
  ],
});
this.lakeBucket.grantRead(glueRole);

new glue.CfnDatabase(this, 'EventsDb', {
  catalogId: this.account,
  databaseInput: { name: 'events' },
});

new glue.CfnCrawler(this, 'EventsCrawler', {
  role: glueRole.roleArn,
  databaseName: 'events',
  targets: { s3Targets: [{ path: `s3://${this.lakeBucket.bucketName}/events/` }] },
  // Run on demand; do NOT schedule in production. Crawl to discover, then pin in IaC.
  schemaChangePolicy: {
    updateBehavior: 'LOG',          // log schema changes, don't silently apply them
    deleteBehavior: 'LOG',
  },
});
```

`updateBehavior: 'LOG'` is the safety setting: if the crawler re-runs and the schema drifted, it logs the change instead of mutating your table. The default (`UPDATE_IN_DATABASE`) is the one that breaks Monday's dashboard.

## 1.4 — Athena: bytes scanned is dollars

Athena is serverless interactive SQL over S3. Under the hood it is **Trino** (formerly PrestoSQL) — the same engine you would run yourself if you outgrew Athena. You write standard SQL, Athena reads the table definition from the Glue catalog, scans the underlying S3 data, and returns results. There is no cluster to manage. The pricing model is the entire point of this lecture:

> **Athena charges per byte scanned from S3.** As of 2026, the standard engine is roughly **$5 per terabyte scanned**, rounded up to a 10 MB minimum per query.

This one fact drives every layout decision. Two queries returning the identical answer can differ by 100x in cost depending on how the data is laid out. Consider a table of 4 GB of NDJSON click events and the query:

```sql
SELECT count(*) FROM clicks WHERE dt = '2026-06-09' AND country = 'JP';
```

- **NDJSON, unpartitioned:** Athena reads *all 4 GB* — it cannot know which rows match without reading them, and JSON is row-oriented so it reads every field of every row even though the query touches only two columns. Cost: 4 GB × $5/TB ≈ **$0.020**, run time several seconds.
- **NDJSON, partitioned by `dt`:** Athena reads only the `dt=2026-06-09/` prefix — say 200 MB. It still reads every column. Cost ≈ **$0.001**. A 20x improvement from partitioning alone.
- **Parquet, partitioned by `dt`:** Athena reads only the `dt=2026-06-09/` prefix *and* only the `country` and (for the count) row-group metadata — Parquet stores columns separately and carries per-row-group min/max statistics, so Athena prunes by partition, then prunes columns, then prunes row groups by predicate. It might scan 12 MB. Cost rounds to the **10 MB minimum ≈ $0.00005**. A ~400x improvement over the naive case.

That is the whole game. Wednesday's exercise has you produce these three numbers on your own data and read them off the query footer. Three levers, in order of impact:

1. **Partition** so the engine skips whole prefixes. The biggest lever for time-series data.
2. **Use Parquet** so the engine reads only the columns the query touches and prunes row groups by predicate.
3. **Compress** (Snappy by default, ZSTD for a better ratio at slightly more CPU) so each byte carries more data.

### Partition projection: stop paying for `MSCK REPAIR`

A partitioned table needs Athena to *know* which partitions exist. The old way: run `MSCK REPAIR TABLE clicks;` (or a crawler) every time new partitions land, so Athena re-lists S3 and registers the new `dt=` folders. This is slow, costs money, and is a scheduled job you have to babysit.

**Partition projection** kills that job. You tell Athena the *formula* for the partitions instead of listing them. For a daily date partition:

```sql
CREATE EXTERNAL TABLE clicks (
  user_id string,
  country string,
  ts      timestamp
)
PARTITIONED BY (dt string)
STORED AS PARQUET
LOCATION 's3://my-lake/clicks/'
TBLPROPERTIES (
  'projection.enabled'        = 'true',
  'projection.dt.type'        = 'date',
  'projection.dt.range'       = '2026-01-01,NOW',
  'projection.dt.format'      = 'yyyy-MM-dd',
  'projection.dt.interval'    = '1',
  'projection.dt.interval.unit' = 'DAYS',
  'storage.location.template' = 's3://my-lake/clicks/dt=${dt}/'
);
```

Now when a query filters `WHERE dt = '2026-06-09'`, Athena computes the prefix `s3://my-lake/clicks/dt=2026-06-09/` directly from the projection rule — no S3 listing, no `MSCK`, no crawler, no metadata lag. New days "just work" the instant Firehose writes them. Partition projection is the single best operational upgrade you can make to an Athena table, and it is the production default for time-partitioned data. Exercise 2 and the mini-project both use it.

### CTAS: writing Parquet without an ETL job

You do not need Glue ETL or Spark to convert JSON to partitioned Parquet. Athena does it with `CREATE TABLE AS SELECT`:

```sql
CREATE TABLE clicks_parquet
WITH (
  format = 'PARQUET',
  parquet_compression = 'SNAPPY',
  partitioned_by = ARRAY['dt'],
  external_location = 's3://my-lake/clicks_parquet/'
)
AS
SELECT user_id, country, ts, dt
FROM clicks_raw_json;
```

One statement reads the raw JSON, writes Snappy-compressed Parquet to S3, partitioned by `dt`. Then you point a projected external table at `s3://my-lake/clicks_parquet/` and re-run your queries against the cheap version. CTAS is the lowest-ceremony way to do the format conversion this week; Glue ETL (PySpark) is the heavier tool for when the transform is too complex for SQL or you need to do it on a schedule at scale.

### Workgroup guardrails

Athena's per-byte model means a careless analyst can scan a petabyte and bill you four figures with one `SELECT *`. The guardrail is an **Athena workgroup** with a per-query data-scanned limit:

```typescript
import * as athena from 'aws-cdk-lib/aws-athena';

new athena.CfnWorkGroup(this, 'LakeWorkgroup', {
  name: 'lake-analysts',
  workGroupConfiguration: {
    bytesScannedCutoffPerQuery: 10_000_000_000, // 10 GB hard cap per query
    enforceWorkGroupConfiguration: true,
    resultConfiguration: {
      outputLocation: `s3://${this.lakeBucket.bucketName}/athena-results/`,
    },
    publishCloudWatchMetricsEnabled: true,
  },
});
```

A query that would scan more than the cutoff is *cancelled* before it runs up the bill. Every production Athena deployment sets this. It is the cheapest insurance in the AWS catalog.

## 1.5 — When it's not Athena: Redshift and OpenSearch in two paragraphs each

**Redshift.** Athena is interactive query over a lake; Redshift is a *warehouse* — a managed columnar database you load data into, with its own storage (RA3 nodes separate compute from managed storage), materialized views, and sub-second concurrency for many simultaneous dashboard users. The decision: if your queries are ad-hoc, infrequent, and over data that already lives in S3, Athena is cheaper and simpler — pay per scan, no cluster. If you have a BI workload with hundreds of concurrent users hammering the same curated tables all day, a warehouse's caching and concurrency win, and Redshift's flat per-hour cost beats Athena's per-scan cost at high query volume. **Redshift Spectrum** is the bridge: a Redshift cluster can query S3 data through the *same Glue catalog* Athena uses, so you can keep hot curated data in Redshift-managed storage and join it to cold lake data in S3 without copying. One catalog, two engines.

**OpenSearch.** Neither Athena nor Redshift is the right tool for full-text search, log tailing, or "show me all events matching this fuzzy string in the last 15 minutes with a latency dashboard." That is OpenSearch (the managed Elasticsearch fork). It indexes documents for fast text and aggregation queries and powers Kibana-style dashboards. Use it for observability logs, search-as-a-feature, and security analytics. The 2026 default for new projects is **OpenSearch Serverless** (you pay per OCU — OpenSearch Compute Unit — and it scales to your load) over the older managed-cluster model, unless you need fine-grained instance control. The decision rule: SQL-shaped analytical questions over columnar data → Athena/Redshift; text search and time-series log exploration → OpenSearch.

## 1.6 — Lake Formation: access control as data, not as JSON

Once many engines query one catalog, "who can read what" gets hard. A bucket policy is too coarse — it grants or denies the whole prefix. You want: "the support team can read the `orders` table but only the rows where `region = 'EU'`, and they cannot see the `email` column at all." That is **Lake Formation**.

Lake Formation sits in front of the Glue catalog and enforces:

- **Table and column permissions** — grant `SELECT` on specific columns, deny others. The `email` column simply does not appear for unauthorized principals.
- **Row-level filters** — a data filter expression like `region = 'EU'` is applied transparently; the principal sees only matching rows.
- **LF-Tags (tag-based access control)** — instead of granting on every table, you tag tables/columns (e.g. `classification=pii`) and grant on the tag. New tables inheriting the tag are governed automatically. This scales to thousands of tables where per-table grants do not.

The decision between a bucket policy and Lake Formation: if access is all-or-nothing at the prefix level and one team owns the bucket, a bucket policy is fine and simpler. The moment you need *fine-grained* (column/row) access, or *many* principals with *different* slices of the same table, or *centralized* governance across accounts, you move to Lake Formation. The capstone's analytics lake uses Lake Formation precisely because it is multi-tenant — different tenants must not see each other's rows.

## 1.7 — The pivot: Bedrock is a router, not a model

Now we cross from analytics to inference, and we start with the lecture's title claim, because it reframes everything.

People say "we use Bedrock" the way they say "we use GPT-4." That is a category error. **Bedrock is not a model. Bedrock is a managed API that routes a single request shape to many foundation models.** When you call Bedrock you choose, *per request*, which model answers — Anthropic Claude, Meta Llama, Mistral, Amazon Titan/Nova, Cohere, AI21, and more. The model is a parameter. Bedrock is the switchboard.

Why does this framing matter operationally?

1. **You swap models with a string change, not a re-integration.** With the **Converse API**, the request and response shapes are model-agnostic. Moving from Claude Haiku to Llama is changing the `modelId` argument — your message-building, tool-definition, and streaming code stays the same. That is the entire value proposition: Bedrock decouples your application from any single model vendor. (`InvokeModel`, the older API, requires per-model request bodies — use Converse for new code precisely so you keep the router benefit.)

2. **You provision *access*, not *infrastructure*.** There is no endpoint to size, no instance to keep warm, no GPU to pay for at 3 a.m. when traffic is zero. You enable model access once, then pay **per token** — per 1,000 input tokens and per 1,000 output tokens, priced per model. Zero traffic costs zero dollars (on-demand). This is the polar opposite of a SageMaker real-time endpoint, which bills by the instance-hour whether or not anyone calls it. Hold that contrast; it is the whole of Lecture 2.

3. **Routing extends to capacity and Region.** Bedrock's **inference profiles** (the `us.anthropic.claude-...` IDs) route a request across multiple Regions to find capacity, improving throughput and availability without you managing failover. Again: routing, not a model.

Here is the minimal Converse call from Python (`boto3`), the shape the challenge uses:

```python
import boto3

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# The model is an argument. Change this string -> different model, same code.
MODEL_ID = "us.anthropic.claude-3-5-haiku-20241022-v1:0"  # a cross-Region inference profile

response = bedrock.converse(
    modelId=MODEL_ID,
    messages=[
        {
            "role": "user",
            "content": [{"text": "Classify the sentiment of this review as "
                                 "positive, negative, or neutral. Reply with one word.\n\n"
                                 "Review: The battery lasts two days and the screen is gorgeous."}],
        }
    ],
    inferenceConfig={"maxTokens": 8, "temperature": 0.0},
)

text = response["output"]["message"]["content"][0]["text"].strip()
usage = response["usage"]  # {'inputTokens': N, 'outputTokens': M, 'totalTokens': N+M}
print(text, usage)
```

Two things to internalize from this snippet. First, `usage` comes back on every call — Bedrock tells you exactly how many input and output tokens you were billed for. **Read that number.** It is your cost, the same way bytes-scanned was your Athena cost. Second, `temperature=0.0` and `maxTokens=8` for a classification task: you do not pay for a paragraph when you asked for one word, and a deterministic temperature makes the latency and cost reproducible for the comparison you will do Friday.

So when the challenge asks "self-hosted SageMaker endpoint or managed Bedrock?", the question is really: *do I want to pay per instance-hour for a model I control and host (SageMaker), or per token for a model someone else hosts and routes (Bedrock)?* That is a cost-and-latency decision with a break-even point, and computing that break-even is the work of Lecture 2 and the Friday challenge.

## 1.8 — What you should be able to do now

After this lecture and the Monday/Tuesday/Wednesday exercises you should be able to:

- Draw the three layers of the lakehouse and name the catalog as the seam.
- Configure a Firehose buffering policy and justify the freshness-vs-small-files trade-off you chose.
- Run a Glue crawler for discovery and list three ways it can lie to you.
- Read the Athena bytes-scanned footer and convert it to dollars in your head.
- Convert a JSON table to partitioned Parquet with CTAS and configure partition projection.
- Set a workgroup data-scanned cutoff.
- Pick Athena vs Redshift vs OpenSearch for a given question.
- Explain to a skeptical colleague why Bedrock is a router and not a model, and why that means swapping models is a string change.

## 1.9 — Exercises that go with this lecture

- **Exercise 1 — Firehose → Glue → Athena.** Land NDJSON, crawl it, query it. Read the bytes-scanned footer for the first time.
- **Exercise 2 — Partition + Parquet + measure.** Convert to partitioned Parquet, add projection, re-query, and write down the before/after cost and latency.

Bring your three numbers (raw, partitioned, Parquet) to Friday. The decision frame in Lecture 2 assumes you have felt the difference, not just read about it.
