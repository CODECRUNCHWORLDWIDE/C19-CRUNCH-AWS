# Week 12 — Exercises

Three exercises that build on each other. The first wires CloudWatch Logs, EMF metrics, and alarms. The second instruments a Lambda with OpenTelemetry and the ADOT extension, sending traces to X-Ray. The third deploys the ADOT collector as an EKS DaemonSet with IRSA. Do them in order — Exercise 2 reuses the structured-logging habit from Exercise 1, and the mini-project assumes all three are done.

## Index

1. **[Exercise 1 — CloudWatch Logs, EMF, and alarms](exercise-01-cloudwatch-logs-emf-alarms.md)** — emit structured JSON logs and an EMF custom metric from a Lambda, query them in Logs Insights, build a metric filter and a static-threshold alarm, and watch it fire. (~75 min)
2. **[Exercise 2 — ADOT on Lambda + X-Ray](exercise-02-adot-lambda-xray.py)** — attach the ADOT extension layer, auto-instrument boto3, add a manual span, send traces to X-Ray, and read the service map. (~90 min)
3. **[Exercise 3 — ADOT collector as an EKS DaemonSet](exercise-03-adot-eks-daemonset.py)** — create the IRSA service account, deploy the collector DaemonSet, point a pod at it, and route traces to X-Ray and metrics to CloudWatch. (~90 min)

## Before you start

- **AWS CLI v2** configured with a profile that can use CloudWatch, Logs, X-Ray, Lambda, IAM, and (for Exercise 3) EKS. `aws --version` should report `aws-cli/2.x`.
- **Python 3.12+** with the per-exercise `requirements.txt`. A clean virtualenv per exercise keeps the OTel deps tidy.
- **A Region you'll stick with all week.** `us-east-1` is assumed in the examples; if you use another, change it everywhere — and remember the **ADOT layer ARN is Region-specific**.
- **An EKS cluster with IRSA (OIDC) enabled** for Exercise 3. If you tore down your Week-5 cluster, the exercise notes how to stand a minimal one back up, but budget time — `eksctl create cluster` is slow.
- **`kubectl`, `helm`, and `eksctl`** on your PATH for Exercise 3.

## How to work the exercises

- Read the prompt. Skim, don't memorize.
- **Type the commands and code yourself.** Copy-pasting AWS CLI calls teaches you nothing; typing them builds the muscle memory you need in an incident — and an incident is exactly when you'll reach for these.
- Run it. Read the output. When you open the X-Ray service map, stop and ask *which span carries the latency* and *why*.
- Tear down what costs money when you finish each session: delete the EKS cluster or scale node groups to zero, delete test Lambdas, and set retention on every log group you created. A forgotten EKS cluster is a far worse weekend surprise than a Lambda.
- Every exercise ends with a checkable artifact: a Logs Insights result, a trace in the X-Ray console, or a metric in CloudWatch sourced from the DaemonSet. If you don't have it, you're not done.

## Cost note

Exercise 1 costs cents (a little log ingestion, a few custom metrics, one alarm). Exercise 2 costs cents plus per-trace X-Ray charges (you record a few hundred traces). **Exercise 3 is the expensive one: an EKS cluster is ~$0.10/hour for the control plane plus node-group instance cost.** Stand the cluster up for the session and **scale node groups to zero or `eksctl delete cluster` when you finish** — leaving an EKS cluster running over the weekend is a real bill. If you still have a live cluster from Week 5/8, reuse it.

There are no solutions checked in. The course is open source — solutions live in forks. After you finish, search GitHub for `c19-week-12` to compare.
