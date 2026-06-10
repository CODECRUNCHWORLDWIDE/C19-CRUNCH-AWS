# Week 9 — Resources

Most of this page is free. The AWS documentation, the re:Invent talks on YouTube, the AWS blog, and the open-source comparator projects (ScyllaDB, Cassandra, FoundationDB) are all free without an account. The one paid item is *The DynamoDB Book* by Alex DeBrie — it is the single best book on single-table design and worth its price, but you can complete this week from the free material alone. Where a free equivalent exists for a paid resource, it is noted.

Every link was checked against its 2026 home. Bookmarks rot; if a link 404s, search the title — these are all canonical pieces and they reappear.

## Required reading (work it into your week)

- **DynamoDB Developer Guide — "Core components" (tables, items, attributes, primary key, secondary indexes)**:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.CoreComponents.html>
- **DynamoDB Developer Guide — "Partitions and data distribution"** (the per-partition 3,000 RCU / 1,000 WCU ceiling that causes every hot-partition story):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.Partitions.html>
- **DynamoDB Developer Guide — "Best practices for designing and using partition keys effectively"** (write-sharding, adaptive capacity, burst):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html>
- **DynamoDB Developer Guide — "Best practices for using secondary indexes"** (GSI vs LSI, sparse indexes, projection):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-indexes.html>
- **DynamoDB Developer Guide — "Using sort keys to organize data" (the single-table modeling chapter)**:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-sort-keys.html>
- **DynamoDB Developer Guide — "Modeling relational data" (adjacency lists, the single-table examples)**:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-relational-modeling.html>
- **DynamoDB Developer Guide — "Read/write capacity mode" (on-demand vs provisioned, the RCU/WCU definitions)**:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWriteCapacityMode.html>
- **DynamoDB Developer Guide — "Managing throughput capacity with auto scaling"**:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/AutoScaling.html>
- **DynamoDB Developer Guide — "Change data capture with Streams"**:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html>
- **DynamoDB Developer Guide — "Time to Live (TTL)"**:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html>
- **DynamoDB Developer Guide — "Condition expressions"** (conditional writes, `attribute_not_exists`):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html>
- **DynamoDB Developer Guide — "Managing complex workflows with transactions"** (`TransactWriteItems`, idempotency token, 2× cost):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html>

## The single-table canon — Rick Houlihan and Alex DeBrie

- **Rick Houlihan — "Advanced Design Patterns for Amazon DynamoDB" (re:Invent 2018, DAT401)** — the talk that started it. This is the one to watch first. Houlihan whiteboards the single-table pattern live:
  search YouTube for "AWS re:Invent 2018 DAT401 Advanced Design Patterns DynamoDB".
- **Rick Houlihan — "Advanced Design Patterns for DynamoDB" (re:Invent 2019, DAT403-R)** — the refined, denser version with more access-pattern examples:
  search YouTube for "AWS re:Invent 2019 DAT403 Advanced Design Patterns DynamoDB".
- **Rick Houlihan — "Data modeling with DynamoDB" (re:Invent 2020, DAT410)** — the last of the canonical AWS-era talks before he left for MongoDB:
  search YouTube for "AWS re:Invent 2020 DAT410 Data modeling DynamoDB".
- **Alex DeBrie — *The DynamoDB Book*** (paid, ~$79, the definitive single-table reference; chapters on strategies for one-to-many, many-to-many, and migrations are the best in print):
  <https://www.dynamodbbook.com/>
- **Alex DeBrie — "The What, Why, and When of Single-Table Design with DynamoDB"** (free, the best single article on the topic; read this if you buy nothing):
  <https://www.alexdebrie.com/posts/dynamodb-single-table/>
- **Alex DeBrie — "DynamoDB Guide"** (free companion site to the book, with worked key-design walkthroughs):
  <https://www.dynamodbguide.com/>
- **Alex DeBrie — "SQL, NoSQL, and Scale: how DynamoDB scales where relational databases don't"**:
  <https://www.alexdebrie.com/posts/dynamodb-no-bad-queries/>

## NoSQL Workbench and tooling

- **NoSQL Workbench for DynamoDB** — the official GUI for designing single-table models, visualizing GSIs, and generating CRUD code. Install it; you will draw your Week 9 table in it:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/workbench.html>
- **DynamoDB local (Docker image)** — run the engine offline for the entire week; the load tests are the only thing that needs real AWS:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html>
- **`amazon/dynamodb-local` on Docker Hub**:
  <https://hub.docker.com/r/amazon/dynamodb-local>
- **LocalStack — DynamoDB + Streams + Lambda emulation** (when you want the Streams → Lambda path offline):
  <https://docs.localstack.cloud/user-guide/aws/dynamodb/>

## CDK, CloudFormation, and OpenTofu references

- **AWS CDK v2 — `aws-cdk-lib/aws-dynamodb` (TableV2, the Global-Tables-aware L2 construct)**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_dynamodb-readme.html>
- **AWS CDK v2 — `TableV2` API reference**:
  <https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_dynamodb.TableV2.html>
- **CloudFormation — `AWS::DynamoDB::GlobalTable` resource reference** (the modern replacement for `AWS::DynamoDB::Table`):
  <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-dynamodb-globaltable.html>
- **OpenTofu / Terraform AWS provider — `aws_dynamodb_table` resource**:
  <https://search.opentofu.org/provider/hashicorp/aws/latest/docs/resources/dynamodb_table>
- **OpenTofu / Terraform AWS provider — `aws_appautoscaling_target` and `aws_appautoscaling_policy`** (provisioned-mode autoscaling):
  <https://search.opentofu.org/provider/hashicorp/aws/latest/docs/resources/appautoscaling_policy>

## SDK references

- **`boto3` — DynamoDB client and resource** (we use both the low-level client and the `Table` resource):
  <https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html>
- **`boto3` — the `TypeDeserializer` / `TypeSerializer` in `boto3.dynamodb.types`** (decoding the wire format in Stream records):
  <https://boto3.amazonaws.com/v1/documentation/api/latest/reference/customizations/dynamodb.html>
- **AWS SDK for JavaScript v3 — `@aws-sdk/lib-dynamodb` `DynamoDBDocumentClient`** (the marshalling document client for the TypeScript exercises):
  <https://docs.aws.amazon.com/AWSJavaScriptSDK/v3/latest/Package/-aws-sdk-lib-dynamodb/>
- **AWS Lambda Powertools for Python — `BatchProcessor` and the DynamoDB Streams data class** (the production pattern for Streams → Lambda with partial-batch-failure reporting):
  <https://docs.powertools.aws.dev/lambda/python/latest/utilities/batch/>

## Capacity and cost

- **DynamoDB pricing page** (the source of every dollar figure in this week's cost report — read the on-demand vs provisioned tables carefully):
  <https://aws.amazon.com/dynamodb/pricing/>
- **AWS Pricing Calculator** (build your steady-state / burst / idle scenarios here for the challenge):
  <https://calculator.aws/#/createCalculator/DynamoDB>
- **DynamoDB Developer Guide — "Reserved capacity"** (the deepest discount for steady provisioned workloads):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/reservedcapacity.html>
- **DynamoDB Developer Guide — "DAX: in-memory acceleration"** (when the microsecond cache earns its cost):
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.html>
- **DynamoDB Developer Guide — "Global Tables: multi-Region replication"**:
  <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html>

## Open-source comparators

- **ScyllaDB documentation** (the C++, shard-per-core, Cassandra- and DynamoDB-compatible store; read the "Alternator" docs for its DynamoDB-API mode):
  <https://docs.scylladb.com/>
- **ScyllaDB Alternator — the DynamoDB-compatible API** (run the same single-table model against Scylla and benchmark it):
  <https://docs.scylladb.com/manual/stable/alternator/alternator.html>
- **Apache Cassandra — "Data modeling" documentation** (the wide-column ancestor; query-first modeling that single-table DynamoDB borrows from):
  <https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html>
- **FoundationDB — "Anatomy of a transaction" and the layer concept** (the ordered, transactional KV store that DynamoDB-like systems are sometimes built on; Snowflake and Apple run it):
  <https://apple.github.io/foundationdb/transaction-manifesto.html>
- **DynamoDB — the 2007 SOSP paper "Dynamo: Amazon's Highly Available Key-value Store"** (the ancestor of *all* of the above; note that DynamoDB-the-service is a different system from Dynamo-the-paper, but the lineage matters):
  <https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf>
- **"Amazon DynamoDB: A Scalable, Predictably Performant, and Fully Managed NoSQL Database Service" (USENIX ATC 2022)** — the paper on the *actual* DynamoDB service, including adaptive capacity and the burst/isolation mechanics:
  <https://www.usenix.org/conference/atc22/presentation/elhemali>

## Talks worth watching (all free, no account)

- **Alex DeBrie — "Data modeling with DynamoDB" (re:Invent 2021/2022, CMY304)** — the modern successor to the Houlihan talks, with the access-pattern-table methodology front and center:
  search YouTube for "AWS re:Invent DeBrie data modeling DynamoDB".
- **Jason Hunter / Pete Naylor — "Amazon DynamoDB deep dive: Advanced design patterns" (recent re:Invent)** — the current AWS-team version of the advanced-patterns talk:
  search YouTube for "re:Invent DynamoDB advanced design patterns".
- **"How Amazon DynamoDB scales" (the USENIX ATC 2022 talk)** — the authors present the service-internals paper:
  search YouTube for "USENIX ATC 2022 DynamoDB scalable predictably performant".

## How to use this resource list

The lectures cite specific URLs from this page at decision points. The links you should read end-to-end *this week* are:

1. **DynamoDB Developer Guide — "Best practices for designing and using partition keys effectively."** Foundational; do not skip. It is the source of truth for write-sharding and adaptive capacity.
2. **Alex DeBrie — "The What, Why, and When of Single-Table Design."** ~30 minutes, the clearest single explanation of the whole approach.
3. **One Houlihan re:Invent talk (2018 DAT401 is the best starting point).** ~60 minutes. Watch him whiteboard it; this is the lecture-1 framing in its original form.
4. **DynamoDB Developer Guide — "Read/write capacity mode."** ~20 minutes, decisive for the challenge's cost math.

The rest are reference material — bookmark and return when a specific question arises. The comparator docs (Scylla, Cassandra, FoundationDB) are for the homework and the quiz; skim them, do not study them.

---

*If a link rots, search the title — these are all canonical pieces and they reappear on the same authors' new homes.*
