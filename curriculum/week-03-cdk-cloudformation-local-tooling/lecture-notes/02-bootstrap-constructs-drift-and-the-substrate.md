# Lecture 2 — `cdk bootstrap` and the Chicken-and-Egg IAM Problem: Constructs, Drift Detection, and the IaC Substrate

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can explain what `cdk bootstrap` creates and why it must exist, choose the right construct level (L1/L2/L3) for any resource, detect and read CloudFormation drift, and describe the deploy mechanics CDK hides.

If Lecture 1 told you *what* CDK is (a CloudFormation template generator), Lecture 2 tells you *how it gets that template into your account safely* — and why that "safely" hides one of the more interesting IAM puzzles in AWS.

> The one sentence: **`cdk bootstrap` exists because to deploy infrastructure you need a privileged role to deploy *with*, but a role is itself infrastructure — so something has to create the first role before CDK can use it.** That is the chicken-and-egg problem, and the CDKToolkit stack is the egg.

---

## 1. The chicken-and-egg IAM problem, stated precisely

Walk through the deploy from first principles. You want `cdk deploy` to create a VPC, a bucket, a KMS key, and a Lambda in your `dev` account. For CloudFormation to create those, *something* has to call the CloudFormation API with permissions to create VPCs, buckets, keys, and functions. There are two ways to grant those permissions:

1. **Give your human/CI credentials god-mode directly.** Every developer and every CI runner gets `AdministratorAccess` so they can create anything. This is what naive teams do, and it is exactly the least-privilege failure Week 2 spent a week teaching you to avoid. Now the blast radius of a leaked developer laptop is your entire account.

2. **Create a single, narrowly-trusted deployment role that CloudFormation assumes**, and let humans/CI hold only `sts:AssumeRole` on that one role plus the ability to start a deploy. The deploy role has the broad permissions; the humans do not. The humans can *ask* for a deploy but cannot *be* the deployer.

Option 2 is correct, and it is exactly what `cdk bootstrap` sets up. But notice the bootstrap problem: **that deployment role is itself a piece of infrastructure.** You cannot use CDK to create the role that CDK needs in order to run, because to create it you would need... the role. Something outside the normal CDK loop, running with elevated permissions *one time*, has to lay down the deployment roles. That one-time act is `cdk bootstrap`.

```
       ┌──────────────────────────────────────────────────────┐
       │  cdk bootstrap   (run ONCE per account+region,        │
       │                   with admin-ish creds)               │
       │                                                       │
       │   deploys the "CDKToolkit" CloudFormation stack:      │
       │     • staging S3 bucket  (for assets/templates)       │
       │     • staging ECR repo   (for Docker image assets)    │
       │     • 4 IAM roles  (deploy / file-pub / image-pub /   │
       │                     lookup)                           │
       │     • a KMS key for the staging bucket                │
       │     • an SSM parameter recording the bootstrap version│
       └───────────────────────────┬──────────────────────────┘
                                    │  now the roles exist
                                    ▼
       ┌──────────────────────────────────────────────────────┐
       │  cdk deploy   (run MANY times, with only               │
       │               sts:AssumeRole on the deploy role)       │
       │                                                       │
       │   1. assume the file-publishing role → upload the     │
       │      synthesized template + assets to the staging     │
       │      bucket                                           │
       │   2. assume the deploy role → CloudFormation          │
       │      create/execute change set                        │
       │   3. CloudFormation assumes the cfn-exec role to       │
       │      actually create your resources                   │
       └──────────────────────────────────────────────────────┘
```

This is the whole reason a CDK deploy "needs three roles," which is the exact confusion the Week 2 README promised to clear up. Now you know.

---

## 2. The four roles bootstrap creates

When you run `cdk bootstrap aws://<account-id>/<region>`, the CDKToolkit stack creates these IAM roles (names abbreviated; the real names are prefixed with `cdk-<qualifier>-`):

| Role | Trusted by | Purpose | Default permissions |
|------|-----------|---------|---------------------|
| **deploy** (`...-deploy-role-...`) | Your CLI/CI principal (via `sts:AssumeRole`) | Orchestrates the deploy: creates/executes the CloudFormation change set | Permission to act on CloudFormation + pass the cfn-exec role |
| **cfn-exec** (`...-cfn-exec-role-...`) | The CloudFormation service | The role CloudFormation *itself* assumes to create your resources | **`AdministratorAccess` by default** — this is the dangerous one |
| **file-publishing** (`...-file-publishing-role-...`) | Your CLI/CI principal | Uploads synthesized templates and file assets to the staging bucket | S3 write to the staging bucket + KMS |
| **image-publishing** (`...-image-publishing-role-...`) | Your CLI/CI principal | Pushes Docker image assets to the staging ECR repo | ECR push to the staging repo |
| **lookup** (`...-lookup-role-...`) | Your CLI/CI principal | Read-only context lookups (`Vpc.fromLookup`, AZ queries) during synth | Broad read-only |

Five roles, technically (people say "four" and forget the lookup role). The one to stare at is **cfn-exec**, which defaults to `AdministratorAccess`. That means: anyone who can start a CDK deploy can, transitively, create *any* resource in the account, because the role CloudFormation uses to execute is an admin. This is fine in a sandbox `dev` account. It is **not** fine in `prod`.

### 2.1 Locking down the cfn-exec role in prod

For `prod` you scope the cfn-exec role down with a **permissions boundary** (the exact tool from Week 2). The bootstrap command takes flags:

```bash
cdk bootstrap aws://111122223333/us-east-1 \
  --cloudformation-execution-policies "arn:aws:iam::aws:policy/PowerUserAccess" \
  --custom-permissions-boundary crunch-cdk-exec-boundary \
  --profile crunch-prod \
  --qualifier crunchprd
```

- `--cloudformation-execution-policies` replaces the default `AdministratorAccess` with a policy (or several) you choose. `PowerUserAccess` (everything except IAM writes) is a common, less-terrifying choice.
- `--custom-permissions-boundary` attaches a boundary to every role the cfn-exec role might create, capping what *those* roles can do. This is how you stop a CDK deploy from minting an admin role inside your prod account.
- `--qualifier` namespaces the bootstrap so you can have multiple, independent bootstrap stacks in one account (e.g. one per team). The default qualifier is `hnb659fds` — a deliberately random string so it never collides. If you use a custom qualifier, your CDK app must declare it (`@aws-cdk/core:bootstrapQualifier` in `cdk.json` or a `DefaultStackSynthesizer`).

> **The senior-engineer rule.** `cdk bootstrap` is a privileged, deliberate, one-time act per account+region, performed by someone who is *allowed* to be admin for that minute. It is **not** something your daily-driver developer role should be able to run. Treat re-bootstrapping like a change to IAM: reviewed, logged, intentional. A surprising number of "how did this account get an admin role?" incidents trace back to a careless `cdk bootstrap`.

### 2.2 The bootstrap version and `BootstrapVersion`

The CDKToolkit stack writes its version to an SSM parameter (`/cdk-bootstrap/<qualifier>/version`). Your synthesized templates include a `Rules` section that checks this version is recent enough. When you upgrade `aws-cdk-lib` and it needs a newer bootstrap, `cdk deploy` fails fast with "this stack uses assets, so the toolkit stack must be deployed... bootstrap version X required, found Y." The fix is to re-run `cdk bootstrap`. This is the most common bootstrap error you will hit; now you know it is benign and the fix is one command.

---

## 3. Constructs: L1, L2, L3

A **construct** is a node in the CDK tree. There are exactly three levels, and choosing the right one is a real engineering decision.

### 3.1 L1 — `Cfn*` — the 1:1 CloudFormation mapping

L1 constructs are named `Cfn<Resource>` (`CfnBucket`, `CfnFunction`, `CfnVPC`). They are **auto-generated from the CloudFormation resource specification** and map one-to-one to CloudFormation resources. Every property is exactly the CloudFormation property, in the same casing, with the same required/optional shape. No defaults, no helpers, no `grant*` methods.

```typescript
import { CfnBucket } from 'aws-cdk-lib/aws-s3';

new CfnBucket(this, 'RawBucket', {
  bucketName: 'my-explicit-name',
  versioningConfiguration: { status: 'Enabled' },
  bucketEncryption: {
    serverSideEncryptionConfiguration: [
      { serverSideEncryptionByDefault: { sseAlgorithm: 'aws:kms' } },
    ],
  },
});
```

**Use L1 when:** an L2 does not exist yet (a brand-new AWS feature), or the L2 does not expose a property you need (the escape hatch). You will reach for L1 rarely, but you must know it exists, because when CDK's abstraction leaks, L1 is the floor you stand on.

### 3.2 L2 — the curated, opinionated layer — your daily driver

L2 constructs (`Bucket`, `Function`, `Vpc`, `Key`) are hand-written by the CDK team and AWS. They add:

- **Sane defaults** a senior engineer would have chosen (the `DeletionPolicy: Retain` on a bucket, encryption on, public access blocked).
- **`grant*` methods** that write least-privilege IAM for you.
- **Helper methods** (`bucket.addLifecycleRule(...)`, `vpc.selectSubnets(...)`, `key.grantDecrypt(...)`).
- **Type-safe enums** instead of magic strings (`BucketEncryption.KMS` instead of `'aws:kms'`).

```typescript
import { Bucket, BucketEncryption, BlockPublicAccess } from 'aws-cdk-lib/aws-s3';
import { Duration } from 'aws-cdk-lib';

const bucket = new Bucket(this, 'Data', {
  encryption: BucketEncryption.KMS,        // creates a KMS key automatically
  enforceSSL: true,                         // adds an aws:SecureTransport deny policy
  blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
  versioned: true,
  lifecycleRules: [
    { transitions: [{ storageClass: StorageClass.INFREQUENT_ACCESS, transitionAfter: Duration.days(30) }] },
  ],
});

bucket.grantRead(myLambda);  // writes s3:GetObject + kms:Decrypt, scoped, for you
```

**Use L2 by default.** ~95% of your CDK code is L2. If you find yourself writing L1, ask whether you missed an L2.

### 3.3 L3 — patterns — assembled architectures

L3 constructs (also called "patterns") compose multiple L2 constructs into a working architecture. `aws-ecs-patterns.ApplicationLoadBalancedFargateService` is the canonical example: it stands up an ALB, listeners, target group, Fargate service, task definition, security groups, and IAM roles from a handful of inputs.

```typescript
import { ApplicationLoadBalancedFargateService } from 'aws-cdk-lib/aws-ecs-patterns';

new ApplicationLoadBalancedFargateService(this, 'Service', {
  cluster,
  cpu: 256,
  memoryLimitMiB: 512,
  desiredCount: 2,
  taskImageOptions: { image: ContainerImage.fromRegistry('nginx') },
});
```

**Use L3 when** it matches your architecture exactly. The danger of L3 is that it is opinionated *for you*; the moment your requirements diverge from the pattern's assumptions, you are fighting it, and you are often better dropping to L2 and assembling the pieces yourself. L3 is a fantastic accelerator for the common case and a trap for the uncommon one. We use L2 throughout this course and reach for L3 only where the pattern is an exact fit.

### 3.4 The escape hatch — when an L2 won't let you set something

Sometimes an L2 does not expose a CloudFormation property you need. You do not abandon the L2 — you reach *through* it to the underlying L1 via `node.defaultChild` and set the raw property:

```typescript
const bucket = new Bucket(this, 'Data', { versioned: true });

// Reach the underlying CfnBucket and set a property the L2 doesn't expose.
const cfnBucket = bucket.node.defaultChild as CfnBucket;
cfnBucket.addPropertyOverride('AccelerateConfiguration.AccelerationStatus', 'Enabled');
```

`addPropertyOverride` (and `addOverride`, `addDeletionOverride`) let you patch the synthesized template directly. This is the pressure-release valve that means CDK can *never* fully block you: worst case, you drop to the raw template. Use it sparingly; every override is a place where the L2's invariants no longer hold.

---

## 4. Logical IDs, renames, and the "I deleted prod by renaming a variable" footgun

Recall from Lecture 1 that CDK derives each resource's CloudFormation **logical ID** from the construct's *path* in the tree, plus an 8-char hash. This has a consequence that has destroyed real production data:

```typescript
new Bucket(this, 'Data');         // logical ID: Data6E1F4D8F
// ...later, you "clean up" by renaming:
new Bucket(this, 'DataBucket');   // logical ID: DataBucketA1B2C3D4 — A DIFFERENT RESOURCE
```

To CloudFormation, the second is a *different* logical ID, which means: **delete the bucket named `Data...` and create a new one named `DataBucket...`.** If the bucket held data and did not have `DeletionPolicy: Retain`, the data is gone. The L2 `Bucket` defaults to `Retain` precisely to blunt this, but many resources do not, and a rename of a DynamoDB table or an RDS instance is a genuinely dangerous change.

The defenses, in order:

1. **Don't rename construct IDs casually.** A construct ID is a stable identity, not a label. Treat renaming one like renaming a database table.
2. **Read the change set before deploying.** `cdk deploy` prints `Resources` with `[+]`, `[-]`, `[~]` markers. A `[-]` on a stateful resource is a stop-the-line moment. `cdk diff` shows it without deploying.
3. **Use `DeletionPolicy: Retain` / `RemovalPolicy.RETAIN`** on every stateful resource (buckets, tables, keys, databases). It means "if CloudFormation wants to delete this, orphan it instead." You lose the auto-cleanup but you keep your data.
4. **For a deliberate logical-ID change without replacement**, use `overrideLogicalId` to pin the old ID, or a CloudFormation resource import. Advanced; out of scope this week but know the words.

---

## 5. The deploy mechanics CDK hides

When you type `cdk deploy`, here is the sequence, end to end:

1. **Synth.** CDK runs your program, builds the construct tree, and writes `cdk.out/` — templates plus any *assets* (Lambda code zips, Docker images, files). Each asset gets a content hash for its name.
2. **Asset publishing.** CDK assumes the **file-publishing** (and **image-publishing**, if there are Docker assets) role and uploads templates and assets to the staging bucket / ECR repo created by bootstrap. Asset names are content hashes, so re-uploading an unchanged asset is a no-op.
3. **Change set creation.** CDK assumes the **deploy** role and calls `CreateChangeSet` against CloudFormation with the new template. CloudFormation computes the diff.
4. **Approval.** Depending on `--require-approval`, CDK may pause and ask you to confirm (the default is to prompt on IAM/security-sensitive changes — `--require-approval broadening`).
5. **Execution.** CDK calls `ExecuteChangeSet`. CloudFormation assumes the **cfn-exec** role and creates/updates/deletes resources in dependency order, streaming events back. CDK tails them and prints progress.
6. **Outputs.** On success, CDK prints the stack outputs (e.g. your bucket name, your function ARN).

Two flags worth knowing now:

- `cdk diff` runs steps 1–3 (create change set, show it) without executing. **Run `cdk diff` before every `cdk deploy`** the way you `git diff` before `git commit`.
- `cdk deploy --hotswap` skips CloudFormation entirely for certain changes (Lambda code, ECS task definitions, Step Functions definitions) and patches the resource directly via the AWS API. It is **dramatically faster** (seconds instead of minutes) and **dev-only** — it leaves your CloudFormation stack drifted (see §6), which is exactly why you never use it in prod. It is the single biggest quality-of-life win in the local dev loop. CDK prints a loud warning when you use it; heed it.

---

## 6. Drift detection — the hidden tax of IaC

**Drift** is the gap between what your IaC says is deployed and what is *actually* deployed. It happens when something changes a resource out-of-band — someone edits a security group in the console during an incident, a `--hotswap` deploy patches a Lambda, an auto-remediation tool flips a setting, a different IaC tool touches the same resource. CloudFormation does not know about the change; its template still describes the old state; your IaC is now lying.

Drift is not hypothetical. It is the **single most common operational pathology of IaC in practice.** The console is right there during an incident, someone makes "a quick fix," forgets to back-port it to the IaC, and three weeks later a routine `cdk deploy` *reverts* the fix because the template never learned about it. Catching drift early is an operational discipline, not a nice-to-have.

CloudFormation has built-in drift detection:

```bash
# Kick off a drift detection scan (asynchronous).
DRIFT_ID=$(aws cloudformation detect-stack-drift \
  --stack-name CrunchIacStarter-dev \
  --profile crunch-dev \
  --query StackDriftDetectionId --output text)

# Poll until the scan completes.
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id "$DRIFT_ID" \
  --profile crunch-dev

# Once DETECTION_COMPLETE, list the drifted resources.
aws cloudformation describe-stack-resource-drifts \
  --stack-name CrunchIacStarter-dev \
  --stack-resource-drift-status-filters MODIFIED DELETED \
  --profile crunch-dev
```

The output for a drifted resource shows `StackResourceDriftStatus: MODIFIED` and a `PropertyDifferences` array with `ExpectedValue` vs `ActualValue` per property. That is the report you read in the challenge after you mutate a resource in the console.

What you do about drift:

- **`cdk diff` against reality** does *not* catch console drift by itself — `cdk diff` compares your code to the *deployed template*, not to actual resource state. You need CloudFormation's drift detection (above) to compare the template to reality.
- **The fix-forward discipline:** either re-apply your IaC (`cdk deploy`, which reverts the drift back to the template) *if the drift was an accident*, or update your IaC to match reality *if the out-of-band change was intentional* and then deploy. Never leave a stack drifted; a drifted stack is a stack whose next deploy is a surprise.
- **Detect drift in CI** on a schedule (e.g. a nightly Lambda that runs `detect-stack-drift` and alerts on any `MODIFIED`). Week 12 wires this into observability. This week you just learn to run it by hand and read it.

> The OpenTofu equivalent of drift detection is `tofu plan` (or `tofu plan -refresh-only`), which refreshes state from reality and shows you the delta. This is one of the structural differences you note in Exercise 3: Terraform's plan *inherently* refreshes against reality, while CloudFormation's deploy trusts its own recorded state until you explicitly ask for a drift scan.

---

## 7. CDK Pipelines — self-mutating delivery

The last substrate piece. `pipelines.CodePipeline` (the modern construct, not the older `CdkPipeline`) builds an AWS CodePipeline that:

1. Pulls source from GitHub/CodeCommit.
2. Runs a `synth` step (`npm ci && npx cdk synth`) to produce `cdk.out`.
3. **Self-mutates** — updates the pipeline itself from the new `cdk.out` before deploying anything else, so a change to the pipeline definition takes effect on the *same* run.
4. Deploys your stacks, grouped into **stages** (a deployable unit, often one per account/region) and **waves** (stages that deploy in parallel).

```typescript
import { CodePipeline, CodePipelineSource, ShellStep } from 'aws-cdk-lib/pipelines';

const pipeline = new CodePipeline(this, 'Pipeline', {
  selfMutation: true,
  synth: new ShellStep('Synth', {
    input: CodePipelineSource.gitHub('your-org/crunch-iac-starter', 'main'),
    commands: ['npm ci', 'npx cdk synth'],
  }),
});

pipeline.addStage(new AppStage(this, 'Dev', {
  env: { account: '111122223333', region: 'us-east-1' },
}));
```

The self-mutation is the clever bit: the pipeline is itself a CDK stack, so the pipeline deploys the pipeline. You change the pipeline's definition in code, push, and the running pipeline updates itself before continuing. For the multi-account topology you built in Week 1, this is the deploy backbone — one pipeline in a tooling account, deploying into `dev` and `prod` via cross-account roles (which is exactly what bootstrap's `--trust` flag is for). We build a single-stage version in the mini-project so you have touched it; the multi-account version arrives in Week 7's CI/CD lab.

---

## 7a. The drift remediation playbook

Detecting drift is the easy half. Knowing what to do when you find it is the half that separates an operator from a dashboard-watcher. When `detect-stack-drift` comes back `DRIFTED`, walk this decision tree — do not improvise, because the wrong move (a panicked re-deploy, or a manual "fix" that creates *more* drift) is how a five-minute incident becomes a one-hour one.

1. **Identify what drifted and how.** `aws cloudformation describe-stack-resource-drifts --stack-name X --query "StackResourceDrifts[?StackResourceDriftStatus!='IN_SYNC']"`. For each drifted resource you get `MODIFIED`, `DELETED`, or `NOT_CHECKED`, plus a property-by-property diff (`PropertyDifferences`) showing `ExpectedValue` vs `ActualValue`. Read it before you touch anything.

2. **Decide: is the live state or the template the source of truth?** This is the whole judgment call. Two cases:
   - *The console change was a mistake or an unauthorized edit.* The **template** is the truth. Fix forward: run `cdk deploy` (or `tofu apply`), which re-asserts the declared configuration and overwrites the drift. This is the default and the right answer roughly nine times out of ten. CloudFormation does not have a "revert to template" button — `deploy` *is* that button.
   - *The console change was a legitimate emergency fix that needs to persist* (someone widened a security group during an incident, say). The **live state** is the truth for now. Update the IaC code to match reality, `cdk diff` to confirm the diff is now empty, then deploy so the template and reality agree again. Never leave reality ahead of code; that is how the next deploy silently reverts an emergency fix and re-opens the incident.

3. **Never hand-edit to "fix" drift.** Reaching into the console to manually undo a drifted property feels fast and creates a second piece of drift. Everything goes back through IaC. The console is read-only in your operational discipline, even when AWS lets you click.

4. **Capture the lesson.** A drifted resource is a signal that something — a human, a script, another tool — is writing to your account outside IaC. Find it. The fix-forward `deploy` closes *this* drift; an SCP, a permission boundary (Week 2), or a `detect-stack-drift` CI job (this week's homework) prevents the *next* one.

The asymmetry to keep in your head: **CloudFormation drift is a snapshot you must explicitly request; OpenTofu surfaces the same information on every `plan` because it refreshes.** Neither tool *remediates* automatically — both make you choose source-of-truth and re-apply. The difference is only in how loudly the tool tells you there is a choice to make. In a CDK shop, that loudness is your responsibility: schedule `detect-stack-drift` (EventBridge rule on a cron, or a CI job) or you will not hear about drift until it breaks a deploy.

---

## 8. Putting it together — the substrate diagram

Here is the whole Week 3 mental model on one page:

```
  YOUR CODE (TypeScript / Python CDK)
        │  cdk synth
        ▼
  cdk.out/  (CloudFormation template JSON + assets)
        │  cdk deploy
        │    ├─ assume file-publishing role → upload to staging bucket  ← bootstrap made this
        │    ├─ assume deploy role → CreateChangeSet                      ← bootstrap made this
        │    └─ ExecuteChangeSet
        ▼
  CloudFormation service  (the substrate; owns the state, server-side)
        │  assumes cfn-exec role                                         ← bootstrap made this
        ▼
  Real AWS resources: VPC, KMS key, S3 bucket, Lambda
        │
        │  ...someone edits a resource in the console...
        ▼
  DRIFT  ← caught by  aws cloudformation detect-stack-drift

  ── OR, the same stack via OpenTofu ──
  YOUR CODE (HCL)  →  tofu plan (refreshes from reality)  →  tofu apply  →  Real AWS resources
                      (state file owns the mapping, client-side)
```

The CDK path rides CloudFormation and needs bootstrap. The OpenTofu path rides a state file and AWS API calls and needs a state backend instead. Same resources, two substrates. You will build both this week and diff the results.

---

## 9. Recap

You should now be able to:

- Explain the chicken-and-egg IAM problem and why `cdk bootstrap` exists.
- Name the roles bootstrap creates (deploy, cfn-exec, file-publishing, image-publishing, lookup) and identify cfn-exec as the dangerous default-admin one.
- Lock down the cfn-exec role for prod with `--cloudformation-execution-policies` and `--custom-permissions-boundary`.
- Choose L1 vs L2 vs L3 for a resource, and use `addPropertyOverride` as an escape hatch.
- Explain why renaming a construct ID can delete a resource, and the four defenses.
- Walk through the six steps of `cdk deploy` and say what `cdk diff` and `--hotswap` do.
- Run CloudFormation drift detection, read the report, and state the fix-forward discipline.
- Describe a self-mutating CDK pipeline and what stages and waves are.

Next, you build all of this: a TS CDK app, its Python twin, and the OpenTofu equivalent, then a LocalStack loop and a drift drill. Head to the [exercises](../exercises/README.md).

---

## References

- *CDK bootstrapping*: <https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html>
- *Bootstrapping environments — customizing*: <https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping-customizing.html>
- *Constructs (L1/L2/L3)*: <https://docs.aws.amazon.com/cdk/v2/guide/constructs.html>
- *CDK escape hatches*: <https://docs.aws.amazon.com/cdk/v2/guide/cfn_layer.html>
- *Logical IDs and the construct tree*: <https://docs.aws.amazon.com/cdk/v2/guide/identifiers.html>
- *CloudFormation drift detection*: <https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html>
- *CDK Pipelines*: <https://docs.aws.amazon.com/cdk/v2/guide/cdk_pipeline.html>
- *Permissions boundaries*: <https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html>
