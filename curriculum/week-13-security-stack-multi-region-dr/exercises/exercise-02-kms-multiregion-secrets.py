#!/usr/bin/env python3
"""
Exercise 2 — A multi-Region KMS key (primary + replica) and a Secrets Manager
secret with automatic rotation, proven with boto3.

Estimated time: ~75 minutes.   Cost: cents ($1/CMK-month prorated, a couple of
                                       secret-months, a handful of KMS API calls).

WHAT THIS DOES
--------------
The whole point is the property that makes encrypted cross-Region replication
work (mini-project + Friday drill): a multi-Region KMS key lets you encrypt in
one Region and decrypt in another, because the primary and replica share key
material. This script:

  1. Creates a MULTI-REGION primary CMK in the primary Region (us-east-1) with
     a key policy that SEPARATES administrators from users, and rotation on.
  2. Replicates it to the DR Region (us-west-2). The replica shares key material.
  3. Encrypts a plaintext blob with the PRIMARY key in us-east-1, then DECRYPTS
     the SAME ciphertext with the REPLICA key in us-west-2 -- proving the
     cross-Region-decrypt property. This is the load-bearing fact for S3 CRR.
  4. Creates a Secrets Manager secret (a generated DB credential) encrypted with
     the CMK, and configures automatic rotation, then forces one rotation and
     shows the value changed without the value ever appearing in source.

HOW TO RUN
----------
    python -m venv .venv && source .venv/bin/activate
    pip install boto3            # boto3 is the only dependency
    export PRIMARY_REGION=us-east-1
    export REPLICA_REGION=us-west-2
    python exercise-02-kms-multiregion-secrets.py

ACCEPTANCE CRITERIA
-------------------
  [ ] A multi-Region primary CMK exists in PRIMARY_REGION with key rotation on
      and a key policy that splits admin from usage.
  [ ] A replica of that key exists in REPLICA_REGION sharing key material.
  [ ] A ciphertext encrypted in PRIMARY_REGION decrypts with the REPLICA key in
      REPLICA_REGION (the script prints the round-tripped plaintext).
  [ ] A Secrets Manager secret encrypted with the CMK exists, with rotation
      configured, and a forced rotation produced a NEW value.
  [ ] You can explain WHY the cross-Region decrypt works (shared key material).

SMOKE OUTPUT (your key ids will differ)
---------------------------------------
    Created multi-Region primary key: mrk-1234abcd... (us-east-1)
    Replicated to us-west-2: arn:aws:kms:us-west-2:...:key/mrk-1234abcd...
    Encrypted in us-east-1, decrypted in us-west-2 -> "capstone-db-password-seed"
      ^ same key material in both Regions; this is what makes encrypted CRR work.
    Secret capstone/aurora/app created; pre-rotation version != post-rotation version. Good.
"""

from __future__ import annotations

import base64
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

PRIMARY_REGION = os.environ.get("PRIMARY_REGION", "us-east-1")
REPLICA_REGION = os.environ.get("REPLICA_REGION", "us-west-2")
ACCOUNT = boto3.client("sts").get_caller_identity()["Account"]

kms_primary = boto3.client("kms", region_name=PRIMARY_REGION)
kms_replica = boto3.client("kms", region_name=REPLICA_REGION)
secrets = boto3.client("secretsmanager", region_name=PRIMARY_REGION)
iam = boto3.client("iam")


def key_policy() -> str:
    """A key policy that DELEGATES to IAM (root statement) and SEPARATES admin
    from usage. The root 'kms:*' is delegation, not a blanket grant -- see
    Lecture 1. We grant usage to the account root here for the lab; in the
    capstone you grant it to specific app/replication roles."""
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    # Delegation to IAM. WITHOUT this, no IAM policy can grant on the key.
                    "Sid": "EnableIAMUserPermissions",
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                    "Action": "kms:*",
                    "Resource": "*",
                },
                {
                    # Key ADMINISTRATORS: manage the key, may NOT use it to crypt.
                    "Sid": "KeyAdministrators",
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                    "Action": [
                        "kms:Create*", "kms:Describe*", "kms:Enable*", "kms:List*",
                        "kms:Put*", "kms:Update*", "kms:Revoke*", "kms:Disable*",
                        "kms:Get*", "kms:Delete*", "kms:ScheduleKeyDeletion",
                        "kms:ReplicateKey", "kms:UpdatePrimaryRegion",
                    ],
                    "Resource": "*",
                },
                {
                    # Key USERS: use the key to crypt, may NOT administer it.
                    "Sid": "KeyUsers",
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                    "Action": [
                        "kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*",
                        "kms:GenerateDataKey*", "kms:DescribeKey",
                    ],
                    "Resource": "*",
                },
            ],
        }
    )


def step_1_create_primary() -> str:
    """Create a multi-Region primary CMK with rotation on."""
    print("Step 1: create multi-Region primary CMK ...")
    resp = kms_primary.create_key(
        Description="C19 wk13 multi-Region CMK (lake/DB/secrets)",
        MultiRegion=True,  # <-- the flag that makes this replicable across Regions
        Policy=key_policy(),
        Tags=[
            {"TagKey": "team", "TagValue": "platform"},
            {"TagKey": "service", "TagValue": "capstone"},
            {"TagKey": "environment", "TagValue": "lab"},
        ],
    )
    key_id = resp["KeyMetadata"]["KeyId"]
    arn = resp["KeyMetadata"]["Arn"]
    # Turn on automatic annual rotation (transparent; same key id/ARN, new material).
    kms_primary.enable_key_rotation(KeyId=key_id)
    # A friendly alias so you don't pass raw key ids around.
    try:
        kms_primary.create_alias(AliasName="alias/capstone-data", TargetKeyId=key_id)
    except ClientError as e:
        if e.response["Error"]["Code"] != "AlreadyExistsException":
            raise
    print(f"  Created multi-Region primary key: {key_id} ({PRIMARY_REGION})")
    print(f"  ARN: {arn}")
    return arn


def step_2_replicate(primary_arn: str) -> str:
    """Replicate the primary into the DR Region. The replica SHARES key material."""
    print(f"Step 2: replicate the key into {REPLICA_REGION} ...")
    key_id = primary_arn.split("/")[-1]
    try:
        resp = kms_primary.replicate_key(
            KeyId=primary_arn,
            ReplicaRegion=REPLICA_REGION,
            Policy=key_policy(),
            Description="C19 wk13 multi-Region CMK replica",
        )
        replica_arn = resp["ReplicaKeyMetadata"]["Arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            # Already replicated on a prior run; reconstruct the replica ARN.
            replica_arn = (
                f"arn:aws:kms:{REPLICA_REGION}:{ACCOUNT}:key/{key_id}"
            )
        else:
            raise
    # A replica's rotation is managed from the primary; just alias it locally.
    try:
        kms_replica.create_alias(AliasName="alias/capstone-data", TargetKeyId=key_id)
    except ClientError as e:
        if e.response["Error"]["Code"] != "AlreadyExistsException":
            raise
    print(f"  Replicated to {REPLICA_REGION}: {replica_arn}")
    return replica_arn


def step_3_cross_region_decrypt(primary_arn: str, replica_arn: str) -> None:
    """Encrypt in the primary Region; decrypt the SAME ciphertext with the replica
    in the DR Region. This is the property that makes encrypted S3 CRR work."""
    print("Step 3: prove cross-Region decrypt (the CRR-enabling property) ...")
    plaintext = b"capstone-db-password-seed"

    enc = kms_primary.encrypt(KeyId=primary_arn, Plaintext=plaintext)
    ciphertext = enc["CiphertextBlob"]
    print(f"  Encrypted in {PRIMARY_REGION} "
          f"({len(base64.b64encode(ciphertext))} b64 bytes of ciphertext).")

    # Decrypt with the REPLICA key in the OTHER Region. No KeyId needed for symmetric
    # decrypt, but we pass it to prove we're using the replica explicitly.
    dec = kms_replica.decrypt(CiphertextBlob=ciphertext, KeyId=replica_arn)
    roundtripped = dec["Plaintext"].decode()
    assert roundtripped == plaintext.decode(), "cross-Region decrypt mismatch!"
    print(f'  Encrypted in {PRIMARY_REGION}, decrypted in {REPLICA_REGION} -> "{roundtripped}"')
    print("    ^ same key material in both Regions; this is what makes encrypted CRR work.")


def step_4_rotated_secret(primary_arn: str) -> None:
    """Create a CMK-encrypted, generated secret and prove rotation changes it.

    NOTE: full Secrets-Manager rotation needs a rotation Lambda (the four-step
    contract: createSecret/setSecret/testSecret/finishSecret) plus a reachable
    database. For the lab we demonstrate the PROPERTY -- a generated value the
    code never sees, and a version change on rotation -- by putting a new
    generated value, which is exactly what the rotation Lambda's createSecret
    step does. In the capstone, addRotationSchedule(HostedRotation...) wires the
    real RDS rotation Lambda."""
    print("Step 4: create a CMK-encrypted secret and rotate it ...")
    name = "capstone/aurora/app"

    # generate-random produces a value the code never constructs or logs.
    pw1 = secrets.get_random_password(
        PasswordLength=32, ExcludePunctuation=True
    )["RandomPassword"]
    try:
        secrets.create_secret(
            Name=name,
            KmsKeyId=primary_arn,  # CMK, not the default aws/secretsmanager key
            SecretString=json.dumps({"username": "app", "password": pw1}),
            Tags=[{"Key": "service", "Value": "capstone"}],
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceExistsException":
            secrets.put_secret_value(
                SecretId=name,
                SecretString=json.dumps({"username": "app", "password": pw1}),
            )
        else:
            raise
    v1 = secrets.describe_secret(SecretId=name)["VersionIdsToStages"]
    pre_version = list(v1.keys())[0]

    # Simulate the rotation Lambda's createSecret step: put a NEW generated value.
    pw2 = secrets.get_random_password(
        PasswordLength=32, ExcludePunctuation=True
    )["RandomPassword"]
    secrets.put_secret_value(
        SecretId=name,
        SecretString=json.dumps({"username": "app", "password": pw2}),
    )
    time.sleep(1)
    v2 = secrets.describe_secret(SecretId=name)["VersionIdsToStages"]
    post_version = [vid for vid, stages in v2.items() if "AWSCURRENT" in stages][0]

    assert pre_version != post_version, "rotation did not change the version!"
    assert pw1 != pw2, "rotated value did not change!"
    print(f"  Secret {name} created; pre-rotation version != post-rotation version. Good.")
    print("    The password was generated, never written in source, and changed on rotation.")
    print("    In the capstone, HostedRotation.postgreSqlSingleUser() does this against Aurora.")


def main() -> None:
    print(f"PrimaryRegion={PRIMARY_REGION}  ReplicaRegion={REPLICA_REGION}  Account={ACCOUNT}\n")
    primary_arn = step_1_create_primary()
    replica_arn = step_2_replicate(primary_arn)
    step_3_cross_region_decrypt(primary_arn, replica_arn)
    step_4_rotated_secret(primary_arn)
    print("\nDone. Keep this key -- the mini-project's S3 CRR uses replicaKmsKeyId =")
    print(f"  {replica_arn}")
    print("\nCLEANUP when finished with the WHOLE week (a multi-Region key delete is")
    print("a two-step, waiting-period operation -- delete the replica first, then the")
    print("primary, each with schedule-key-deletion --pending-window-in-days 7):")
    print(f"  aws kms schedule-key-deletion --region {REPLICA_REGION} "
          f"--key-id {replica_arn} --pending-window-in-days 7")
    print(f"  aws secretsmanager delete-secret --region {PRIMARY_REGION} "
          "--secret-id capstone/aurora/app --recovery-window-in-days 7")


if __name__ == "__main__":
    main()
