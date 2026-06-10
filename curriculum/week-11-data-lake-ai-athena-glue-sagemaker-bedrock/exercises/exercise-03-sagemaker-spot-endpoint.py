#!/usr/bin/env python3
"""
Exercise 3 — Train a tiny scikit-learn classifier in SageMaker on managed Spot,
and deploy it to a SageMaker real-time endpoint.

Estimated time: ~90 minutes.
Cost: a Spot training job (cents) + a real-time endpoint (~$0.115/hour while it
      exists). DELETE THE ENDPOINT WHEN YOU FINISH -- the script's last step does
      it for you; do not skip it.

WHAT THIS DOES
--------------
  1. Builds a tiny tabular dataset (the classic 4-feature Iris set, from
     scikit-learn -- no external download) and uploads train/test CSVs to S3.
  2. Launches a SageMaker *training job* on a managed-Spot ml.m5.large with
     checkpointing, using the prebuilt scikit-learn framework container, and
     prints the Spot savings line.
  3. Deploys the fitted model to a REAL-TIME endpoint (always-on, low latency).
  4. Invokes the endpoint and prints predictions + a rough per-call latency.
  5. Tears the endpoint down.

This is the inference path the capstone's recommendation feature is built on.
The model is deliberately trivial; the POINT IS THE PLUMBING -- training job,
Spot, model artifact, endpoint config, endpoint, invoke, delete.

HOW TO RUN
----------
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements-ex03.txt      # sagemaker, scikit-learn, boto3, pandas
    export REGION=us-east-1
    # Run from SageMaker Studio (execution role auto-detected) OR locally with a
    # role ARN that SageMaker can assume:
    export SAGEMAKER_ROLE_ARN="arn:aws:iam::<acct>:role/<your-sagemaker-exec-role>"
    python exercise-03-sagemaker-spot-endpoint.py

NOTE ON THE TRAINING SCRIPT
---------------------------
SageMaker runs a *separate* entry-point script inside the training container.
This file writes that script (src/train.py) to disk at runtime so the exercise
is one self-contained file. In a real project train.py lives in source control.

ACCEPTANCE CRITERIA
-------------------
  [ ] A training job runs on use_spot_instances=True and prints a non-zero
      "Managed Spot Training savings" percentage.
  [ ] A real-time endpoint is created and returns predictions for test rows.
  [ ] You record a rough per-call latency (single-digit to low-double-digit ms).
  [ ] The endpoint is DELETED at the end (verify in the console / CLI).

SMOKE OUTPUT (your numbers will differ)
---------------------------------------
    Training seconds: 138
    Billable seconds: 46
    Managed Spot Training savings: 66.7%
    Endpoint 'iris-realtime-...' InService.
    predictions for 5 test rows: [0, 1, 2, 1, 0]
    rough per-call latency: p50 ~9.4 ms over 20 calls
    Endpoint deleted.
"""

from __future__ import annotations

import json
import os
import pathlib
import statistics
import time

import boto3
import pandas as pd
import sagemaker
from sagemaker.sklearn.estimator import SKLearn
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split

REGION = os.environ.get("REGION", "us-east-1")

# ---------------------------------------------------------------------------
# The training script that runs INSIDE the SageMaker scikit-learn container.
# Contract: data is mounted at SM_CHANNEL_TRAIN; the fitted model must be
# written to SM_MODEL_DIR; hyperparameters arrive as CLI args.
# ---------------------------------------------------------------------------
TRAIN_PY = '''
import argparse
import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--model-dir", type=str, default=os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    parser.add_argument("--train", type=str, default=os.environ.get("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    args = parser.parse_args()

    df = pd.read_csv(os.path.join(args.train, "train.csv"))
    X = df[["f0", "f1", "f2", "f3"]]
    y = df["label"]

    clf = RandomForestClassifier(
        n_estimators=args.n_estimators, max_depth=args.max_depth, random_state=42
    )
    clf.fit(X, y)
    print("train accuracy:", accuracy_score(y, clf.predict(X)))

    joblib.dump(clf, os.path.join(args.model_dir, "model.joblib"))


# The serving container calls model_fn to load the artifact, then input_fn /
# predict_fn / output_fn per request. Defaults handle JSON; we make it explicit.
def model_fn(model_dir):
    return joblib.load(os.path.join(model_dir, "model.joblib"))


if __name__ == "__main__":
    main()
'''


def write_train_script() -> str:
    src = pathlib.Path("src")
    src.mkdir(exist_ok=True)
    (src / "train.py").write_text(TRAIN_PY)
    return str(src)


def build_and_upload_data(session: sagemaker.Session, bucket: str) -> str:
    """Create train/test CSVs from the Iris dataset and upload train to S3."""
    data = load_iris(as_frame=True)
    df = data.frame.rename(
        columns={
            "sepal length (cm)": "f0",
            "sepal width (cm)": "f1",
            "petal length (cm)": "f2",
            "petal width (cm)": "f3",
            "target": "label",
        }
    )[["f0", "f1", "f2", "f3", "label"]]

    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df["label"])
    pathlib.Path("data").mkdir(exist_ok=True)
    train_df.to_csv("data/train.csv", index=False)
    test_df.to_csv("data/test.csv", index=False)

    train_s3 = session.upload_data("data/train.csv", bucket=bucket, key_prefix="iris/train")
    print(f"uploaded training data to {train_s3}")
    return train_s3


def get_role(session: sagemaker.Session) -> str:
    """Use the Studio execution role if present, else the env-provided ARN."""
    try:
        return sagemaker.get_execution_role()
    except Exception:
        arn = os.environ.get("SAGEMAKER_ROLE_ARN")
        if not arn:
            raise SystemExit(
                "Set SAGEMAKER_ROLE_ARN to a role SageMaker can assume, "
                "or run inside SageMaker Studio."
            )
        return arn


def train_on_spot(session: sagemaker.Session, role: str, source_dir: str, train_s3: str) -> SKLearn:
    estimator = SKLearn(
        entry_point="train.py",
        source_dir=source_dir,
        role=role,
        instance_type="ml.m5.large",
        instance_count=1,
        framework_version="1.2-1",
        py_version="py3",
        base_job_name="iris-spot",
        hyperparameters={"n-estimators": 200, "max-depth": 4},
        sagemaker_session=session,
        # --- managed Spot: the two lines that cut training cost ~2/3 ---
        use_spot_instances=True,
        max_wait=3600,   # wall-clock budget incl. waiting for Spot capacity
        max_run=1200,    # the job itself
        checkpoint_s3_uri=f"s3://{session.default_bucket()}/iris/checkpoints/",
    )
    estimator.fit({"train": train_s3})
    # The Spot savings line is printed in the job logs above by SageMaker;
    # we also fetch it from the job description for the record.
    desc = session.sagemaker_client.describe_training_job(
        TrainingJobName=estimator.latest_training_job.name
    )
    billable = desc.get("BillableTimeInSeconds")
    training = desc.get("TrainingTimeInSeconds")
    if billable and training:
        savings = (1 - billable / training) * 100 if training else 0
        print(f"Training seconds: {training}")
        print(f"Billable seconds: {billable}")
        print(f"Managed Spot Training savings: {savings:.1f}%")
    return estimator


def deploy_and_invoke(estimator: SKLearn) -> None:
    endpoint_name = f"iris-realtime-{int(time.time())}"
    print(f"deploying real-time endpoint {endpoint_name} (this takes a few minutes)...")
    predictor = estimator.deploy(
        initial_instance_count=1,
        instance_type="ml.m5.large",
        endpoint_name=endpoint_name,
        serializer=sagemaker.serializers.JSONSerializer(),
        deserializer=sagemaker.deserializers.JSONDeserializer(),
    )
    print(f"Endpoint '{endpoint_name}' InService.")

    try:
        test_df = pd.read_csv("data/test.csv")
        sample = test_df[["f0", "f1", "f2", "f3"]].head(5).values.tolist()
        preds = predictor.predict(sample)
        print(f"predictions for 5 test rows: {preds}")

        # Rough latency: 20 single-row calls, report p50.
        one = [test_df[["f0", "f1", "f2", "f3"]].iloc[0].tolist()]
        latencies = []
        for _ in range(20):
            t0 = time.perf_counter()
            predictor.predict(one)
            latencies.append((time.perf_counter() - t0) * 1000)
        print(f"rough per-call latency: p50 ~{statistics.median(latencies):.1f} ms over 20 calls")
    finally:
        # ALWAYS delete the endpoint. Real-time endpoints bill by the hour.
        predictor.delete_endpoint(delete_endpoint_config=True)
        print("Endpoint deleted.")


def main() -> None:
    boto_session = boto3.Session(region_name=REGION)
    session = sagemaker.Session(boto_session=boto_session)
    bucket = session.default_bucket()
    role = get_role(session)

    source_dir = write_train_script()
    train_s3 = build_and_upload_data(session, bucket)
    estimator = train_on_spot(session, role, source_dir, train_s3)
    deploy_and_invoke(estimator)
    print("\nDone. Confirm no endpoints remain: aws sagemaker list-endpoints")


if __name__ == "__main__":
    main()
