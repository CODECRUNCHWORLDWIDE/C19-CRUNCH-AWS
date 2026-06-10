// Exercise 2 — Cross-Region Replication + a watermarking Object Lambda
//
// Goal: On top of the Exercise-1 bucket, add (1) Cross-Region Replication to a
//       second region with replica re-encryption under a destination CMK, and
//       (2) an S3 Object Lambda Access Point whose Lambda stamps a watermark on
//       JPEGs at GET time.
//
// Estimated time: ~2.5 hours.
//
// HOW TO USE THIS FILE
//
//   1. Continue in the `c19-week6-storage` CDK app from Exercise 1.
//      Bootstrap BOTH regions if you have not:
//
//        cdk bootstrap aws://<account>/us-east-1 aws://<account>/us-west-2
//
//   2. Save this file as lib/c19-week6-replication-stack.ts.
//
//   3. Save the Lambda handler below (see the WATERMARK HANDLER block at the
//      bottom of this file) to lambda/watermark/index.py, and add a
//      lambda/watermark/requirements.txt containing a single line: Pillow
//
//   4. Register both stacks in bin/c19-week6-storage.ts:
//
//        const dr = new C19Week6ReplicationStack(app, 'C19Week6ReplicationStack', {
//          env: { region: 'us-east-1' },            // source region
//          crossRegionReferences: true,
//        });
//        Tags.of(dr).add('team', 'platform');
//        Tags.of(dr).add('service', 'data-lake');
//        Tags.of(dr).add('environment', 'dev');
//
//   5. cdk diff then cdk deploy C19Week6ReplicationStack.
//
// ACCEPTANCE CRITERIA
//
//   [ ] cdk deploy succeeds; outputs include the source bucket, the replica
//       bucket (in us-west-2), and the Object Lambda Access Point ARN.
//   [ ] Uploading an object to the source bucket replicates it to the replica
//       bucket within a few minutes (verify with the CLI block at the bottom).
//   [ ] GET through the Object Lambda Access Point returns a watermarked JPEG;
//       GET against the raw bucket returns the original.
//   [ ] The replica object is encrypted under the DESTINATION region's CMK,
//       not the source key.
//
// The verification commands are at the very bottom of this file.

import {
  Stack,
  StackProps,
  Duration,
  RemovalPolicy,
  CfnOutput,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Key } from 'aws-cdk-lib/aws-kms';
import {
  Bucket,
  BucketEncryption,
  BlockPublicAccess,
  ObjectOwnership,
  CfnBucket,
  CfnAccessPoint,
} from 'aws-cdk-lib/aws-s3';
import { CfnAccessPoint as CfnObjectLambdaAccessPoint } from 'aws-cdk-lib/aws-s3objectlambda';
import {
  Role,
  ServicePrincipal,
  PolicyStatement,
  Effect,
} from 'aws-cdk-lib/aws-iam';
import { Runtime, Code, Function as LambdaFn, Architecture } from 'aws-cdk-lib/aws-lambda';

const SOURCE_REGION = 'us-east-1';
const DEST_REGION = 'us-west-2';

export class C19Week6ReplicationStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // ------------------------------------------------------------------
    // 1. Destination (replica) bucket + CMK in the DR region.
    //    A separate sub-stack scoped to us-west-2 so its resources land there.
    // ------------------------------------------------------------------
    const destStack = new Stack(this, 'ReplicaRegionStack', {
      env: { region: DEST_REGION },
      crossRegionReferences: true,
    });

    const destKey = new Key(destStack, 'ReplicaCmk', {
      description: 'CMK for the CRR replica bucket (us-west-2)',
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.RETAIN,
      alias: 'alias/c19-week6-replica',
    });

    const replicaBucket = new Bucket(destStack, 'ReplicaBucket', {
      encryption: BucketEncryption.KMS,
      encryptionKey: destKey,
      bucketKeyEnabled: true,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      objectOwnership: ObjectOwnership.BUCKET_OWNER_ENFORCED,
      enforceSSL: true,
      versioned: true, // CRR REQUIRES versioning on BOTH source and destination
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // ------------------------------------------------------------------
    // 2. Source bucket + CMK in the primary region.
    // ------------------------------------------------------------------
    const sourceKey = new Key(this, 'SourceCmk', {
      description: 'CMK for the CRR source bucket (us-east-1)',
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.RETAIN,
      alias: 'alias/c19-week6-source',
    });

    const sourceBucket = new Bucket(this, 'SourceBucket', {
      encryption: BucketEncryption.KMS,
      encryptionKey: sourceKey,
      bucketKeyEnabled: true,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      objectOwnership: ObjectOwnership.BUCKET_OWNER_ENFORCED,
      enforceSSL: true,
      versioned: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // ------------------------------------------------------------------
    // 3. The replication role S3 assumes. It reads (and decrypts) the source,
    //    writes (and encrypts) the destination.
    // ------------------------------------------------------------------
    const replRole = new Role(this, 'ReplicationRole', {
      assumedBy: new ServicePrincipal('s3.amazonaws.com'),
      description: 'S3 CRR role: source read/decrypt, dest write/encrypt',
    });
    replRole.addToPolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['s3:GetReplicationConfiguration', 's3:ListBucket'],
      resources: [sourceBucket.bucketArn],
    }));
    replRole.addToPolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        's3:GetObjectVersionForReplication',
        's3:GetObjectVersionAcl',
        's3:GetObjectVersionTagging',
      ],
      resources: [`${sourceBucket.bucketArn}/*`],
    }));
    replRole.addToPolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['kms:Decrypt'],
      resources: [sourceKey.keyArn],
    }));
    replRole.addToPolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['s3:ReplicateObject', 's3:ReplicateDelete', 's3:ReplicateTags'],
      resources: [`${replicaBucket.bucketArn}/*`],
    }));
    replRole.addToPolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['kms:Encrypt', 'kms:GenerateDataKey'],
      resources: [destKey.keyArn],
    }));

    // ------------------------------------------------------------------
    // 4. Attach the replication configuration via the L1 escape hatch.
    //    (CRR is not yet a first-class L2 prop in aws-cdk-lib 2.x.)
    // ------------------------------------------------------------------
    const cfnSource = sourceBucket.node.defaultChild as CfnBucket;
    cfnSource.replicationConfiguration = {
      role: replRole.roleArn,
      rules: [
        {
          id: 'crr-to-dr-region',
          status: 'Enabled',
          priority: 0,
          filter: {},
          deleteMarkerReplication: { status: 'Enabled' },
          sourceSelectionCriteria: {
            sseKmsEncryptedObjects: { status: 'Enabled' },
          },
          destination: {
            bucket: replicaBucket.bucketArn,
            storageClass: 'STANDARD_IA', // replica is a recovery asset — store it cheaper
            encryptionConfiguration: { replicaKmsKeyId: destKey.keyArn },
          },
        },
      ],
    };

    // ------------------------------------------------------------------
    // 5. The watermarking Object Lambda.
    //    A plain S3 Access Point sits on the bucket; the Object Lambda Access
    //    Point sits on the Access Point and invokes the Lambda on GET.
    // ------------------------------------------------------------------
    const watermarkFn = new LambdaFn(this, 'WatermarkFn', {
      runtime: Runtime.PYTHON_3_12,
      architecture: Architecture.ARM_64, // Graviton — cheaper per ms
      handler: 'index.handler',
      code: Code.fromAsset('lambda/watermark', {
        // Build Pillow into the bundle. Requires Docker available locally.
        bundling: {
          image: Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash', '-c',
            'pip install -r requirements.txt -t /asset-output && cp index.py /asset-output',
          ],
        },
      }),
      timeout: Duration.seconds(30),
      memorySize: 512,
    });
    // The Lambda must be able to call WriteGetObjectResponse.
    watermarkFn.addToRolePolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: ['s3-object-lambda:WriteGetObjectResponse'],
      resources: ['*'],
    }));
    // And read the original object via the presigned URL S3 hands it.
    sourceBucket.grantRead(watermarkFn);
    sourceKey.grantDecrypt(watermarkFn);

    const supportingAp = new CfnAccessPoint(this, 'SupportingAp', {
      bucket: sourceBucket.bucketName,
      name: 'c19-week6-supporting-ap',
    });

    const olap = new CfnObjectLambdaAccessPoint(this, 'WatermarkOlap', {
      name: 'c19-week6-watermark-olap',
      objectLambdaConfiguration: {
        supportingAccessPoint: supportingAp.attrArn,
        transformationConfigurations: [
          {
            actions: ['GetObject'],
            contentTransformation: {
              AwsLambda: {
                FunctionArn: watermarkFn.functionArn,
              },
            },
          },
        ],
      },
    });

    // ------------------------------------------------------------------
    // 6. Outputs for the verification block.
    // ------------------------------------------------------------------
    new CfnOutput(this, 'SourceBucketName', { value: sourceBucket.bucketName });
    new CfnOutput(this, 'ReplicaBucketName', { value: replicaBucket.bucketName });
    new CfnOutput(this, 'ObjectLambdaArn', { value: olap.attrArn });
    new CfnOutput(this, 'SourceRegion', { value: SOURCE_REGION });
    new CfnOutput(this, 'DestRegion', { value: DEST_REGION });
  }
}

// ============================================================================
// WATERMARK HANDLER  ->  save as lambda/watermark/index.py
// ============================================================================
//
// import io
// import urllib.request
// import boto3
// from PIL import Image, ImageDraw, ImageFont
//
// s3 = boto3.client("s3")
//
//
// def handler(event, _context):
//     ctx = event["getObjectContext"]
//     route = ctx["outputRoute"]
//     token = ctx["outputToken"]
//
//     # Fetch the original object using the presigned URL S3 provides.
//     original = urllib.request.urlopen(ctx["inputS3Url"]).read()
//
//     try:
//         img = Image.open(io.BytesIO(original)).convert("RGB")
//     except Exception:
//         # Not an image we can decode — return the original bytes untouched.
//         s3.write_get_object_response(
//             Body=original, RequestRoute=route, RequestToken=token
//         )
//         return {"statusCode": 200}
//
//     draw = ImageDraw.Draw(img)
//     text = "CRUNCH LABS - CONFIDENTIAL"
//     # Bottom-left, with a translucent-looking light stamp.
//     draw.text((12, img.height - 28), text, fill=(255, 255, 255))
//     draw.text((11, img.height - 29), text, fill=(0, 0, 0))
//
//     out = io.BytesIO()
//     img.save(out, format="JPEG", quality=85)
//
//     s3.write_get_object_response(
//         Body=out.getvalue(),
//         RequestRoute=route,
//         RequestToken=token,
//         ContentType="image/jpeg",
//     )
//     return {"statusCode": 200}
//
// ----------------------------------------------------------------------------
// lambda/watermark/requirements.txt:
//
//   Pillow
//
// ============================================================================
// VERIFICATION  (run after cdk deploy)
// ============================================================================
//
//   SRC=$(aws cloudformation describe-stacks --stack-name C19Week6ReplicationStack \
//     --query "Stacks[0].Outputs[?OutputKey=='SourceBucketName'].OutputValue" --output text)
//   DST=$(aws cloudformation describe-stacks --stack-name C19Week6ReplicationStack \
//     --query "Stacks[0].Outputs[?OutputKey=='ReplicaBucketName'].OutputValue" --output text)
//   OLAP=$(aws cloudformation describe-stacks --stack-name C19Week6ReplicationStack \
//     --query "Stacks[0].Outputs[?OutputKey=='ObjectLambdaArn'].OutputValue" --output text)
//
//   # 1. Upload a JPEG to the SOURCE bucket.
//   aws s3 cp ./sample.jpg "s3://$SRC/photos/sample.jpg"
//
//   # 2. Wait a couple of minutes, then confirm it replicated to us-west-2.
//   aws s3api head-object --bucket "$DST" --key photos/sample.jpg --region us-west-2 \
//     --query "{enc:ServerSideEncryption, key:SSEKMSKeyId}"
//   #   -> enc should be "aws:kms" and key should be the us-west-2 (replica) CMK.
//
//   # 3. GET through the Object Lambda Access Point -> watermarked.
//   aws s3api get-object --bucket "$OLAP" --key photos/sample.jpg watermarked.jpg
//   #   Open watermarked.jpg: it carries the "CRUNCH LABS - CONFIDENTIAL" stamp.
//
//   # 4. GET the raw object -> original (no watermark).
//   aws s3api get-object --bucket "$SRC" --key photos/sample.jpg original.jpg
//
//   # 5. Confirm replication status on the source object version.
//   aws s3api head-object --bucket "$SRC" --key photos/sample.jpg \
//     --query "ReplicationStatus"   # -> "COMPLETED"
//
// ============================================================================
// TEAR-DOWN
// ============================================================================
//
//   cdk destroy C19Week6ReplicationStack
//   # The two CMKs are RETAIN; schedule their deletion manually if you want
//   # them gone:
//   #   aws kms schedule-key-deletion --key-id alias/c19-week6-source  --pending-window-in-days 7
//   #   aws kms schedule-key-deletion --key-id alias/c19-week6-replica --pending-window-in-days 7 --region us-west-2
//
// ============================================================================
