# Lecture 2 — EKS Production Patterns: Karpenter, IRSA, the AWS Load Balancer Controller, and Spot Node Economics

> **Duration:** ~2 hours of reading + hands-on.
> **Outcome:** You can stand up a production-shaped EKS cluster with managed node groups for the system add-ons, Karpenter provisioning Spot worker nodes, IRSA scoping a single pod to a single S3 prefix, the AWS Load Balancer Controller turning Ingress into an ALB, External DNS writing Route 53, and the EBS CSI driver provisioning volumes. You can explain *why* each piece exists and what breaks without it.

If you only remember one thing from this lecture, remember this:

> **EKS gives you a Kubernetes control plane and nothing else. The control plane is the easy part. The production cluster is the dozen pieces you bolt on — node autoscaling, pod identity, ingress, DNS, storage — and every one of them is an IAM problem before it is a Kubernetes problem.**

This is the lecture where Week 2 (IAM) and Week 4 (VPC) cash in. IRSA is a trust-policy problem. Karpenter is a "which subnets and which instance types" problem. The LB Controller is a "which IAM permissions to create an ALB" problem. If IAM and networking are not solid, none of this works, and the error messages are famously unhelpful.

---

## 1. What `$73/month` actually buys you

When you create an EKS cluster, AWS gives you a **managed Kubernetes control plane**: the API server, etcd, the scheduler, and the controller-manager, run across three AZs, patched and backed up by AWS. That's the $0.10/hour. What it does **not** give you:

- **Worker nodes.** Pods need somewhere to run. You bring nodes (managed node groups, Karpenter, or Fargate profiles).
- **A way to grow/shrink nodes.** That's **Karpenter** (or the older Cluster Autoscaler).
- **A way to give pods AWS permissions.** That's **IRSA** or **Pod Identity**.
- **Ingress / load balancing.** That's the **AWS Load Balancer Controller**.
- **DNS records.** That's **External DNS**.
- **Persistent storage.** That's the **EBS CSI driver** (and/or EFS CSI).
- **Networking.** That's the **VPC CNI** (the default; assigns real VPC IPs to pods).

A "production EKS cluster" is the control plane *plus all of the above, wired correctly*. The exercises this week wire them. This lecture explains each.

---

## 2. The node story: managed node groups vs Karpenter vs Fargate profiles

You have three ways to get compute under your pods, and mature clusters use **two or three at once**.

### 2.1 Managed node groups

A managed node group is an EKS-managed **ASG** of worker nodes with lifecycle automation: AWS handles the launch template, the bootstrap, graceful draining on scale-down, and coordinated version upgrades. You set min/max/desired and the instance type(s).

**Use managed node groups for the things that must always be running and must not depend on Karpenter:** the system add-ons themselves. Karpenter cannot schedule the pod that schedules nodes onto a node that doesn't exist yet — that's a chicken-and-egg. So the standard pattern is a **small, On-Demand managed node group** (often 2 nodes across 2 AZs) that hosts CoreDNS, Karpenter itself, the LB Controller, and other critical controllers, and then **Karpenter provisions everything else on Spot.**

### 2.2 Karpenter

**Cluster Autoscaler** (the old way) worked by resizing ASGs: you pre-defined node groups, and it scaled them up when pods were pending. It was slow (ASG round-trips) and you had to hand-curate instance types per group.

**Karpenter** (the modern way, `v1` API stable since 2024) is smarter: it watches for **pending pods**, computes the *cheapest set of right-sized instances* that would fit them, and launches EC2 **directly** — no pre-defined ASG. It bin-packs aggressively, **consolidates** under-utilized nodes (moving pods off and terminating the node), and handles Spot interruptions natively. It's faster and cheaper than Cluster Autoscaler, and it's why EKS-on-Spot is economically serious.

Karpenter is configured with two CRDs:

- **`NodePool`** — the policy: which instance families/sizes/architectures/capacity-types (Spot vs On-Demand) Karpenter may use, limits, and disruption rules.
- **`EC2NodeClass`** — the AWS specifics: which AMI family (Bottlerocket/AL2023), which subnets and security groups (discovered by tag), the instance profile (IAM role for the nodes).

```yaml
# NodePool: let Karpenter use Graviton Spot, fall back to On-Demand, consolidate aggressively.
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      requirements:
        - key: kubernetes.io/arch
          operator: In
          values: ["arm64"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]
        - key: karpenter.k8s.aws/instance-category
          operator: In
          values: ["c", "m", "r"]
        - key: karpenter.k8s.aws/instance-generation
          operator: Gt
          values: ["6"]            # gen 7+ Graviton only
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
      expireAfter: 168h            # recycle nodes weekly to pick up AMI patches
  limits:
    cpu: "200"                     # safety ceiling: Karpenter never exceeds 200 vCPU
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 1m           # reclaim wasted capacity fast
---
# EC2NodeClass: Bottlerocket on Graviton, discover subnets/SGs by tag.
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiFamily: Bottlerocket
  amiSelectorTerms:
    - alias: bottlerocket@latest
  role: "KarpenterNodeRole-c19-week05"      # the IAM role nodes assume
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: "c19-week05"   # tag your private subnets with this
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: "c19-week05"
```

Read that `NodePool` like an SRE: it says "give me gen-7+ Graviton `c`/`m`/`r` instances, prefer Spot, allow On-Demand fallback, never exceed 200 vCPU total, recycle nodes weekly for patching, and consolidate under-utilized nodes after a minute." That single document is most of your node strategy and most of your node *cost* strategy.

**The Spot economics, concretely.** A diversified Karpenter `NodePool` on Spot across `c7g`/`m7g`/`r7g` of several sizes is drawing from many Spot pools, so interruptions are rare and, when they happen, Karpenter cordons-and-drains within the 2-minute notice and launches a replacement from another pool. You run stateless services at **60–70% off On-Demand** with managed risk. The discipline: set `PodDisruptionBudget`s on your workloads so Karpenter can't drain a node out from under your only replica, and keep anything genuinely stateful or singleton on the On-Demand managed group.

### 2.3 Fargate profiles

A **Fargate profile** says "pods matching this namespace/label selector run on Fargate instead of on a node." No node to manage for those pods — Fargate runs each pod in its own microVM. Use it for **bursty, isolation-sensitive, or low-volume** workloads where you don't want them sharing a node, or to run a small cluster with *zero* worker nodes. The trade-off is Fargate's per-pod overhead (it rounds CPU/memory up to the next supported size and adds a per-pod cost), so it's rarely the cheapest at scale — but it's operationally the lightest.

**The mature pattern:** a tiny On-Demand managed node group for system controllers, **Karpenter on Spot** for the bulk of workloads, and **Fargate profiles** for the one or two namespaces that want hard pod isolation. The capstone's compute-hybrid layer is exactly this.

---

## 3. IRSA: the single most-botched thing in EKS

A pod needs to read an S3 bucket. How does it get AWS credentials? The wrong answers, in order of how-much-this-will-hurt-you:

1. **Bake an access key into the image.** Catastrophic. Now your AWS keys are in a container registry forever.
2. **Use the node's instance profile.** Tempting, because the node already has an IAM role. But then **every pod on that node** inherits the node's permissions. One compromised pod owns everything the node can do. This is the "node role is over-privileged" anti-pattern, and it is everywhere.
3. **IRSA — IAM Roles for Service Accounts.** The right answer. Each pod assumes its **own** IAM role, scoped to exactly what that pod needs, via a Kubernetes service account.

### 3.1 How IRSA actually works (the part people skip and then can't debug)

EKS gives every cluster an **OIDC identity provider** — an OIDC issuer URL. When you annotate a Kubernetes **ServiceAccount** with an IAM role ARN, the EKS pod-identity webhook injects two things into any pod using that SA:

- A **projected service-account token** (a signed JWT, the "web identity"), mounted at a file path.
- The env vars `AWS_ROLE_ARN` and `AWS_WEB_IDENTITY_TOKEN_FILE`.

The AWS SDK inside the pod sees those env vars and calls **`sts:AssumeRoleWithWebIdentity`**, presenting the JWT. STS validates the JWT against the cluster's registered OIDC provider, checks the **role's trust policy**, and — if everything lines up — hands back temporary credentials scoped to that role. The pod now has exactly that role's permissions and nothing more.

The two pieces that must match, and the two pieces everyone gets wrong:

**(a) The IAM role's trust policy** must trust the cluster's OIDC provider *and* pin the specific service account:

```jsonc
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.eu-west-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D3041E"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "oidc.eks.eu-west-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D3041E:aud": "sts.amazonaws.com",
        "oidc.eks.eu-west-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D3041E:sub": "system:serviceaccount:app:fastapi-reader"
      }
    }
  }]
}
```

That `:sub` condition is the whole game. It says **only** the `fastapi-reader` service account in the `app` namespace may assume this role. Drop it (or use `StringLike` with a wildcard) and *any* pod in the cluster can assume the role — you've recreated the over-privileged-node problem with extra steps. Pin the subject. Always.

**(b) The ServiceAccount annotation** must name the role:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: fastapi-reader
  namespace: app
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::111122223333:role/c19-week05-fastapi-reader
```

And the permissions policy on that role is the *least-privilege S3 scope* — one prefix, one bucket:

```jsonc
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:GetObject"],
    "Resource": "arn:aws:s3:::c19-week05-data/public/*"
  }]
}
```

That's IRSA: the pod can `GetObject` from `c19-week05-data/public/*` and **literally nothing else** — not write, not list other prefixes, not touch another bucket. In the EKS exercise you will prove the negative: exec into the pod, succeed at reading `public/hello.txt`, and **fail** to read `private/secret.txt` with an `AccessDenied`. That failing call is the deliverable — it proves the scope holds.

### 3.2 IRSA vs Pod Identity

In 2023 AWS shipped **EKS Pod Identity** as an IRSA alternative. Instead of a per-cluster OIDC provider and per-role trust policies, you install the **Pod Identity Agent** add-on and create **association** objects mapping a service account to a role. The trust policy is uniform (`pods.eks.amazonaws.com`), so you don't hand-edit OIDC-provider ARNs into every role, and the same role can be reused across clusters without re-registering OIDC providers.

**When to prefer Pod Identity:** new clusters, many clusters (the OIDC-per-cluster bookkeeping of IRSA gets painful), or when you want roles reusable across clusters. **When IRSA still wins:** you're already on it and it works (don't migrate for fashion), or you need a feature Pod Identity hasn't reached yet for your edge case. This week we teach **IRSA** because it's what the SAP exam tests, what the capstone spec names, and what you'll see in 90% of existing clusters — and because understanding `sts:AssumeRoleWithWebIdentity` makes Pod Identity trivial to pick up later. The stretch goal asks you to swap to Pod Identity and write up the trade-off.

---

## 4. The AWS Load Balancer Controller

A Kubernetes `Ingress` or a `Service type=LoadBalancer` is just an *intent*. Something has to turn that intent into a real AWS load balancer. That something is the **AWS Load Balancer Controller**, a controller you install (Helm) that watches Ingress/Service objects and provisions:

- **ALBs** for `Ingress` objects (annotation `alb.ingress.kubernetes.io/...`) — L7, path/host routing, the right choice for HTTP services.
- **NLBs** for `Service type=LoadBalancer` with the NLB annotation — L4, ultra-low latency, the right choice for TCP/gRPC at scale.

Two routing modes worth knowing:

- **Instance mode:** the ALB targets node ports; traffic hops node → kube-proxy → pod. Works with managed node groups.
- **IP mode:** the ALB targets pod IPs **directly** (possible because the VPC CNI gives pods real VPC IPs). One fewer network hop, plays nicely with Fargate (where there's no node port). **Prefer IP mode** in modern clusters.

The controller itself needs IAM permissions to create/modify ALBs, target groups, listeners, and security-group rules — so it gets its **own IRSA role** with the published LB-Controller policy. (See the chicken-and-egg: the controller runs on the managed node group, scoped via IRSA, and *then* it can provision the ALB that fronts your Karpenter-scheduled pods.)

```yaml
# An Ingress that the AWS Load Balancer Controller turns into an internet-facing ALB,
# in IP target mode, with health checks pointing at FastAPI's /healthz.
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fastapi
  namespace: app
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/healthcheck-path: /healthz
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:eu-west-1:111122223333:certificate/abcd-1234
    external-dns.alpha.kubernetes.io/hostname: fastapi.c19-week05.example.com
spec:
  ingressClassName: alb
  rules:
    - host: fastapi.c19-week05.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: fastapi
                port:
                  number: 80
```

---

## 5. External DNS

Notice the `external-dns.alpha.kubernetes.io/hostname` annotation above. The ALB the controller creates has an ugly auto-generated DNS name. **External DNS** is a controller that watches Ingress/Service objects for hostname annotations and writes the matching **Route 53** records (alias records to the ALB) automatically. Now `fastapi.c19-week05.example.com` resolves to the freshly-minted ALB without anyone touching the Route 53 console. External DNS also gets its **own IRSA role**, scoped to the specific hosted zone (`route53:ChangeResourceRecordSets` on one zone ARN — never `*`).

The pattern that should be clicking by now: **every controller that touches AWS gets its own narrowly-scoped IRSA role.** LB Controller, External DNS, the EBS CSI driver, your app — four service accounts, four roles, four least-privilege policies. That's not bureaucracy; that's blast-radius control. A compromised External DNS pod can change DNS records in one zone and do nothing else.

---

## 6. The EBS CSI driver

Stateful pods need volumes. The **EBS CSI driver** (a managed EKS add-on) implements the Container Storage Interface so that a `PersistentVolumeClaim` dynamically provisions a real **EBS volume**, attaches it to the node the pod lands on, and mounts it. It, too, runs under an IRSA role allowing `ec2:CreateVolume`, `ec2:AttachVolume`, etc.

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
provisioner: ebs.csi.aws.com
volumeBindingMode: WaitForFirstConsumer   # wait until the pod is scheduled, then make the volume in that AZ
parameters:
  type: gp3
  encrypted: "true"                         # KMS-encrypt every volume by default
```

`WaitForFirstConsumer` matters: EBS volumes are **AZ-scoped**. If you provision the volume before the pod is scheduled, you might make it in `eu-west-1a` and then the scheduler puts the pod in `eu-west-1b`, and the pod can never attach. Binding late ensures the volume is born in the pod's AZ. Our FastAPI app is stateless, so we mostly *don't* use this — but you must know it for the capstone's stateful sidecar, and `encrypted: "true"` is non-negotiable in production.

---

## 7. The VPC CNI and IP exhaustion (the gotcha that pages you at 2 a.m.)

The default EKS networking plugin, the **VPC CNI**, gives every pod a **real IP address from your VPC subnets**. That's great for security groups and ALB IP-target mode — pods are first-class network citizens. It's a footgun for **IP exhaustion**: a `/24` subnet has ~250 usable IPs, and a busy node can hold dozens of pods, each consuming a VPC IP (plus warm-pool IPs the CNI pre-allocates). Plan subnet CIDRs for pod density, not node count. This is why Week 4 had you carve generous private subnets. If you see pods stuck in `ContainerCreating` with "failed to assign an IP address," you've hit this — enable prefix delegation or widen the subnets.

---

## 8. Putting it together: the deployment order

There's a dependency order, and getting it wrong produces those famously-unhelpful errors. Stand the cluster up in this sequence:

1. **VPC** (from Week 4) — private subnets **tagged** `karpenter.sh/discovery=<cluster>` and `kubernetes.io/role/internal-elb=1`.
2. **EKS control plane** + **OIDC provider** registered.
3. **Small On-Demand managed node group** (2 nodes, 2 AZs) for system controllers.
4. **Core add-ons:** VPC CNI, CoreDNS, kube-proxy, EBS CSI driver (all managed add-ons).
5. **Karpenter** (Helm) with its IRSA role, plus the `NodePool` + `EC2NodeClass`.
6. **AWS Load Balancer Controller** (Helm) with its IRSA role.
7. **External DNS** (Helm) with its IRSA role, scoped to the hosted zone.
8. **Your app:** ServiceAccount (IRSA-annotated) + Deployment + Service + Ingress + PodDisruptionBudget.

When you apply the app, watch the cascade: the scheduler can't place pods → Karpenter sees pending pods → Karpenter launches a Spot Graviton node in ~30–60s → pods schedule → the LB Controller sees the Ingress and provisions an ALB → External DNS writes the Route 53 record → the pod, via IRSA, reads its S3 prefix. Every arrow in that chain is one of the pieces in this lecture. When something breaks, you now know exactly which controller and which IAM role to interrogate.

---

## 9. Cost discipline on EKS (so you don't get the $73 surprise)

- The control plane bills **the moment the cluster exists**. `cdk destroy` / `eksctl delete cluster` nightly during this week. We give you a cron pattern in the exercise.
- Karpenter `consolidationPolicy: WhenEmptyOrUnderutilized` reclaims idle nodes — leave it on.
- Tag everything (`team`, `service`, `environment`) so Cost Explorer can attribute spend. EKS spreads cost across EC2, EBS, ELB, and the control-plane line; without tags you can't tell which service cost what.
- Spot for workers, On-Demand only for the system node group and anything stateful/singleton.
- Right-size requests/limits. Karpenter bin-packs against **requests**; over-requesting wastes nodes, under-requesting causes throttling and OOMKills.

---

## 10. Cluster upgrades and the version-skew tax

The bolt-on you forget until it pages you is **upgrades**. EKS supports each Kubernetes minor version for a window (roughly 14 months in 2026; after that it's force-upgraded), and a minor version drops every few months. So a long-lived cluster is *always* drifting toward an upgrade, and "we'll deal with it later" is how teams end up on an unsupported version with a forced upgrade scheduled by AWS at a time they did not pick.

The upgrade is a four-part move, and the order matters:

1. **Control plane first.** Upgrade the EKS control plane one minor version at a time (you cannot skip minors — 1.31 → 1.33 means 1.31 → 1.32 → 1.33). This is an in-place, AWS-managed operation with no data-plane downtime if your workloads tolerate the brief API-server blips.
2. **Add-ons next.** The managed add-ons (VPC CNI, CoreDNS, kube-proxy, EBS CSI) each have a version compatible with each Kubernetes version. Bump them to the matching version *after* the control plane. A kube-proxy that is two minors behind the API server is a classic source of subtle networking breakage.
3. **Nodes last.** Roll the worker nodes to an AMI built for the new version. With managed node groups this is a managed rolling replacement; with **Karpenter** you bump the `EC2NodeClass` AMI alias (or rely on `expireAfter` to recycle nodes onto the latest AMI within a week) and Karpenter drains-and-replaces respecting your `PodDisruptionBudget`s. This is *why* the `expireAfter: 168h` in the `NodePool` matters — it keeps nodes from drifting arbitrarily far behind.
4. **Your controllers.** The LB Controller, External DNS, and Karpenter itself have version-compatibility matrices against Kubernetes. Check them before, not after.

**The skew rule** Kubernetes enforces: the kubelet (on nodes) may be at most *three* minors behind the API server, never ahead. So you can run the control plane ahead of the nodes briefly during an upgrade, but you cannot let nodes lag forever. The practical discipline: upgrade on a cadence (every other minor, say), in a non-prod cluster first, with a Friday-afternoon rollback plan, and never let the cluster fall to the bottom of the support window where AWS picks the timing for you.

---

## 11. A debugging playbook for when the cascade breaks

The deployment cascade in §8 has a famous failure mode at every arrow, and the error messages rarely name the real cause. Keep this table; it is the difference between a five-minute fix and a two-hour rabbit hole.

| Symptom | Most likely cause | Where to look |
|---|---|---|
| Pods stuck `Pending` forever | Karpenter can't find a matching instance type, or subnets aren't tagged for discovery | `kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter`; check `karpenter.sh/discovery` subnet tags and the `NodePool` requirements |
| Pod runs but every AWS call is `AccessDenied` | IRSA not wired: missing SA annotation, or trust policy `:sub` doesn't match the SA | `kubectl describe sa <sa> -n <ns>` for the role-arn annotation; `aws sts get-caller-identity` from inside the pod |
| Pod has the *node's* permissions, not its own | Pod predates the SA annotation, or `AWS_WEB_IDENTITY_TOKEN_FILE` isn't injected | restart the pod; confirm `spec.serviceAccountName` is your SA, not `default` |
| `Ingress` never gets an `ADDRESS` | LB Controller can't create the ALB — missing IAM permission or no public subnets tagged | LB Controller pod logs in `kube-system`; check `kubernetes.io/role/elb` subnet tags |
| ALB is up but returns 503 | Target group has no healthy targets: wrong health-check path or port | target-group health in the EC2 console; confirm `target-type: ip` and the `/healthz` annotation |
| DNS name never resolves | External DNS can't write Route 53 — IRSA scoped to the wrong zone, or no hostname annotation | External DNS pod logs; confirm the role allows `route53:ChangeResourceRecordSets` on *that* zone |
| Pod `ContainerCreating`, "failed to assign an IP" | VPC CNI IP exhaustion in the subnet | widen subnet CIDR or enable prefix delegation (§7) |
| `PersistentVolumeClaim` stuck `Pending` | EBS CSI can't provision — IRSA missing, or volume/pod AZ mismatch | EBS CSI controller logs; confirm `volumeBindingMode: WaitForFirstConsumer` (§6) |

The meta-lesson, again: **every one of these is an IAM or a tagging problem before it is a Kubernetes problem.** When the cluster misbehaves, your first two questions are "which controller owns this arrow?" and "what IAM role does that controller assume, and is it scoped right?" Answer those and the unhelpful error message stops mattering.

---

## 12. Seeing the cluster: observability and the metrics that matter

You cannot operate what you cannot see, and a Karpenter-driven Spot cluster is *more* dynamic than a fixed fleet — nodes come and go, pods reschedule, capacity flexes. Week 12 goes deep on observability; here is the minimum you wire from day one so the exercises and the capstone are debuggable.

- **Container Insights** — the managed CloudWatch integration that collects per-pod, per-node, and per-namespace CPU/memory/network metrics, plus performance log events. Enable it on the cluster (it's a one-line add-on) and you get dashboards without standing up anything yourself. It is the fastest way to answer "is this pod throttled or is the node starved?"
- **The metrics-server** — not optional. The Horizontal Pod Autoscaler and `kubectl top` both read from it. No metrics-server, no HPA, no `kubectl top pods`. Install it as an add-on early.
- **Karpenter's own metrics** — Karpenter exports Prometheus metrics on node provisioning latency, consolidation actions, and Spot interruptions. When someone asks "how often are we getting interrupted?" the answer is a metric, not a guess. Scrape it.
- **The four signals to alarm on** for a service like our FastAPI app: pod restart rate (crash loops), pod CPU/memory against requests (right-sizing and OOMKills), ALB target 5xx rate and target-group healthy-host count (the LB Controller's view of health), and Karpenter pending-pod duration (capacity not arriving fast enough). Those four catch the overwhelming majority of "the cluster feels broken" pages.

The principle: **the dynamism that makes EKS-on-Spot cheap is the same dynamism that makes it opaque.** A node you've never seen before is now running your pod; a consolidation event just moved three pods at 2 a.m. Without Container Insights and Karpenter metrics, you are debugging blind. With them, the cascade from §8 is visible end to end, and the debugging playbook in §11 becomes "read the dashboard" instead of "tail seven logs."

This is also where the cost story closes the loop: Container Insights surfaces per-namespace CPU/memory utilization, which is exactly the data you need to prove your requests/limits are right-sized — the §9 discipline that decides whether Karpenter bin-packs tightly or wastes half a node per pod. Observability is not separate from FinOps on EKS; it is the instrument you read the bill through.

---

## 13. What to carry into the exercises

- **EKS = control plane + a dozen bolt-ons**, and every bolt-on is an IAM problem first.
- **Node strategy:** tiny On-Demand managed group for controllers, Karpenter-on-Spot for the bulk, Fargate profiles for isolation.
- **IRSA mechanics:** OIDC provider → SA annotation → injected web-identity JWT → `sts:AssumeRoleWithWebIdentity` → trust policy pins the `:sub`. Pin the subject; prove the negative.
- **One narrowly-scoped IRSA role per controller and per app.** Blast-radius control, not bureaucracy.
- **The deployment order** and the cascade you watch when the app lands.
- **Tear it down nightly.** The control-plane fee does not sleep.

In Exercise 2 you will do all of this for the FastAPI service: Karpenter on Spot Graviton, IRSA scoped to one S3 prefix, the LB Controller fronting it with an ALB. Then in the challenge you'll benchmark it against the Fargate and Lambda deployments and find out — in dollars and milliseconds — when this operational weight is worth carrying.
