# Mini-Project — The Crunch IaC Starter

> Produce a reusable infrastructure-as-code starter: the **VPC + KMS-encrypted S3 + Lambda** stack expressed in **TypeScript CDK (primary)**, **Python CDK**, and **OpenTofu**, with a **LocalStack-backed local test loop** that proves all three are equivalent and that the Lambda actually reads from the bucket. This scaffold and its dev loop are the substrate every subsequent lab in C19 deploys through.

This is the most important artifact you build before the capstone, and it is deliberately small. You already wrote the three stacks as exercises this week. The mini-project is the act of turning three throwaway exercise folders into one **reusable, tested, documented repository** that a teammate can clone and deploy in under five minutes — and that *you* will extend in Weeks 4, 6, 9, and 13 without rewriting.

Read the README's "substrate note" again before you start: when Week 4 adds VPC endpoints, it edits the VPC construct in this repo. When Week 6 adds replication and Object Lambda, it edits the bucket in this repo. When Week 9 needs a DynamoDB table, it lands in this repo. The capstone is deployed from a descendant of this monorepo. **A sloppy scaffold this week is a tax you pay every week after.** So spend the six hours. Make it clean.

**Estimated time:** ~6 hours (split across Saturday in the suggested schedule, building on the three exercises).

---

## What you will build

A single Git repository — call it `crunch-iac-starter` — that holds three independent implementations of the *same* logical stack plus the tooling to test them locally:

```
crunch-iac-starter/
├── README.md                         # how to deploy each variant + the dev loop
├── .gitignore                        # excludes cdk.out/, node_modules/, .venv/, *.tfstate, .terraform/
├── Makefile                          # one entry point: make synth | deploy-local | test | destroy
├── lambda/
│   └── read_object.py                # the SHARED Lambda handler (one copy, used by all three)
├── ts/                               # TypeScript CDK (primary)
│   ├── bin/crunch-iac-ts.ts
│   ├── lib/crunch-iac-ts-stack.ts
│   ├── cdk.json
│   ├── package.json
│   └── test/crunch-iac-ts-stack.test.ts   # fine-grained assertions on the synthesized template
├── py/                               # Python CDK
│   ├── app.py
│   ├── crunch_iac_py/crunch_iac_py_stack.py
│   ├── cdk.json
│   ├── requirements.txt
│   └── tests/test_synth.py           # assertions.Template parity checks
├── tofu/                             # OpenTofu
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── versions.tf
└── scripts/
    ├── localstack-up.sh              # start LocalStack with the docker socket mounted
    ├── seed-bucket.sh                # put hello.txt into the emulated bucket
    └── invoke-local.sh              # sam local invoke against the emulated bucket
```

The three implementations are intentionally redundant. The point is not DRY — the point is that you can stand in a design review and say, with evidence, "here is the same intent in three tools; here is what each one costs you." That sentence is worth more than any single working deploy.

---

## The shared stack (identical intent across all three tools)

This is the same stack you built in Exercises 1–3. Every implementation must produce, logically:

- A **VPC** at CIDR `10.42.0.0/16`, two AZs, public + private-isolated subnets, and **zero NAT Gateways**. NAT is the silent budget killer; we avoid it deliberately this week and add VPC endpoints in Week 4.
- A **KMS customer-managed key** with automatic rotation enabled, a description, and (in `dev`) a removal policy that schedules deletion rather than retaining.
- An **S3 bucket** that is: KMS-encrypted with that key, `BucketKeyEnabled` for cost, versioned, fully public-access-blocked, TLS-enforced (a bucket policy denying non-TLS access), with a lifecycle rule that transitions to Infrequent Access at 30 days, expires current objects at 365 days, and expires noncurrent versions at 90 days.
- A **Lambda** (Python 3.12, handler `read_object.handler`) with `BUCKET_NAME` in its environment and **least-privilege read access** to the bucket — `s3:GetObject` on the bucket plus `kms:Decrypt` on the key, and nothing more.

The Lambda handler is shared verbatim across all three. There is exactly one `lambda/read_object.py` in the repo, and all three stacks reference it by relative path. If you find yourself with three copies, stop and fix it.

---

## Rules

- **You may** reuse the code you wrote in Exercises 1, 2, and 3. That is the intended starting point — this mini-project is the act of consolidating and testing them, not writing them from scratch.
- **You may NOT** add a NAT Gateway, an internet-facing load balancer, or any always-on compute. The starter is near-zero-cost by design. The only lingering cost is the KMS key (\$1/month while it exists), and your `make destroy` schedules it for deletion.
- **You must** keep the Lambda handler in exactly one place (`lambda/read_object.py`) shared by all three implementations.
- **You must** provide a `Makefile` (or a `justfile`, or three thin shell scripts) so a newcomer runs `make synth`, `make test`, `make deploy-local`, `make destroy` without reading three separate toolchains' docs.
- **You must** run the **inner loop against LocalStack**, not real AWS. A single optional real-`dev` deploy is allowed for the "I saw the real thing" screenshot, but the tested loop is local and free.
- Pin your versions: `aws-cdk-lib` in `package.json` and `requirements.txt`, the AWS provider in `tofu/versions.tf`. Unpinned IaC is a future-you problem.

---

## Acceptance criteria

- [ ] A public GitHub repo named `c19-week-03-iac-starter-<yourhandle>`.
- [ ] Repo layout matches the tree above (one shared `lambda/`, three implementation folders, a `scripts/` and a `Makefile`).
- [ ] **TypeScript CDK** (`ts/`): `npm ci && npm run build && npx cdk synth` produces a template with **no unresolved tokens**, and `npm test` passes with at least **five fine-grained assertions** on the synthesized template (see "TS tests" below).
- [ ] **Python CDK** (`py/`): in a fresh `.venv`, `pip install -r requirements.txt && cdk synth` succeeds, and `pytest` passes with parity assertions against the same resource set.
- [ ] **OpenTofu** (`tofu/`): `tofu init && tofu validate && tofu plan` against LocalStack (via `tflocal` or the LocalStack provider endpoints) reports a clean plan with the expected resource count and **no errors**.
- [ ] **Template parity is demonstrated, not asserted.** Your README contains a short table comparing the TS-synthesized, Py-synthesized, and Tofu-planned resource *types and counts*, and one paragraph explaining the structural differences you observed (logical IDs, the bucket-policy shape, how each tool wrote the least-privilege IAM).
- [ ] **The dev loop works end-to-end against LocalStack:** `make deploy-local` deploys the TS stack to LocalStack, `make seed` puts `hello.txt` in the emulated bucket, and `make invoke-local` runs the Lambda with `sam local invoke` and prints a JSON result containing the object's size and preview.
- [ ] **The Lambda IAM is least-privilege in all three.** You can point, in each synthesized/planned artifact, to the `s3:GetObject` statement scoped to the bucket and the `kms:Decrypt` statement scoped to the key — and confirm there is no `s3:*` or `kms:*` wildcard.
- [ ] `make destroy` tears down whatever you deployed (LocalStack and, if used, real `dev`) and schedules the KMS key for deletion.
- [ ] The `README.md` includes: a one-paragraph description, the exact clone-to-deploy commands for each variant, the parity table, and a "Things I learned" section with at least three specific items.

---

## Suggested order of operations

Build incrementally. You already have the three stacks from the exercises; this is consolidation.

### Phase 1 — Repo skeleton and the shared handler (~45 min)

1. `mkdir crunch-iac-starter && cd crunch-iac-starter && git init`.
2. Create the directory tree above (empty files are fine for now).
3. Move your Exercise 1 `lambda/read_object.py` to the repo root `lambda/`. This is the single shared copy. Confirm it reads `BUCKET_NAME` from the environment and returns the object size and a preview.
4. Write a `.gitignore` that excludes `cdk.out/`, `node_modules/`, `.venv/`, `*.tfstate`, `*.tfstate.backup`, `.terraform/`, and `__pycache__/`. Never commit state or build output.
5. First commit: `repo skeleton + shared lambda handler`.

### Phase 2 — Land the TypeScript CDK variant (~1 h)

1. Move your Exercise 1 stack into `ts/`. Point `Code.fromAsset` at `'../lambda'` so it uses the shared handler, not a copy.
2. Confirm `npm run build && npx cdk synth` is clean.
3. Write `ts/test/crunch-iac-ts-stack.test.ts` using `aws-cdk-lib/assertions`. At minimum, assert (see snippet below): the KMS key has rotation enabled; the bucket blocks all public access; the bucket has the lifecycle rule; exactly one Lambda exists with runtime `python3.12`; the Lambda's role policy contains an `s3:GetObject` and a `kms:Decrypt` statement.
4. Commit: `ts cdk variant + template tests`.

### Phase 3 — Land the Python CDK variant (~1 h)

1. Move your Exercise 2 stack into `py/`. Point the asset at `../lambda` here too.
2. Create a clean `.venv`, `pip install -r requirements.txt`, confirm `cdk synth` is clean.
3. Write `py/tests/test_synth.py` using `aws_cdk.assertions.Template` mirroring the TS assertions — the same resource types and the same least-privilege IAM. This is the parity proof in code.
4. Commit: `py cdk variant + parity tests`.

### Phase 4 — Land the OpenTofu variant (~1 h)

1. Move your Exercise 3 HCL into `tofu/`, split sensibly across `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`.
2. Pin the AWS provider in `versions.tf`. Configure the provider's `endpoints` block (or use `tflocal`) so `tofu plan` targets LocalStack.
3. `tofu init && tofu validate && tofu plan`. Confirm the plan's resource count and that there are no errors.
4. Commit: `opentofu variant`.

### Phase 5 — The Makefile and the LocalStack loop (~1.5 h)

Wire the whole thing behind one entry point. A starting `Makefile`:

```makefile
# Makefile — one entry point for the Crunch IaC starter.
.PHONY: localstack-up synth test deploy-local seed invoke-local plan-tofu destroy

localstack-up:
	./scripts/localstack-up.sh

synth:
	cd ts && npx cdk synth >/dev/null && echo "ts synth ok"
	cd py && cdk synth >/dev/null && echo "py synth ok"

test:
	cd ts && npm test
	cd py && pytest -q

deploy-local: localstack-up
	cd ts && cdklocal bootstrap && cdklocal deploy --require-approval never

seed:
	./scripts/seed-bucket.sh

invoke-local:
	./scripts/invoke-local.sh

plan-tofu: localstack-up
	cd tofu && tofu init -input=false && tofu plan

destroy:
	-cd ts && cdklocal destroy --force
	-docker rm -f localstack
	@echo "Local teardown complete. If you deployed to real dev, run: cd ts && cdk destroy --profile crunch-dev --force"
```

`scripts/localstack-up.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
if docker ps --format '{{.Names}}' | grep -q '^localstack$'; then
  echo "localstack already running"; exit 0
fi
docker run --rm -d --name localstack -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  localstack/localstack:latest
echo "waiting for localstack..."
until curl -sf http://localhost:4566/_localstack/health >/dev/null; do sleep 1; done
echo "localstack healthy on :4566"
```

`scripts/seed-bucket.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ENDPOINT=http://localhost:4566
BUCKET=$(aws --endpoint-url=$ENDPOINT s3 ls | awk '/data/{print $3; exit}')
if [ -z "${BUCKET:-}" ]; then echo "no bucket found — run 'make deploy-local' first" >&2; exit 1; fi
echo "hello from the crunch iac starter" | aws --endpoint-url=$ENDPOINT s3 cp - "s3://$BUCKET/hello.txt"
echo "seeded s3://$BUCKET/hello.txt"
```

`scripts/invoke-local.sh` (uses `sam local invoke`, pointing the Lambda's boto3 client at LocalStack via the `AWS_ENDPOINT_URL` env var, which boto3 1.34+ honors):

```bash
#!/usr/bin/env bash
set -euo pipefail
ENDPOINT=http://host.docker.internal:4566   # the container reaches the host's localstack here
BUCKET=$(aws --endpoint-url=http://localhost:4566 s3 ls | awk '/data/{print $3; exit}')
cat > /tmp/event.json <<EOF
{ "key": "hello.txt" }
EOF
# A minimal SAM template wrapping the same handler so sam can run it.
cat > /tmp/sam-template.yaml <<EOF
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31
Resources:
  Reader:
    Type: AWS::Serverless::Function
    Properties:
      Handler: read_object.handler
      Runtime: python3.12
      CodeUri: ./lambda
      Timeout: 15
      Environment:
        Variables:
          BUCKET_NAME: ${BUCKET}
          AWS_ENDPOINT_URL: ${ENDPOINT}
EOF
sam local invoke Reader \
  --template /tmp/sam-template.yaml \
  --event /tmp/event.json \
  --docker-network host
```

Run the loop: `make deploy-local && make seed && make invoke-local`. You should see a JSON payload with `"size"` and a `"preview"` of the seeded text. Commit: `makefile + localstack dev loop`.

### Phase 6 — The parity table and README (~45 min)

1. Synthesize all three and build the parity table (see "Deliverable: the parity table" below).
2. Write the README: description, per-variant clone-to-deploy commands, the parity table, the "Things I learned" section.
3. Run `make destroy`. Confirm nothing lingers. Push to GitHub.

---

## TS tests — the snippet you must adapt

`aws-cdk-lib/assertions` lets you assert on the synthesized template without deploying. Your `ts/test/crunch-iac-ts-stack.test.ts` should look approximately like this:

```typescript
import { App } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { CrunchIacTsStack } from '../lib/crunch-iac-ts-stack';

const app = new App();
const stack = new CrunchIacTsStack(app, 'TestStack', {
  env: { account: '123456789012', region: 'us-east-1' },
});
const t = Template.fromStack(stack);

test('KMS key has rotation enabled', () => {
  t.hasResourceProperties('AWS::KMS::Key', { EnableKeyRotation: true });
});

test('bucket blocks all public access and is versioned', () => {
  t.hasResourceProperties('AWS::S3::Bucket', {
    VersioningConfiguration: { Status: 'Enabled' },
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
  });
});

test('bucket has the IA transition + expiration lifecycle rule', () => {
  t.hasResourceProperties('AWS::S3::Bucket', {
    LifecycleConfiguration: {
      Rules: Match.arrayWith([
        Match.objectLike({
          ExpirationInDays: 365,
          Transitions: Match.arrayWith([
            Match.objectLike({ StorageClass: 'STANDARD_IA', TransitionInDays: 30 }),
          ]),
        }),
      ]),
    },
  });
});

test('exactly one python3.12 Lambda', () => {
  t.resourceCountIs('AWS::Lambda::Function', 1);
  t.hasResourceProperties('AWS::Lambda::Function', { Runtime: 'python3.12' });
});

test('Lambda role policy is least-privilege: GetObject + kms Decrypt only', () => {
  t.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({ Action: Match.arrayWith(['s3:GetObject']) }),
        Match.objectLike({ Action: 'kms:Decrypt' }),
      ]),
    },
  });
});
```

If any of these fail, your stack drifted from the spec — fix the stack, not the test.

---

## Deliverable: the parity table

Synthesize all three and fill in a table like this in your README (your counts will differ slightly by CDK version; the *types* should match):

| Resource type | TS CDK | Python CDK | OpenTofu |
|---|---:|---:|---:|
| `AWS::EC2::VPC` | 1 | 1 | 1 |
| `AWS::EC2::Subnet` | 4 | 4 | 4 |
| `AWS::KMS::Key` | 1 | 1 | 1 |
| `AWS::S3::Bucket` | 1 | 1 | 1 |
| `AWS::S3::BucketPolicy` | 1 | 1 | 1 |
| `AWS::Lambda::Function` | 1 | 1 | 1 |
| `AWS::IAM::Role` (Lambda) | 1 | 1 | 1 |
| `AWS::IAM::Policy` (read grant) | 1 | 1 | (inline) |

Then write one honest paragraph: the CDK variants produce near-identical CloudFormation with different logical-ID hashes; OpenTofu writes the same resources but with provider-managed IDs, an inline IAM policy by default, and a state file that CDK does not have. That paragraph is the deliverable — it proves you understand the tools, not just that you copied them.

---

## Rubric

| Criterion | Weight | What "great" looks like |
|----------|-------:|-------------------------|
| Three working variants | 25% | TS synth, Py synth, and Tofu plan all clean on a fresh clone |
| Template parity proven | 20% | The parity table is filled, the paragraph is accurate, and the TS/Py tests encode it |
| Least-privilege IAM | 15% | No `s3:*` or `kms:*` wildcard anywhere; `grant`-generated scoping pointed to in each artifact |
| LocalStack dev loop | 20% | `make deploy-local && make seed && make invoke-local` returns the object size + preview |
| Repo hygiene | 10% | One shared handler, pinned versions, `.gitignore` excludes state and build output, no committed secrets |
| README quality | 10% | A newcomer clones and runs any variant in <5 minutes from the README alone |

---

## What this prepares you for — and why it is the substrate

- **Week 4 (VPC, Networking & Edge)** extends the `Vpc` construct in `ts/lib/`: it adds gateway endpoints for S3 and DynamoDB, interface endpoints, and a real three-AZ layout. You will not start a new repo — you will branch this one.
- **Week 6 (Storage)** extends the bucket: replication, Object Lambda, intelligent tiering. Same repo.
- **Week 9 (DynamoDB)** adds a single-table construct alongside the bucket. Same repo.
- **Week 13–15 (Capstone)** is deployed from a descendant of this monorepo, with the same `make`-driven dev loop and the same LocalStack-first discipline.

By the time you reach the capstone, your reflex will be: "new infrastructure → a construct in the starter → synth → diff → test → deploy through the loop." That reflex is the entire point of Week 3.

---

## Stretch (optional)

- Add **cdk-nag** (`AwsSolutionsChecks`) to the TS app and resolve or document every finding. Week 13 makes this mandatory; doing it now is free practice.
- Add a **GitHub Actions** workflow (`.github/workflows/ci.yml`) that runs `make synth` and `make test` on every push, spinning up LocalStack as a service container. Required from Week 4 onward.
- Add an **S3 Gateway VPC endpoint** to the VPC so the isolated-subnet Lambda can reach S3 with no NAT and no internet — and prove the Lambda still reads the object. This is the trick Week 4 makes central.
- Write a **`make drift`** target that triggers `aws cloudformation detect-stack-drift` against a real-`dev` deploy, polls to completion, and exits non-zero on drift. This is the seed of a production drift-CI job.

---

## Submission

When done:

1. Push your repo to GitHub with a public URL.
2. Make sure the README's clone-to-deploy commands work on a fresh clone for all three variants.
3. Make sure `make synth`, `make test`, and the LocalStack loop (`make deploy-local && make seed && make invoke-local`) are green on a freshly cloned copy.
4. Post the repo URL in your cohort tracker, and note in your engineering journal which of the three tools you would actually pick for a real product and why. You will defend that choice in Friday's architectural review.
