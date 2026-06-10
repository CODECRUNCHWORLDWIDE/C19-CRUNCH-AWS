# Lecture 1 — Why AWS Has 200+ Services and How to Navigate That

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can place any AWS service into one of seven families, reason about its blast radius and cost shape before reading its docs, choose a Region on real grounds, and draw the shared responsibility model from memory.

If you only remember one thing from this lecture, remember this:

> **AWS is not 200+ products you have to learn. It is seven service families, a handful of cross-cutting primitives (the account, IAM, the Region, the bill), and a long tail of services you can ignore until a specific problem forces you to learn one.** The catalog is intimidating only if you try to hold it flat. Held as a tree, it is small.

---

## 1. The origin story explains the catalog

AWS launched in 2006 with two services: **S3** (object storage, March 2006) and **EC2** (rentable virtual machines, August 2006). That is not a coincidence of marketing — it is the entire design philosophy. Amazon's internal teams had spent years fighting over shared infrastructure. The fix was to expose infrastructure as **primitives behind APIs**: a team that wanted storage called the storage API; a team that wanted a server called the compute API. Nobody filed a ticket. Nobody waited on a capacity-planning meeting.

That philosophy is why there are 200+ services today. AWS does not build "products" in the way a SaaS company does. It builds **primitives**, and then it builds primitives on top of primitives, and then it builds managed conveniences on top of *those*. EC2 is a primitive. ECS is a convenience over EC2. Fargate is a convenience over ECS. App Runner is a convenience over Fargate. Each layer exists because some customer was tired of operating the layer below it.

Three consequences follow, and they hold across the whole catalog:

1. **Most services are compositions of a few primitives.** Learn the primitives (compute, storage, a network, an identity system, a queue) and the rest are recombinations.
2. **There are almost always three-to-five ways to do the same thing**, at different levels of "how much do I want to operate myself." Run a container on EC2 (you operate the host), ECS-on-EC2 (you operate the cluster), Fargate (you operate nothing below the task), or Lambda (you operate nothing below the function). The right answer is a trade-off, never a default.
3. **Old services never die.** AWS almost never deprecates anything, because some customer's production system depends on it. SimpleDB still exists. That is why the catalog only grows. It is also why "200+ services" is a misleading number — maybe 30 of them matter to any given team.

So the skill is not memorizing 200 services. The skill is **triage**: given a new service name, place it in the tree, guess its shape, and decide whether you need it today.

---

## 2. The seven service families

Here is the tree. AWS's own console groups things slightly differently and inconsistently; this grouping is the one that holds up in design reviews. For each family, learn the *two or three* services that carry 90% of the weight, and treat the rest as "I'll read the docs if a problem points me there."

### Family 1 — Compute

Where your code runs.

| Service | One-line shape | When |
|---|---|---|
| **EC2** | Rent a virtual (or bare-metal) server. You own the OS. | You need a long-lived host, custom kernels, GPUs, or a lift-and-shift. |
| **Lambda** | Run a function on an event. No server. Pay per ms. | Event handlers, glue, anything bursty and stateless. Cold starts matter. |
| **ECS Fargate** | Run a container with no host to manage. | Long-running containers without a Kubernetes habit. |
| **EKS** | Managed Kubernetes control plane. | You already think in Kubernetes and want it managed. $72/mo for the control plane. |

You can ignore **Batch, Lightsail, App Runner, Outposts, EC2 Image Builder** until a problem names them.

### Family 2 — Storage

Where bytes sit at rest.

| Service | One-line shape | When |
|---|---|---|
| **S3** | Object storage. Effectively infinite. The default home for any blob. | Almost always. Backups, data lakes, static sites, artifacts. |
| **EBS** | A virtual disk you attach to one EC2 instance. | Block storage for a single host (a database volume, a boot disk). |
| **EFS** | A network filesystem (NFS) many hosts mount at once. | Shared POSIX filesystem across instances/containers. |

Ignore **FSx, Storage Gateway, S3 Glacier-as-a-separate-thing** (it's an S3 storage class now) until needed.

### Family 3 — Database

Structured state.

| Service | One-line shape | When |
|---|---|---|
| **RDS / Aurora** | Managed relational SQL (Postgres, MySQL, ...). | Relational data, transactions, joins. Aurora when you want AWS's storage engine. |
| **DynamoDB** | Managed key-value / document store. Single-digit-ms at any scale. | Known access patterns, high scale, serverless. The single-table model (Week 9). |
| **ElastiCache** | Managed Redis / Memcached. | Caching, sessions, leaderboards. |

Ignore **Neptune, DocumentDB, Timestream, Keyspaces, QLDB** until a workload demands graph/time-series/etc.

### Family 4 — Networking & Content Delivery

How packets move.

| Service | One-line shape | When |
|---|---|---|
| **VPC** | Your private virtual network. Subnets, route tables, security groups. | Always — almost everything runs inside one. (Week 4.) |
| **Route 53** | DNS and health-checked routing. **Global.** | Domains, failover routing, latency routing. |
| **CloudFront** | CDN at the edge locations. **Global.** | Caching static and dynamic content close to users. |
| **ELB (ALB/NLB)** | Load balancers. | Spread traffic across targets. |

Ignore **Transit Gateway, PrivateLink, Direct Connect, Global Accelerator** until your topology grows past one VPC (we cover them in Week 4).

### Family 5 — Security & Identity

Who can do what, and to which bytes.

| Service | One-line shape | When |
|---|---|---|
| **IAM** | Users, roles, policies. The permission system. **Global.** | Always. This is Week 2, the most important week. |
| **IAM Identity Center** | Human SSO across accounts. The `aws sso login` target. | How people (not machines) log in. |
| **KMS** | Managed encryption keys. | Encrypt anything; control who can decrypt. |
| **Organizations** | Multi-account governance + SCP guardrails. | The moment you have more than one account. **This week.** |

Ignore **GuardDuty, Security Hub, Macie, Inspector, WAF, Shield, Secrets Manager** until Weeks 2 and 13. They are important; they are not Week 1.

### Family 6 — Integration & Messaging

How services talk asynchronously.

| Service | One-line shape | When |
|---|---|---|
| **SQS** | A managed queue. At-least-once delivery. | Decouple producers from consumers; absorb bursts. |
| **SNS** | Pub/sub fan-out. | One message, many subscribers. |
| **EventBridge** | An event bus with routing rules. | Event-driven architecture spine (Week 10). |
| **Step Functions** | A state-machine orchestrator. | Multi-step workflows with retries and branching. |

Ignore **Kinesis, MSK, MQ, AppFlow** until Week 10.

### Family 7 — Management & Observability

How you watch, govern, and pay for everything above.

| Service | One-line shape | When |
|---|---|---|
| **CloudWatch** | Logs, metrics, alarms, dashboards. | Always — your eyes on the system (Week 12). |
| **CloudTrail** | An audit log of every API call. | Always — your forensic record. Turn it on day one. |
| **CloudFormation** | Native infrastructure as code. The substrate under CDK. | Declarative provisioning (Week 3). |
| **Cost Explorer / Budgets / CUR** | The billing and FinOps surface. | **This week.** Cost is observability. |

Ignore **Config, Systems Manager (mostly), Control Tower, Service Catalog** until you need governance at scale.

> **The heuristic, restated.** When you meet a new service, ask three questions: *(1) Which family? (2) What primitive is it a convenience over? (3) Do I have the problem it solves right now?* If the answer to (3) is no, close the tab. You will not be a worse engineer for not knowing what AWS HealthOmics does.

---

## 3. Global vs Regional vs zonal — the dimension beginners miss

Every AWS service lives at exactly one of three scopes, and confusing them is the source of a remarkable number of production incidents.

- **Global services** have a single control plane shared across the whole partition. **IAM, Route 53, CloudFront, WAF (for CloudFront), and the billing/Organizations console** are global. When you create an IAM role, it is not "in `eu-west-1`" — it just *is*. A consequence: many global services' control planes physically live in **`us-east-1`**, which is why `us-east-1` problems sometimes ripple into "global" operations.

- **Regional services** are scoped to a Region. An S3 bucket lives in a Region. A DynamoDB table lives in a Region. A VPC lives in a Region. The data does not leave that Region unless you explicitly replicate it. This is the scope you choose for almost everything, and it is the unit of **data residency** — if your customer's data must stay in the EU, you choose `eu-*` Regions and you do not let it leave.

- **Zonal resources** are pinned to a single Availability Zone within a Region. An EC2 instance runs in one AZ. An EBS volume lives in one AZ and can only attach to an instance in that same AZ. A subnet is zonal. This is the scope of **fault isolation**: "multi-AZ" means you spread zonal resources across AZs so one data center failing does not take you down.

```
Partition (aws)
│
├── Global plane ───────── IAM · Route 53 · CloudFront · Organizations · Billing
│
└── Region (eu-west-1) ─── S3 buckets · DynamoDB tables · VPCs · RDS clusters
        │
        ├── AZ eu-west-1a ─ EC2 instances · EBS volumes · subnets
        ├── AZ eu-west-1b ─ EC2 instances · EBS volumes · subnets
        └── AZ eu-west-1c ─ EC2 instances · EBS volumes · subnets
```

When you design for availability, you are reasoning about which scope each resource sits at. A "single point of failure in one AZ" is a zonal-resource mistake. A "we lost the whole Region" event is rare but real, and is why Week 13 covers multi-Region DR.

---

## 4. Choosing a Region — on grounds, not habit

Engineers new to AWS default to `us-east-1` because every tutorial does. That is a bad habit. Choose a Region on four axes:

1. **Latency.** Put compute close to your users. A European user base served from `us-east-1` eats ~100 ms of round-trip you did not need to pay.
2. **Data residency / compliance.** GDPR, schrems, sectoral rules. If data must stay in a jurisdiction, the Region choice is a legal constraint, not a preference.
3. **Service availability.** Not every service is in every Region. New services launch in `us-east-1` first and roll out over months. Check the **Region table** before committing.
4. **Cost.** Per-unit prices differ by Region — `us-east-1` is often the cheapest, some Regions are 10–30% more. For a steady, large workload that difference is real money.

And one special case you must internalize: **`us-east-1` is special.** It is the oldest Region, it hosts the control planes of several global services, it is where the billing and IAM consoles default, and it is the busiest. Some APIs (for instance, requesting an ACM certificate for CloudFront, or some Organizations and billing operations) **must** run in `us-east-1` regardless of where the rest of your stack lives. This is exactly why our Wednesday lab denies `us-east-1` to one OU — to teach you that "deny a Region" is a sharper instrument than it looks, because a blanket `us-east-1` deny can break global operations.

> **War story, generalized.** Teams routinely write an SCP that denies every Region except their chosen one, forget to carve out `us-east-1`, and then discover their CloudFront cert requests and some IAM-adjacent calls silently fail. The fix is a `NotAction` / `Arn`-condition carve-out for the genuinely-global operations. You will hit this in the exercise. That is on purpose.

---

## 5. The shared responsibility model

AWS draws one diagram more than any other, and it is the one that ends arguments in incident reviews. The split is:

- **AWS is responsible for security *of* the cloud** — the physical data centers, the hypervisor, the network backbone, the hardware, and the managed-service software up to the line where you start configuring it.
- **You are responsible for security *in* the cloud** — your data, your IAM policies, your network configuration, your patching (where the service exposes an OS), and your application code.

The line **moves per service**, and that is the part beginners miss. The more managed the service, the more of the stack AWS owns:

| Service | AWS owns | You own |
|---|---|---|
| **EC2** | Hardware, hypervisor, network. | The OS, patching, the app, firewall rules (security groups), data, IAM. |
| **RDS** | Hardware, OS, DB engine patching, backups infra. | Schema, queries, who can connect, encryption choices, data, IAM. |
| **S3** | Hardware, the storage service, durability (11 nines). | Bucket policy, Block Public Access, encryption choice, what you put in it, IAM. |
| **Lambda** | Hardware, OS, runtime, scaling. | Function code, its IAM role, the data it touches, dependencies. |

Read the rows top to bottom: as you move from EC2 to Lambda, "you own" shrinks — but **two things are always yours: your data and your IAM.** No managed service ever takes responsibility for "you gave the wrong principal `s3:GetObject` on the bucket with the customer PII." That is structurally your problem. This is why Week 2 (IAM) exists and why this week's first act is locking the root user: the parts that are *always* yours are the parts worth getting right on day one.

```
        of the cloud (AWS)                    in the cloud (you)
   ┌───────────────────────────┐        ┌───────────────────────────┐
   │ regions, AZs, data centers│        │ your data                 │
   │ hardware, networking       │        │ IAM: who can do what      │
   │ hypervisor / managed engine│        │ network & firewall config │
   │ service availability (SLA) │        │ OS patching (EC2-class)    │
   └───────────────────────────┘        │ application code           │
                                         └───────────────────────────┘
                line moves right ◄────► as the service gets more managed
```

---

## 6. The cross-cutting primitives that are not "a service"

Four things touch *everything*, and they are the real Week-1 curriculum:

1. **The account.** The hard boundary for both **security** and **billing**. Resources in account A cannot see resources in account B unless you explicitly cross the boundary with IAM. The bill is per account. This is why "one account per environment" is the baseline pattern and why we stand up an Organization this week. Lecture 2 is entirely about this.

2. **IAM.** Every API call is authenticated and authorized by IAM. There are no exceptions. Even "public" S3 access is an IAM/resource-policy decision you made. Week 2.

3. **The Region.** Covered above. The unit of data residency and the default scope of most resources.

4. **The bill.** Every resource has a cost shape — per-hour (EC2), per-request-and-per-ms (Lambda), per-GB-month (S3), per-GB-transferred (almost everything, via data-transfer charges). **Reasoning about cost is a design skill, not an afterthought.** This is why C19 configures Budgets and the CUR in Week 1 and ends every later week with a cost report. The single most expensive surprise in AWS is *data transfer out* and *NAT Gateway*, neither of which shows up until the bill arrives — unless you set up observability first. Which we do, this week.

---

## 7. A worked triage, end to end

Let's run the heuristic on a real prompt so it sticks. Suppose a teammate says: *"We need to send a templated email whenever a user signs up, and we want to retry if the email provider is down."*

- **What primitives?** An event (signup), some compute (build + send the email), a way to retry (a queue), and a way to send mail.
- **Which families?** Integration & messaging (the event + the queue), compute (the function), and a delivery service.
- **Map to services:** EventBridge or an SNS topic for the signup event → SQS for retry-able work → Lambda to render and send → **SES** (Simple Email Service) for the actual mail. SES is in the long tail we said you could ignore — but the *problem* (send mail) named it, so now you learn the one service, not the other 190.
- **Cost shape?** Lambda: pennies per million invocations. SQS: pennies per million messages. SES: fractions of a cent per email. EventBridge: pennies per million events. This whole thing costs almost nothing until you have real volume — which you now *know*, because you reasoned about the cost shape before building.
- **Blast radius / IAM?** The Lambda needs a role that can read from SQS and call `ses:SendEmail`. Nothing else. Least privilege falls out of the design.

That is the whole skill. You did not need to know SES existed yesterday. You needed the map, and the map pointed you at exactly one new thing to read.

---

## 8. Hands-on — read the catalog with the CLI

Open a terminal (or CloudShell — see Lecture 2 for `aws sso login`). You can interrogate AWS's own service and Region metadata. List the Regions your account can use:

```bash
aws ec2 describe-regions \
  --query 'Regions[].RegionName' \
  --output table
```

You'll see the Regions enabled for your account (some are opt-in). Now look at the AZs in one Region:

```bash
aws ec2 describe-availability-zones \
  --region eu-west-1 \
  --query 'AvailabilityZones[].{Name:ZoneName,State:State}' \
  --output table
```

Three (sometimes more) AZs. That is the fault-isolation budget you design against. Now prove that a *global* service does not care about `--region`. Ask for your account's IAM account summary from two different Regions and confirm the answer is identical:

```bash
aws iam get-account-summary --region eu-west-1 --query 'SummaryMap.Users'
aws iam get-account-summary --region ap-southeast-2 --query 'SummaryMap.Users'
```

Same number both times — because IAM is global and the `--region` flag is ignored for it. Contrast with a Regional service, where the Region absolutely matters:

```bash
# Buckets are global in name but Regional in location; this lists ALL buckets
# in the account regardless of --region, because the S3 list-buckets control
# plane is global — but each bucket has a home Region you must respect.
aws s3api list-buckets --query 'Buckets[].Name' --output table
```

Run these now. The point is not the output; it is the muscle memory of *checking the scope* before you assume it.

---

## 9. What this lecture deliberately skips

- **Deep IAM.** You can read a deny by Friday; writing least-privilege policies with conditions and boundaries is all of Week 2.
- **VPC internals.** Subnets, route tables, NAT — Week 4. This week, "a VPC is your private network" is enough.
- **Any actual compute deployment.** We do not launch a server this week. We build the *governance and cost* substrate that every later compute lab depends on.
- **The 190 services in the long tail.** By design. You now have a map; the map tells you when to learn each one.

---

## 10. Recap

You should now be able to:

- Explain *why* AWS has 200+ services (primitives + conveniences-over-primitives, and nothing ever dies).
- Place any service into one of seven families and name the two or three that carry each family.
- Distinguish global, Regional, and zonal scope, and explain why `us-east-1` is special.
- Choose a Region on latency, residency, availability, and cost — not habit.
- Draw the shared responsibility model and state that **your data and your IAM are always yours**.
- Run the triage heuristic on a novel problem to find the one service you actually need to learn.

Next up: the account boundary, Organizations, SCPs, and root hygiene — the controls a senior engineer wires up before launching anything. Continue to [Lecture 2 — Account-Level Posture](./02-account-posture-organizations-scps.md).

---

## References

- *AWS Global Infrastructure*: <https://aws.amazon.com/about-aws/global-infrastructure/>
- *Regions and Availability Zones*: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html>
- *Shared Responsibility Model*: <https://aws.amazon.com/compliance/shared-responsibility-model/>
- *AWS Well-Architected Framework*: <https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html>
- *AWS CLI v2 — `describe-regions`*: <https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-regions.html>
