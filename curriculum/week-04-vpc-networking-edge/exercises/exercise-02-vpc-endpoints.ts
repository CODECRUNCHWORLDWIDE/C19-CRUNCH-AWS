/**
 * Exercise 2 — Add VPC endpoints
 *
 * Goal: extend the three-AZ VPC from Exercise 1 with the endpoints a private,
 * containerized, SSM-managed workload needs, so its AWS-service traffic never
 * touches the NAT Gateway.
 *
 *   - Gateway endpoints (FREE): S3, DynamoDB.
 *   - Interface endpoints (~$0.01/hr/AZ): STS, KMS, SSM, ssmmessages, ec2messages,
 *     ECR API, ECR DKR, CloudWatch Logs.
 *
 * Remember from Lecture 1: ECR stores image LAYERS in S3, so the S3 gateway
 * endpoint is REQUIRED for `docker pull` to work without NAT, even though the
 * ECR API/DKR interface endpoints are also present. Miss the S3 endpoint and
 * your pull silently goes out the NAT door.
 *
 * This is a runnable CDK stack. Drop it in `lib/endpoints-stack.ts`, wire it in
 * `bin/crunch-week04.ts`, then:
 *
 *   npx cdk deploy CrunchNetworkStack CrunchEndpointsStack --require-approval never
 *
 * Verify with the commands in the block comment at the bottom of this file.
 */

import { Stack, StackProps, CfnOutput, Tags } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';

export interface EndpointsStackProps extends StackProps {
  /** The VPC produced by NetworkStack (Exercise 1). */
  readonly vpc: ec2.Vpc;
}

export class EndpointsStack extends Stack {
  constructor(scope: Construct, id: string, props: EndpointsStackProps) {
    super(scope, id, props);

    const { vpc } = props;

    // ---------------------------------------------------------------------
    // Gateway endpoints — free, route-table based. S3 and DynamoDB only.
    // We attach them to the isolated subnets (where the no-egress workloads
    // live) so that tier can reach S3/DynamoDB with no internet route at all.
    // ---------------------------------------------------------------------
    const s3Endpoint = vpc.addGatewayEndpoint('S3GatewayEndpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3,
      subnets: [{ subnetType: ec2.SubnetType.PRIVATE_ISOLATED }],
    });

    // Endpoint policy: only allow access to THIS account's buckets through the
    // endpoint. Defense in depth — a compromised host can't exfiltrate to an
    // arbitrary public bucket via the endpoint.
    s3Endpoint.addToPolicy(
      new iam.PolicyStatement({
        principals: [new iam.AnyPrincipal()],
        actions: ['s3:GetObject', 's3:PutObject', 's3:ListBucket'],
        resources: ['*'],
        conditions: {
          StringEquals: { 'aws:ResourceAccount': this.account },
        },
      }),
    );

    vpc.addGatewayEndpoint('DynamoDbGatewayEndpoint', {
      service: ec2.GatewayVpcEndpointAwsService.DYNAMODB,
      subnets: [{ subnetType: ec2.SubnetType.PRIVATE_ISOLATED }],
    });

    // ---------------------------------------------------------------------
    // A dedicated security group for the interface endpoints. Interface
    // endpoints are ENIs; they need a security group that lets the VPC reach
    // them on 443. We allow inbound HTTPS from the whole VPC CIDR.
    // ---------------------------------------------------------------------
    const endpointSg = new ec2.SecurityGroup(this, 'EndpointSg', {
      vpc,
      description: 'Allow HTTPS from within the VPC to interface endpoints',
      allowAllOutbound: true,
    });
    endpointSg.addIngressRule(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(443),
      'HTTPS from within the VPC',
    );

    // ---------------------------------------------------------------------
    // Interface endpoints — PrivateLink ENIs. Each one ~$0.01/hr/AZ + data.
    // privateDnsEnabled overrides the public service hostname to resolve to
    // these ENIs, so application code needs zero changes.
    // ---------------------------------------------------------------------
    const interfaceServices: Record<string, ec2.InterfaceVpcEndpointAwsService> = {
      Sts: ec2.InterfaceVpcEndpointAwsService.STS,
      Kms: ec2.InterfaceVpcEndpointAwsService.KMS,
      Ssm: ec2.InterfaceVpcEndpointAwsService.SSM,
      SsmMessages: ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
      Ec2Messages: ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
      EcrApi: ec2.InterfaceVpcEndpointAwsService.ECR,
      EcrDocker: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
      Logs: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
    };

    for (const [name, service] of Object.entries(interfaceServices)) {
      const endpoint = vpc.addInterfaceEndpoint(`${name}Endpoint`, {
        service,
        subnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
        privateDnsEnabled: true,
        securityGroups: [endpointSg],
      });
      Tags.of(endpoint).add('Project', 'crunch-week04');
    }

    new CfnOutput(this, 'EndpointSecurityGroupId', { value: endpointSg.securityGroupId });
    new CfnOutput(this, 'InterfaceEndpointCount', {
      value: String(Object.keys(interfaceServices).length),
    });
  }
}

/*
 * Wire it in bin/crunch-week04.ts:
 *
 *   import { NetworkStack } from '../lib/network-stack';
 *   import { EndpointsStack } from '../lib/endpoints-stack';
 *
 *   const network = new NetworkStack(app, 'CrunchNetworkStack', { env });
 *   new EndpointsStack(app, 'CrunchEndpointsStack', { env, vpc: network.vpc });
 *
 * Deploy both:
 *
 *   npx cdk deploy CrunchNetworkStack CrunchEndpointsStack --require-approval never
 *
 * ---------------------------------------------------------------------------
 * VERIFY (AWS CLI) — don't trust the console.
 * ---------------------------------------------------------------------------
 *
 * 1) List every endpoint in the VPC and its type:
 *
 *   VPC_ID=$(aws cloudformation describe-stacks --stack-name CrunchNetworkStack \
 *     --query "Stacks[0].Outputs[?OutputKey=='VpcId'].OutputValue" --output text)
 *
 *   aws ec2 describe-vpc-endpoints \
 *     --filters "Name=vpc-id,Values=$VPC_ID" \
 *     --query "VpcEndpoints[].{Svc:ServiceName,Type:VpcEndpointType,State:State,PrivateDns:PrivateDnsEnabled}" \
 *     --output table
 *
 *   Expect 2 'Gateway' rows (S3, DynamoDB) and 8 'Interface' rows, all 'available'.
 *   The 8 interface rows should show PrivateDns: True.
 *
 * 2) Confirm the S3 gateway endpoint injected its prefix-list route into the
 *    isolated route tables:
 *
 *   aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC_ID" \
 *     --query "RouteTables[].Routes[?GatewayId!=null && starts_with(GatewayId,'vpce-')]" \
 *     --output json
 *
 *   You should see routes whose DestinationPrefixListId is the S3 prefix list
 *   (pl-xxxxxxxx) targeting a vpce-... endpoint. THAT route is what steals S3
 *   traffic away from NAT.
 *
 * 3) Confirm the interface endpoint ENIs exist in the isolated subnets:
 *
 *   aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" \
 *     "Name=vpc-endpoint-type,Values=Interface" \
 *     --query "VpcEndpoints[].NetworkInterfaceIds" --output json
 *
 * Expected outcome: 10 endpoints total (2 gateway + 8 interface), all available,
 * interface endpoints with private DNS on. You are now ready for Exercise 3,
 * where a private host proves it uses these instead of the NAT.
 *
 * Teardown (if not continuing to Exercise 3):
 *
 *   npx cdk destroy CrunchEndpointsStack CrunchNetworkStack
 */
