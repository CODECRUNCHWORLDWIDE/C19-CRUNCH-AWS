#!/usr/bin/env python3
"""
Exercise 2 — The same FastAPI app on EKS, with Karpenter Spot nodes + IRSA-scoped S3.

Goal:  Deploy the IDENTICAL fastapi-spectrum app (from exercise 1) onto EKS, where a
       small On-Demand managed node group hosts the system controllers, Karpenter
       provisions Spot Graviton worker nodes for the app, and an IRSA role scopes the
       pod to read EXACTLY one S3 prefix (public/*). You then prove the negative: the
       pod can read public/hello.txt and CANNOT read private/secret.txt.

Estimated time: 2.5 hours.

------------------------------------------------------------------------------------
HOW TO USE THIS FILE
------------------------------------------------------------------------------------
This is a runnable AWS CDK app in Python. It deploys the EKS cluster + add-ons. The
Karpenter NodePool/EC2NodeClass and the app manifests are applied as Kubernetes
manifests through the cluster construct, so a single `cdk deploy` stands up the whole
thing.

  1. Create and activate a venv, install CDK libs:

       python3 -m venv .venv && source .venv/bin/activate
       pip install "aws-cdk-lib>=2.160.0" constructs "aws-cdk.lambda-layer-kubectl-v31"

  2. Put this file at infra-eks/app.py with a cdk.json next to it:

       { "app": "python3 app.py" }

  3. Deploy (this takes ~15-20 minutes — EKS control planes are not fast):

       cdk bootstrap
       cdk deploy

  4. Wire kubectl, seed the bucket, and verify (commands at the bottom of this file).

  5. TEAR IT DOWN when you stop for the day — the control plane bills idle ($0.10/hr):

       cdk destroy

------------------------------------------------------------------------------------
ACCEPTANCE CRITERIA
------------------------------------------------------------------------------------
  [ ] EKS cluster up; a small On-Demand managed node group hosts system pods.
  [ ] Karpenter installed; applying the app causes Karpenter to launch a SPOT
      Graviton node within ~60s (watch `kubectl get nodes -w`).
  [ ] The app pod uses an IRSA-annotated ServiceAccount.
  [ ] `curl .../read?key=public/hello.txt`  -> 200 with the line.
  [ ] `curl .../read?key=private/secret.txt` -> 403 AccessDenied  (prove the scope).
  [ ] Everything tagged team/service/environment.
  [ ] Cluster destroyed at end of session.

Inline hints are at the bottom. Don't peek for 15 minutes.
"""

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_eks as eks,
    aws_iam as iam,
    aws_s3 as s3,
    lambda_layer_kubectl_v31 as kubectl,
)
from constructs import Construct

CLUSTER_NAME = "c19-week05"
TAGS = {"team": "crunch-aws", "service": "fastapi-spectrum", "environment": "dev"}


class EksKarpenterIrsaStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- VPC from Week 4 ------------------------------------------------
        vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_name="c19-week04-vpc")

        # --- S3 bucket the /read endpoint reads ----------------------------
        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            bucket_name=f"c19-week05-data-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- EKS cluster ----------------------------------------------------
        # A small On-Demand managed node group hosts the system controllers.
        # Karpenter (installed below) provisions the Spot worker capacity.
        cluster = eks.Cluster(
            self,
            "Cluster",
            cluster_name=CLUSTER_NAME,
            version=eks.KubernetesVersion.V1_31,
            kubectl_layer=kubectl.KubectlV31Layer(self, "KubectlLayer"),
            vpc=vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
            default_capacity=0,  # no default group; we add our own explicitly
            endpoint_access=eks.EndpointAccess.PUBLIC_AND_PRIVATE,
        )

        cluster.add_nodegroup_capacity(
            "SystemNodes",
            instance_types=[ec2.InstanceType("m7g.large")],  # Graviton, On-Demand
            ami_type=eks.NodegroupAmiType.BOTTLEROCKET_ARM_64,
            min_size=2,
            max_size=2,
            desired_size=2,
            capacity_type=eks.CapacityType.ON_DEMAND,
            labels={"role": "system"},
        )

        # Tag the private subnets so Karpenter can discover them.
        for subnet in vpc.private_subnets:
            cdk.Tags.of(subnet).add("karpenter.sh/discovery", CLUSTER_NAME)

        # --- EBS CSI driver via IRSA add-on --------------------------------
        ebs_csi_sa = cluster.add_service_account(
            "EbsCsiSa", name="ebs-csi-controller-sa", namespace="kube-system"
        )
        ebs_csi_sa.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEBSCSIDriverPolicy")
        )
        eks.CfnAddon(
            self,
            "EbsCsiAddon",
            cluster_name=cluster.cluster_name,
            addon_name="aws-ebs-csi-driver",
            service_account_role_arn=ebs_csi_sa.role.role_arn,
        )

        # --- AWS Load Balancer Controller (Helm) with its own IRSA role ----
        lbc_sa = cluster.add_service_account(
            "AwsLbControllerSa", name="aws-load-balancer-controller", namespace="kube-system"
        )
        # The published LB-Controller policy is large; attach the minimal set used here.
        lbc_sa.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=[
                    "elasticloadbalancing:*",
                    "ec2:Describe*",
                    "ec2:CreateSecurityGroup",
                    "ec2:CreateTags",
                    "ec2:AuthorizeSecurityGroupIngress",
                    "ec2:RevokeSecurityGroupIngress",
                    "acm:DescribeCertificate",
                    "acm:ListCertificates",
                    "iam:CreateServiceLinkedRole",
                    "wafv2:*",
                    "shield:*",
                ],
                resources=["*"],
            )
        )
        cluster.add_helm_chart(
            "AwsLbController",
            chart="aws-load-balancer-controller",
            repository="https://aws.github.io/eks-charts",
            namespace="kube-system",
            release="aws-load-balancer-controller",
            values={
                "clusterName": cluster.cluster_name,
                "serviceAccount": {"create": False, "name": "aws-load-balancer-controller"},
                "region": self.region,
                "vpcId": vpc.vpc_id,
            },
        )

        # --- Karpenter (Helm) with its node role + controller IRSA role ----
        # The node role is what Karpenter-launched instances assume.
        karpenter_node_role = iam.Role(
            self,
            "KarpenterNodeRole",
            role_name=f"KarpenterNodeRole-{CLUSTER_NAME}",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSWorkerNodePolicy"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKS_CNI_Policy"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )
        # Map the node role into aws-auth so Karpenter nodes can join the cluster.
        cluster.aws_auth.add_role_mapping(
            karpenter_node_role,
            username="system:node:{{EC2PrivateDNSName}}",
            groups=["system:bootstrappers", "system:nodes"],
        )

        karpenter_sa = cluster.add_service_account(
            "KarpenterSa", name="karpenter", namespace="kube-system"
        )
        karpenter_sa.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2:CreateLaunchTemplate", "ec2:CreateFleet", "ec2:RunInstances",
                    "ec2:CreateTags", "ec2:TerminateInstances", "ec2:DeleteLaunchTemplate",
                    "ec2:Describe*", "pricing:GetProducts", "ssm:GetParameter",
                    "iam:PassRole", "iam:CreateInstanceProfile", "iam:TagInstanceProfile",
                    "iam:AddRoleToInstanceProfile", "iam:DeleteInstanceProfile",
                    "iam:GetInstanceProfile", "sqs:*",
                ],
                resources=["*"],
            )
        )
        cluster.add_helm_chart(
            "Karpenter",
            chart="karpenter",
            repository="oci://public.ecr.aws/karpenter/karpenter",
            namespace="kube-system",
            release="karpenter",
            values={
                "serviceAccount": {"create": False, "name": "karpenter"},
                "settings": {
                    "clusterName": cluster.cluster_name,
                    "clusterEndpoint": cluster.cluster_endpoint,
                },
            },
        )

        # --- Karpenter NodePool + EC2NodeClass (applied as manifests) ------
        cluster.add_manifest(
            "KarpenterNodeClass",
            {
                "apiVersion": "karpenter.k8s.aws/v1",
                "kind": "EC2NodeClass",
                "metadata": {"name": "default"},
                "spec": {
                    "amiFamily": "Bottlerocket",
                    "amiSelectorTerms": [{"alias": "bottlerocket@latest"}],
                    "role": karpenter_node_role.role_name,
                    "subnetSelectorTerms": [{"tags": {"karpenter.sh/discovery": CLUSTER_NAME}}],
                    "securityGroupSelectorTerms": [
                        {"tags": {f"kubernetes.io/cluster/{CLUSTER_NAME}": "owned"}}
                    ],
                },
            },
        )
        cluster.add_manifest(
            "KarpenterNodePool",
            {
                "apiVersion": "karpenter.sh/v1",
                "kind": "NodePool",
                "metadata": {"name": "default"},
                "spec": {
                    "template": {
                        "spec": {
                            "requirements": [
                                {"key": "kubernetes.io/arch", "operator": "In", "values": ["arm64"]},
                                {"key": "karpenter.sh/capacity-type", "operator": "In",
                                 "values": ["spot", "on-demand"]},
                                {"key": "karpenter.k8s.aws/instance-category", "operator": "In",
                                 "values": ["c", "m", "r"]},
                                {"key": "karpenter.k8s.aws/instance-generation", "operator": "Gt",
                                 "values": ["6"]},
                            ],
                            "nodeClassRef": {"group": "karpenter.k8s.aws", "kind": "EC2NodeClass",
                                             "name": "default"},
                            "expireAfter": "168h",
                        }
                    },
                    "limits": {"cpu": "50"},
                    "disruption": {"consolidationPolicy": "WhenEmptyOrUnderutilized",
                                   "consolidateAfter": "1m"},
                },
            },
        )

        # --- The app: IRSA service account scoped to public/* --------------
        app_sa = cluster.add_service_account("FastapiReaderSa", name="fastapi-reader", namespace="app")
        app_sa.node.add_dependency(cluster.add_manifest("AppNamespace", {
            "apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "app"},
        }))
        app_sa.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[f"{data_bucket.bucket_arn}/public/*"],  # ONLY public/*
            )
        )

        image = "PUT_YOUR_ECR_IMAGE_URI_HERE"  # the image you pushed in exercise 1, arm64

        cluster.add_manifest(
            "FastapiDeployment",
            {
                "apiVersion": "apps/v1", "kind": "Deployment",
                "metadata": {"name": "fastapi", "namespace": "app"},
                "spec": {
                    "replicas": 2,
                    "selector": {"matchLabels": {"app": "fastapi"}},
                    "template": {
                        "metadata": {"labels": {"app": "fastapi"}},
                        "spec": {
                            "serviceAccountName": "fastapi-reader",
                            "nodeSelector": {"karpenter.sh/nodepool": "default"},
                            "containers": [{
                                "name": "fastapi", "image": image,
                                "ports": [{"containerPort": 8080}],
                                "env": [{"name": "DATA_BUCKET", "value": data_bucket.bucket_name}],
                                "resources": {"requests": {"cpu": "250m", "memory": "256Mi"}},
                                "readinessProbe": {"httpGet": {"path": "/healthz", "port": 8080}},
                            }],
                        },
                    },
                },
            },
        )
        cluster.add_manifest(
            "FastapiService",
            {
                "apiVersion": "v1", "kind": "Service",
                "metadata": {"name": "fastapi", "namespace": "app"},
                "spec": {"selector": {"app": "fastapi"}, "ports": [{"port": 80, "targetPort": 8080}]},
            },
        )
        cluster.add_manifest(
            "FastapiIngress",
            {
                "apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
                "metadata": {
                    "name": "fastapi", "namespace": "app",
                    "annotations": {
                        "alb.ingress.kubernetes.io/scheme": "internet-facing",
                        "alb.ingress.kubernetes.io/target-type": "ip",
                        "alb.ingress.kubernetes.io/healthcheck-path": "/healthz",
                    },
                },
                "spec": {
                    "ingressClassName": "alb",
                    "rules": [{"http": {"paths": [{
                        "path": "/", "pathType": "Prefix",
                        "backend": {"service": {"name": "fastapi", "port": {"number": 80}}},
                    }]}}],
                },
            },
        )

        for k, v in TAGS.items():
            cdk.Tags.of(self).add(k, v)

        cdk.CfnOutput(self, "BucketName", value=data_bucket.bucket_name)
        cdk.CfnOutput(self, "ClusterNameOut", value=cluster.cluster_name)


app = cdk.App()
EksKarpenterIrsaStack(
    app,
    "EksKarpenterIrsaStack",
    env=cdk.Environment(
        account=app.node.try_get_context("account") or None,
        region=app.node.try_get_context("region") or None,
    ),
)
app.synth()

# ------------------------------------------------------------------------------------
# AFTER `cdk deploy`: wire kubectl, seed the bucket, and verify.
# ------------------------------------------------------------------------------------
#   aws eks update-kubeconfig --name c19-week05 --region <region>
#   kubectl get nodes                       # initially the 2 system nodes
#   kubectl get pods -n app -w              # watch the app pods go Pending then Running
#   kubectl get nodes -w                    # watch Karpenter add a SPOT node (~60s)
#
#   BUCKET=$(aws cloudformation describe-stacks --stack-name EksKarpenterIrsaStack \
#     --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)
#   echo "hello from eks" | aws s3 cp - "s3://$BUCKET/public/hello.txt"
#   echo "forbidden"       | aws s3 cp - "s3://$BUCKET/private/secret.txt"
#
#   ALB=$(kubectl get ingress fastapi -n app -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
#   curl -s "http://$ALB/healthz"                      # {"status":"ok"}
#   curl -s "http://$ALB/read?key=public/hello.txt"    # {"key":...,"first_line":"hello from eks"}
#   curl -s "http://$ALB/read?key=private/secret.txt"  # {"detail":"AccessDenied"}  <-- IRSA scope proof
#
#   # Confirm the pod node is Spot:
#   kubectl get node -l karpenter.sh/capacity-type=spot
#
# TEAR DOWN when done for the day:
#   cdk destroy
#
# A nightly tear-down cron (macOS/Linux) so you never get the $73 surprise:
#   # crontab -e  -> run destroy at 23:00 every day
#   0 23 * * *  cd /path/to/infra-eks && /usr/local/bin/cdk destroy --force >> ~/eks-teardown.log 2>&1
#
# ------------------------------------------------------------------------------------
# HINTS (don't peek for 15 minutes)
# ------------------------------------------------------------------------------------
# * Pods stuck Pending forever? Karpenter isn't seeing them. Check:
#     kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter
#   Usual causes: subnets not tagged karpenter.sh/discovery, or the NodePool requirements
#   exclude every available instance type (e.g. no gen-7 Graviton Spot in your region).
# * /read returns AccessDenied for public/* too? IRSA isn't wired. Check that the pod
#   actually uses the SA: `kubectl get pod -n app <pod> -o jsonpath='{.spec.serviceAccountName}'`
#   should be fastapi-reader, and `kubectl describe sa fastapi-reader -n app` should show the
#   eks.amazonaws.com/role-arn annotation. Then check the role trust policy pins the :sub.
# * Ingress has no ADDRESS? The LB Controller pod is failing. Check its logs in kube-system;
#   usual cause is the IRSA role missing an elasticloadbalancing or ec2 permission.
# * Replace PUT_YOUR_ECR_IMAGE_URI_HERE with the arm64 image you pushed in exercise 1, e.g.
#   <account>.dkr.ecr.<region>.amazonaws.com/fastapi-spectrum:latest
