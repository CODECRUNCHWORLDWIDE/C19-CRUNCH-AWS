# Week 2 — Challenges

The exercises drill the mechanics — build the topology, attach the boundary, run
the analyzer. **The challenge tests the one skill this whole week is about:
reading a policy out loud and finding the bug.** It is the closest thing in C19
to the live "Read this policy out loud. Now break it." lecture, done solo, with
the simulator as your judge.

## Index

1. **[Challenge 1 — Find the Bug in Twelve Policies](challenge-01-find-the-bug-in-twelve-policies.md)** — twelve real-world IAM policies, each seeded with exactly one flaw (over-broad wildcard, missing condition, confused-deputy gap, wrong ARN granularity, a `Not*` trap, a privilege-escalation primitive). For each: name the bug, explain the evaluation logic that makes it dangerous, write the fix, and prove the bug with `aws iam simulate-custom-policy`. (~3.5h)

The challenge is **not optional** this week. It is the Friday block in the
schedule and the artifact your cohort peer-reviews on Sunday. The lecture showed
you twelve bugs and named them; the challenge gives you twelve *new* ones and
makes you do the naming yourself. If you can do this, you are the engineer who
catches the IAM bug in review — which is the entire point of Week 2.

## How the challenge is graded (peer review, Sunday)

Your reviewer checks three things per policy:

1. **Did you find the right bug?** (There is exactly one seeded flaw per policy.)
2. **Can you explain the evaluation logic that makes it dangerous?** Not "it's
   too broad" — *why* the engine grants more than intended, in terms of the
   five-step decision flow from Lecture 1.
3. **Does your fix actually fix it, proven by the simulator?** A fix you did not
   simulate is a hypothesis.

A bug found by accident, without the evaluation-logic explanation, scores zero.
The explanation is the skill.
