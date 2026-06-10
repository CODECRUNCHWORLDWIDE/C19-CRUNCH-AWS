"""
Exercise 3 — Shared EFS across Fargate and EC2

Goal: Create ONE EFS file system, an access point, and mount it into BOTH an
      ECS Fargate task and an EC2 instance at the SAME TIME. Then prove shared
      read/write with a round-trip file: write from EC2, read from Fargate,
      write back from Fargate, read on EC2.

Estimated time: ~2 hours.

This is a CDK app in Python (CDK v2). It deploys into the production VPC you
built in Week 4 (private + isolated subnets, S3/DynamoDB gateway endpoints).
We look the VPC up by tag so this stack does not recreate networking.

HOW TO USE THIS FILE

  1. New CDK Python app:

       mkdir c19-week6-efs && cd c19-week6-efs
       python -m venv .venv && source .venv/bin/activate
       pip install aws-cdk-lib constructs
       cdk init app --language python    # then replace app.py / the stack file

     (Or drop this file in as the stack and wire it into app.py — see the
     bottom of the file for the app entrypoint.)

  2. Set the VPC lookup tag to match YOUR Week-4 VPC, or pass a vpc_id.

  3. cdk diff ; cdk deploy

  4. Run the VERIFICATION steps at the bottom.

ACCEPTANCE CRITERIA

  [ ] cdk deploy succeeds; outputs the EFS file-system id, access-point id,
      the ECS cluster/service, and the EC2 instance id.
  [ ] The Fargate task and the EC2 instance both mount the same EFS at
      /mnt/shared.
  [ ] A file written on EC2 is readable inside the Fargate container, and a
      file written by Fargate is readable on EC2 (the round-trip).
  [ ] Transit encryption (TLS) is ENABLED on both mounts and IAM authorization
      is enforced via the access point.

TEAR-DOWN

  cdk destroy   # EFS at this size is pennies, but the EC2 instance is not free
                # to leave running — destroy it the same day.
"""

from aws_cdk import (
    App,
    Stack,
    Tags,
    CfnOutput,
    RemovalPolicy,
    Duration,
    aws_ec2 as ec2,
    aws_efs as efs,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class C19Week6EfsStack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)

        # --------------------------------------------------------------
        # 1. Reuse the Week-4 production VPC (do NOT make a new one).
        #    Adjust the tag filter to match how you tagged your VPC.
        # --------------------------------------------------------------
        vpc = ec2.Vpc.from_lookup(self, "Vpc", tags={"Name": "c19-prod-vpc"})

        # --------------------------------------------------------------
        # 2. One Security Group for EFS mount targets. NFS is TCP/2049.
        #    Both the EC2 instance and the Fargate tasks will be members
        #    of (or allowed by) this group so they can reach the mounts.
        # --------------------------------------------------------------
        efs_sg = ec2.SecurityGroup(
            self, "EfsSg", vpc=vpc,
            description="EFS mount-target SG (NFS 2049)",
            allow_all_outbound=True,
        )

        # --------------------------------------------------------------
        # 3. The EFS file system. Multi-AZ, Elastic throughput, encrypted,
        #    with lifecycle management moving cold files to IA after 30 days.
        # --------------------------------------------------------------
        file_system = efs.FileSystem(
            self, "Shared",
            vpc=vpc,
            security_group=efs_sg,
            encrypted=True,                                   # KMS at rest
            throughput_mode=efs.ThroughputMode.ELASTIC,
            lifecycle_policy=efs.LifecyclePolicy.AFTER_30_DAYS,        # -> IA
            out_of_infrequent_access_policy=efs.OutOfInfrequentAccessPolicy.AFTER_1_ACCESS,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            removal_policy=RemovalPolicy.DESTROY,             # dev only
        )

        # --------------------------------------------------------------
        # 4. An access point: enforce a POSIX user and a root directory so
        #    every client lands in /shared owned by uid/gid 1000.
        # --------------------------------------------------------------
        ap = file_system.add_access_point(
            "SharedAp",
            path="/shared",
            create_acl=efs.Acl(owner_uid="1000", owner_gid="1000", permissions="0775"),
            posix_user=efs.PosixUser(uid="1000", gid="1000"),
        )

        # --------------------------------------------------------------
        # 5. The EC2 side: a small instance that mounts EFS via user data.
        # --------------------------------------------------------------
        ec2_role = iam.Role(
            self, "Ec2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )
        # Allow the instance to use the EFS access point with IAM auth.
        file_system.grant(ec2_role, "elasticfilesystem:ClientMount", "elasticfilesystem:ClientWrite")

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "dnf install -y amazon-efs-utils",
            "mkdir -p /mnt/shared",
            # Mount with TLS + IAM + the access point.
            f"mount -t efs -o tls,iam,accesspoint={ap.access_point_id} "
            f"{file_system.file_system_id}:/ /mnt/shared",
            # Prove EC2 can write.
            "echo \"hello from EC2 $(hostname) at $(date -u +%FT%TZ)\" > /mnt/shared/from-ec2.txt",
            # Persist the mount across reboots.
            f"echo '{file_system.file_system_id}:/ /mnt/shared efs "
            f"_netdev,tls,iam,accesspoint={ap.access_point_id} 0 0' >> /etc/fstab",
        )

        instance = ec2.Instance(
            self, "Mounter",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            role=ec2_role,
            security_group=efs_sg,           # member of the EFS SG -> can reach 2049
            user_data=user_data,
        )

        # --------------------------------------------------------------
        # 6. The Fargate side: a task that mounts the SAME EFS + access point
        #    at /mnt/shared, reads the EC2 file, and writes one back.
        # --------------------------------------------------------------
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        task_def = ecs.FargateTaskDefinition(
            self, "TaskDef", cpu=256, memory_limit_mib=512,
        )
        # The task role gets EFS client access too.
        file_system.grant(
            task_def.task_role,
            "elasticfilesystem:ClientMount",
            "elasticfilesystem:ClientWrite",
        )

        task_def.add_volume(
            name="shared",
            efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=file_system.file_system_id,
                transit_encryption="ENABLED",                # TLS
                authorization_config=ecs.AuthorizationConfig(
                    access_point_id=ap.access_point_id,
                    iam="ENABLED",
                ),
            ),
        )

        container = task_def.add_container(
            "app",
            image=ecs.ContainerImage.from_registry("public.ecr.aws/amazonlinux/amazonlinux:2023"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="efs-demo",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            # Read what EC2 wrote, then write our own file, then loop so the
            # task stays up while you inspect the mount.
            command=[
                "bash", "-c",
                "echo '--- contents written by EC2 ---'; "
                "cat /mnt/shared/from-ec2.txt || echo '(EC2 file not present yet)'; "
                "echo \"hello from Fargate $(hostname) at $(date -u +%FT%TZ)\" "
                "> /mnt/shared/from-fargate.txt; "
                "echo '--- wrote /mnt/shared/from-fargate.txt ---'; "
                "ls -la /mnt/shared; sleep 3600",
            ],
        )
        container.add_mount_points(
            ecs.MountPoint(
                source_volume="shared",
                container_path="/mnt/shared",
                read_only=False,
            )
        )

        service = ecs.FargateService(
            self, "Service",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            security_groups=[efs_sg],        # task ENIs can reach the mounts
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # --------------------------------------------------------------
        # 7. Outputs.
        # --------------------------------------------------------------
        CfnOutput(self, "FileSystemId", value=file_system.file_system_id)
        CfnOutput(self, "AccessPointId", value=ap.access_point_id)
        CfnOutput(self, "InstanceId", value=instance.instance_id)
        CfnOutput(self, "ClusterName", value=cluster.cluster_name)
        CfnOutput(self, "ServiceName", value=service.service_name)


# ----------------------------------------------------------------------------
# App entrypoint (this is the app.py body).
# ----------------------------------------------------------------------------
app = App()
stack = C19Week6EfsStack(
    app, "C19Week6EfsStack",
    # from_lookup needs a concrete account/region at synth time.
    env={"account": app.node.try_get_context("account"), "region": "us-east-1"},
)
Tags.of(stack).add("team", "platform")
Tags.of(stack).add("service", "shared-efs")
Tags.of(stack).add("environment", "dev")
app.synth()


# ============================================================================
# VERIFICATION (run after cdk deploy; both mounts are live)
# ============================================================================
#
#   IID=$(aws cloudformation describe-stacks --stack-name C19Week6EfsStack \
#     --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
#
#   # 1. The EC2 file was written at boot. Read it via SSM (no SSH, no public IP):
#   aws ssm start-session --target "$IID"
#   #   then inside the session:
#   #     cat /mnt/shared/from-ec2.txt
#   #     cat /mnt/shared/from-fargate.txt      # written by the Fargate task!
#   #     mount | grep /mnt/shared              # shows efs + tls
#
#   # 2. Read what the Fargate task saw (it cat'd from-ec2.txt at startup):
#   aws logs tail /ecs/efs-demo --since 15m --follow
#   #   You should see "--- contents written by EC2 ---" followed by the EC2
#   #   message, then "--- wrote /mnt/shared/from-fargate.txt ---".
#
#   # 3. Confirm both mounts use the SAME file system id:
#   aws efs describe-mount-targets --file-system-id <FileSystemId>
#
# THE PROOF: from-ec2.txt is visible to Fargate, and from-fargate.txt is visible
# to EC2 — one EFS, two compute platforms, concurrent shared read/write.
# ============================================================================
