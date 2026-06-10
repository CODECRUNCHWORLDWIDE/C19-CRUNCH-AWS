#!/usr/bin/env python3
"""
Exercise 3 — Deploy the ADOT collector as an EKS DaemonSet with IRSA, point a
test pod at it, and route traces to X-Ray + metrics to CloudWatch.

Estimated time: ~90 minutes.
Cost: an EKS cluster is ~$0.10/hour for the control plane PLUS node-group
      instance cost. DELETE OR SCALE THE CLUSTER TO ZERO WHEN YOU FINISH.
      If you still have a Week-5/8 cluster, reuse it (set CLUSTER below).

WHAT THIS DOES
--------------
This is an ORCHESTRATION script: it shells out to eksctl/kubectl to do the EKS
work (there is no clean boto3 path for `eksctl create iamserviceaccount` + IRSA),
and it writes the Kubernetes manifests to disk so you can read them. It:

  1. Creates an IRSA-bound ServiceAccount `adot-collector` in `observability`
     with EXACTLY two managed policies: X-Ray write + CloudWatch agent/EMF write.
     IRSA = the pod gets scoped creds, NOT the node role. (Week 5 idea.)
  2. Writes and applies a ConfigMap (the collector config: OTLP in, awsxray +
     awsemf out) and a DaemonSet (one collector pod per node) that uses that SA.
  3. Writes and applies a tiny traced test pod that emits OTLP to the collector.
  4. Tails the collector logs so you can watch traces being exported to X-Ray.

The collector config is the SAME shape as the Lambda one from Exercise 2 -- the
only thing that changed between "serverless" and "EKS" is the COLLECTOR'S
DEPLOYMENT TOPOLOGY, not your instrumentation. That is the whole lesson.

PREREQUISITES
-------------
  - An EKS cluster with an OIDC provider (IRSA) enabled. `eksctl utils
    associate-iam-oidc-provider --cluster <name> --approve` if not.
  - kubectl, eksctl on PATH and pointed at the cluster.
  - Permission to create IAM roles and EKS service accounts.

HOW TO RUN
----------
    export REGION=us-east-1
    export CLUSTER=c19-eks            # your existing cluster
    python exercise-03-adot-eks-daemonset.py            # deploy
    python exercise-03-adot-eks-daemonset.py --cleanup  # remove the k8s objects + SA

ACCEPTANCE CRITERIA
-------------------
  [ ] An IRSA ServiceAccount `adot-collector` exists, bound to an IAM role with
      X-Ray write + CloudWatch agent policies (NOT granted to the node role).
  [ ] A DaemonSet runs one `adot-collector` pod per node, using that SA.
  [ ] A test pod sends OTLP traces through the collector to X-Ray (visible in
      the X-Ray service map).
  [ ] Collector logs show the awsxray exporter shipping segments.
  [ ] Cleanup removes the DaemonSet, ConfigMap, test pod, and IRSA SA.

SMOKE OUTPUT
------------
    [1/4] creating IRSA service account adot-collector ...
    [2/4] applying collector ConfigMap + DaemonSet ...
    daemonset.apps/adot-collector created
    [3/4] applying traced test pod ...
    pod/otel-test created
    [4/4] tailing collector logs (Ctrl-C to stop) ...
    ... awsxrayexporter  exported 3 segments
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

REGION = os.environ.get("REGION", "us-east-1")
CLUSTER = os.environ.get("CLUSTER", "c19-eks")
NAMESPACE = "observability"
SA_NAME = "adot-collector"


def sh(cmd: str, check: bool = True) -> None:
    """Run a shell command, streaming output."""
    print(f"  $ {cmd}")
    subprocess.run(cmd, shell=True, check=check)


# ---------------------------------------------------------------------------
# Collector config -- IDENTICAL SHAPE to the Lambda case. OTLP in, X-Ray +
# CloudWatch EMF out. The awscontainerinsightreceiver line (commented) is how
# you'd add Container Insights node metrics from the same collector.
# ---------------------------------------------------------------------------
COLLECTOR_CONFIG = f"""
apiVersion: v1
kind: ConfigMap
metadata:
  name: adot-collector-config
  namespace: {NAMESPACE}
data:
  collector.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317      # app pods on this node send OTLP here
          http:
            endpoint: 0.0.0.0:4318
      # awscontainerinsightreceiver: {{}}   # uncomment to also emit Container Insights metrics
    processors:
      batch: {{}}
    exporters:
      awsxray:
        region: {REGION}
      awsemf:
        region: {REGION}
        namespace: MyApp/EKS
    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [batch]
          exporters: [awsxray]
        metrics:
          receivers: [otlp]
          processors: [batch]
          exporters: [awsemf]
"""

# DaemonSet: one collector per node, using the IRSA-bound ServiceAccount.
DAEMONSET = f"""
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: adot-collector
  namespace: {NAMESPACE}
spec:
  selector:
    matchLabels:
      app: adot-collector
  template:
    metadata:
      labels:
        app: adot-collector
    spec:
      serviceAccountName: {SA_NAME}        # IRSA -> scoped X-Ray + CW creds, NOT node role
      containers:
        - name: adot-collector
          image: public.ecr.aws/aws-observability/aws-otel-collector:latest
          args: ["--config=/etc/otel/collector.yaml"]
          ports:
            - containerPort: 4317
              hostPort: 4317              # so app pods reach it via the node IP
          volumeMounts:
            - name: config
              mountPath: /etc/otel
      volumes:
        - name: config
          configMap:
            name: adot-collector-config
"""

# A minimal traced test pod. It uses the OTel auto-instrumentation image to emit
# a few spans to the collector at the node's IP (status.hostIP), proving the path.
TEST_POD = """
apiVersion: v1
kind: Pod
metadata:
  name: otel-test
  namespace: observability
spec:
  restartPolicy: Never
  containers:
    - name: otel-test
      image: public.ecr.aws/docker/library/python:3.12-slim
      env:
        - name: NODE_IP
          valueFrom:
            fieldRef:
              fieldPath: status.hostIP
      command: ["/bin/sh", "-c"]
      args:
        - |
          pip install --quiet opentelemetry-distro opentelemetry-exporter-otlp >/dev/null
          export OTEL_SERVICE_NAME=otel-test
          export OTEL_TRACES_EXPORTER=otlp
          export OTEL_EXPORTER_OTLP_ENDPOINT="http://${NODE_IP}:4317"
          export OTEL_PROPAGATORS=xray
          python - <<'PY'
          import time
          from opentelemetry import trace
          from opentelemetry.sdk.trace import TracerProvider
          from opentelemetry.sdk.trace.export import BatchSpanProcessor
          from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
          from opentelemetry.sdk.resources import Resource
          provider = TracerProvider(resource=Resource.create({"service.name": "otel-test"}))
          provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
          trace.set_tracer_provider(provider)
          tracer = trace.get_tracer("otel-test")
          for i in range(5):
              with tracer.start_as_current_span("work") as s:
                  s.set_attribute("iteration", i)
                  time.sleep(0.2)
          provider.shutdown()  # flush remaining spans before exit
          print("emitted 5 spans to the collector")
          PY
          sleep 30
"""


def apply_manifest(text: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(text)
        path = f.name
    sh(f"kubectl apply -f {path}")


def deploy() -> None:
    sh(f"kubectl create namespace {NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -")

    print("[1/4] creating IRSA service account adot-collector ...")
    # eksctl wires the IAM role + OIDC trust so ONLY this SA can assume it.
    sh(
        f"eksctl create iamserviceaccount "
        f"--cluster {CLUSTER} --namespace {NAMESPACE} --name {SA_NAME} "
        f"--attach-policy-arn arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess "
        f"--attach-policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy "
        f"--region {REGION} --approve --override-existing-serviceaccounts"
    )

    print("[2/4] applying collector ConfigMap + DaemonSet ...")
    apply_manifest(COLLECTOR_CONFIG)
    apply_manifest(DAEMONSET)
    sh(f"kubectl -n {NAMESPACE} rollout status daemonset/adot-collector --timeout=120s")

    print("[3/4] applying traced test pod ...")
    apply_manifest(TEST_POD)
    sh(f"kubectl -n {NAMESPACE} wait --for=condition=Ready pod/otel-test --timeout=120s", check=False)

    print("[4/4] tailing collector logs (Ctrl-C to stop) ...")
    print("   look for: 'awsxrayexporter' shipping segments, then check the X-Ray console.")
    sh(f"kubectl -n {NAMESPACE} logs -l app=adot-collector --tail=40 -f", check=False)


def cleanup() -> None:
    sh(f"kubectl -n {NAMESPACE} delete pod otel-test --ignore-not-found")
    sh(f"kubectl -n {NAMESPACE} delete daemonset adot-collector --ignore-not-found")
    sh(f"kubectl -n {NAMESPACE} delete configmap adot-collector-config --ignore-not-found")
    sh(
        f"eksctl delete iamserviceaccount --cluster {CLUSTER} "
        f"--namespace {NAMESPACE} --name {SA_NAME} --region {REGION}",
        check=False,
    )
    print(
        "removed DaemonSet/ConfigMap/pod/SA. The CLUSTER itself is still running -- "
        "if you created it for this exercise, delete it now:\n"
        f"    eksctl delete cluster --name {CLUSTER} --region {REGION}"
    )


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        deploy()
