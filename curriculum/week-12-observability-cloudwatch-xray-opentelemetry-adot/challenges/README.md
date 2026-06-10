# Week 12 — Challenges

One challenge this week. It is the synthesis of both lectures: it takes the instrumented API from the exercises, puts a real SLO on it, builds the multi-window multi-burn-rate alarm that the Google SRE workbook describes, and then *proves the alarm works* by injecting a controlled outage and measuring how fast it pages and how fast it clears.

## Index

1. **[Challenge 1 — Burn-rate SLO and a synthetic outage](challenge-01-burn-rate-slo-and-synthetic-outage.md)** — define a 99.9% availability SLO, build a multi-window burn-rate alarm with the fast burns routed to "page" and slow burns to "ticket," fire a synthetic outage, and record the detection time and the recovery-confirmation time. (~2.5–3 h)

## How to approach it

- This is the capstone's observability spine in miniature. The capstone spec requires "burn-rate alarms on a 99.9% SLO" verbatim; this is where you build them.
- The deliverable is **working alarms AND a written `SLO.md`** with the measured numbers — the detection time, the recovery-confirmation time, and the burn-rate arithmetic. Alarms without the measured proof, or the writeup without the alarms, is incomplete.
- An alarm you have never watched fire is a hope, not a control. The whole point is the synthetic-outage step: you deliberately break the service and watch the right alarm transition at the right moment.
- Bring the instrumented API from Exercise 2 (or the mini-project's), and redeploy whatever you tore down. Tear it down again when you finish capturing numbers.
