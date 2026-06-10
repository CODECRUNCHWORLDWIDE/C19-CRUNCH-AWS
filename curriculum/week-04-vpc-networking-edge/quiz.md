# Week 4 — Quiz

Fourteen questions covering CIDR planning, subnet tiers, NAT vs endpoints, Security Groups vs NACLs, PrivateLink/TGW/peering, Route 53 routing policies, CloudFront, ACM, and WAF. Take it with your lecture notes closed. Aim for 12/14 before moving to Week 5. Answer key at the bottom — don't peek.

---

**Q1.** You give a subnet the CIDR `10.0.16.0/28`. How many IP addresses can you actually assign to instances, ENIs, and endpoints in it?

- A) 16
- B) 14
- C) 11
- D) 8

---

**Q2.** What single thing determines whether a subnet is "public," "private," or "isolated" in AWS?

- A) A checkbox labelled "public" you set at subnet creation.
- B) Whether the subnet has a public IPv4 CIDR.
- C) The subnet's associated route table — specifically what its default route (`0.0.0.0/0`) targets, if anything.
- D) Which Availability Zone the subnet lives in.

---

**Q3.** Your dev VPC spans three AZs. To minimize the recurring bill while still allowing private instances outbound internet access, how many NAT Gateways should you provision?

- A) Three — one per AZ, always, for high availability.
- B) Two — a primary and a standby.
- C) One — accept that an AZ failure degrades egress in a dev account.
- D) Zero — NAT Gateways are never needed if you have an Internet Gateway.

---

**Q4.** A private instance with no public IP runs `aws s3 cp s3://my-bucket/file /tmp/file`. There is an **S3 gateway endpoint** attached to the subnet's route table and also a NAT default route. Which path does the S3 traffic take, and why?

- A) The NAT Gateway, because `0.0.0.0/0` matches first.
- B) The S3 gateway endpoint, because the endpoint injects an S3 prefix-list route that is more specific than `0.0.0.0/0` (longest-prefix match).
- C) It is split 50/50 across both for load balancing.
- D) It fails — you cannot have both a gateway endpoint and a NAT route in the same table.

---

**Q5.** Order these four egress mechanisms from cheapest to most expensive *per month, idle*: Internet Gateway, NAT Gateway, S3 gateway endpoint, interface endpoint (single AZ).

- A) Interface endpoint < IGW < gateway endpoint < NAT Gateway
- B) IGW = gateway endpoint (both free) < interface endpoint (~$7/mo) < NAT Gateway (~$33/mo)
- C) NAT Gateway < interface endpoint < gateway endpoint < IGW
- D) They all cost the same per hour; only data processing differs.

---

**Q6.** You deploy a container into an **isolated** subnet that must `docker pull` from a private ECR repository. You add interface endpoints for `ecr.api` and `ecr.dkr`, but the pull still fails. What is the single most likely missing piece?

- A) A NAT Gateway — ECR always needs internet.
- B) The **S3 gateway endpoint** — ECR stores image layers in S3, so the pull needs an S3 path.
- C) A second ECR DKR endpoint in another AZ.
- D) Private DNS is not supported for ECR, so it can never work in an isolated subnet.

---

**Q7.** Which statement about Security Groups vs Network ACLs is correct?

- A) Both are stateless; you must allow return traffic explicitly in each.
- B) Security Groups are stateful and allow-only; NACLs are stateless, subnet-scoped, and support explicit deny.
- C) NACLs are attached to ENIs; Security Groups are attached to subnets.
- D) Security Groups support explicit deny rules; NACLs do not.

---

**Q8.** A client behind a **custom NACL** makes an outbound HTTPS request and the connection hangs with no response. Outbound 443 is allowed. What did the engineer most likely forget?

- A) An inbound NACL rule allowing the ephemeral port range (1024–65535) for the return traffic — NACLs are stateless.
- B) To attach a Security Group to the subnet.
- C) To enable DNS resolution on the VPC.
- D) Nothing — outbound HTTPS cannot work through any NACL.

---

**Q9.** You need full connectivity among exactly three stable VPCs in one region, and cost matters. You then learn a fourth, fifth, and eventually twentieth VPC will join, with transitive routing and centralized control. Which choices are correct?

- A) Peering for all of it — peering scales fine to 20 VPCs.
- B) Transit Gateway from the start — peering never works for more than two VPCs.
- C) Peering for the initial three (cheap, simple, non-transitive is acceptable at that size); migrate to a Transit Gateway as the count grows and you need transitive, hub-and-spoke routing.
- D) PrivateLink endpoint services for all of it.

---

**Q10.** Why do you use a Route 53 **alias** record rather than a CNAME to point `example.com` (the zone apex) at a CloudFront distribution?

- A) CNAMEs are deprecated in Route 53.
- B) DNS forbids a CNAME at the zone apex; an alias is a Route 53 extension that works at the apex, is free to resolve, and tracks the target's IPs automatically.
- C) A CNAME at the apex costs $50/month; an alias is free.
- D) There is no difference; the two are interchangeable.

---

**Q11.** You run a blue environment at 90% of traffic and a green environment at 10% so you can watch dashboards before shifting more traffic. Which Route 53 routing policy implements this?

- A) Latency
- B) Failover
- C) Geolocation
- D) Weighted

---

**Q12.** You are creating an ACM certificate to attach to a CloudFront distribution for an app whose ALB runs in `eu-west-1`. In which region must the **CloudFront** certificate be issued?

- A) `eu-west-1` — same region as the ALB.
- B) `us-east-1` — CloudFront only attaches certificates from `us-east-1`.
- C) Any region; CloudFront is global and region-agnostic for certs.
- D) Both `eu-west-1` and `us-east-1`; you need one in each.

---

**Q13.** In a WAF web ACL, you add the `AWSManagedRulesCommonRuleSet` managed group and your own rate-based rule. Which field does each use to decide what happens on a match?

- A) Both use `action`.
- B) Both use `overrideAction`.
- C) Your rate-based rule uses `action` (`block`/`allow`/`count`); the managed group uses `overrideAction` (`none` to honor the group's actions, or `count` to dry-run).
- D) Managed groups use `action`; your own rules use `overrideAction`.

---

**Q14.** When is Shield Advanced ($3,000/month) the right call over Shield Standard (free)?

- A) Always — every production account should run Shield Advanced.
- B) Never — Shield Standard covers L7 attacks fully.
- C) Only for a public, revenue-critical, attack-attractive target where the $36k/year plus DDoS cost protection is cheaper than the risk; otherwise Standard plus a well-tuned WAF is correct.
- D) Only for internal services in private subnets.

---

## Answer key

<details>
<summary>Click to reveal answers</summary>

1. **C** — AWS reserves five addresses in every subnet (network, VPC router, DNS, future-use, broadcast). A `/28` has 16 addresses; 16 − 5 = **11** usable.
2. **C** — "Public/private/isolated" is purely a function of the route table. There is no "public" checkbox; there is only "does the default route go to an IGW (public), a NAT (private-with-egress), or nowhere off-VPC (isolated)?"
3. **C** — In dev/stage, one NAT Gateway total is the cost-sane default; an AZ failure degrading egress in a dev account is survivable. Three-per-AZ is correct for production with real egress needs, not for dev. Zero NAT is correct only when all egress is to AWS services (use endpoints).
4. **B** — The gateway endpoint adds a route whose destination is the S3 managed prefix list, which is more specific than `0.0.0.0/0`. Longest-prefix match sends the S3 traffic to the endpoint, transparently, with no application change.
5. **B** — IGW and gateway endpoints are both **free**. An interface endpoint is ~$0.01/hr/AZ (~$7.30/mo per AZ). A NAT Gateway is ~$0.045/hr (~$32.85/mo) before data. Memorize the hierarchy: IGW free, gateway endpoint free, interface endpoint cheap-and-metered, NAT Gateway expensive-and-metered.
6. **B** — ECR stores image layers in S3. Without the S3 gateway endpoint, the layer download has no path and the pull fails even with both ECR endpoints present. This is the single most common "why won't my private task start" bug.
7. **B** — Security Groups: stateful, ENI-scoped, allow-only. NACLs: stateless, subnet-scoped, numbered first-match with explicit allow *and* deny. D inverts the deny support (it is NACLs that support deny).
8. **A** — NACLs are stateless, so the return traffic to a high ephemeral port is not automatically allowed. You must add an inbound rule for the ephemeral range. A Security Group, being stateful, would never have this problem.
9. **C** — Peering is fine and cheap for two or three stable VPCs (non-transitive is acceptable there). Once you need many VPCs, transitive routing, and centralized control, a Transit Gateway is the right tool — connecting 20 VPCs by peering needs 190 connections; a TGW needs 20 attachments.
10. **B** — DNS forbids a CNAME at the zone apex. Route 53 alias records are a Route 53 extension that resolve the target's IPs internally, work at the apex, are free to resolve to AWS resources, and track IP changes automatically.
11. **D** — Weighted routing splits traffic by integer weights across records sharing a name; 90/10 is the canonical blue/green-canary use. Failover is active/passive; latency is nearest-region; geolocation is by user location.
12. **B** — For CloudFront the certificate **must** be in `us-east-1`, regardless of where the origin lives. The ALB's own cert can be in `eu-west-1`, but the CloudFront cert is `us-east-1`.
13. **C** — Your own rules use `action` (`block`/`allow`/`count`). Managed rule groups use `overrideAction` — `none` to honor the group's built-in actions, or `count` to run them in count-only dry-run mode while tuning.
14. **C** — Shield Standard (free, automatic, L3/L4) is right for almost everything. Shield Advanced is justified only for a public, revenue-critical, attack-attractive target where the cost (and its DDoS cost-protection credits) beats the risk. Reaching for it on a hobby project is the same mistake as three NAT Gateways in dev.

</details>

---

If you scored under 10, re-read the lecture for the questions you missed — Q4/Q6 point at Lecture 1 §7, Q12/Q13 at Lecture 2 §5–6. If you scored 13 or 14, you're ready for the [homework](./homework.md).
