// Exercise 2 — Blue/green ECS Fargate deploy with a 10% canary and alarm rollback
//
// Goal: Add a `deploy` stage to the Exercise 1 pipeline that does a CodeDeploy
//       BLUE/GREEN deployment onto ECS Fargate. Two target groups behind one
//       ALB listener, a Canary10Percent5Minutes config, and a CloudWatch 5XX
//       alarm on the green target group that triggers AUTOMATIC ROLLBACK.
//
// Estimated time: 90 minutes.
//
// HOW TO USE THIS FILE
//
//   1. This is a runnable CDK (TypeScript) stack. Drop it into your CDK app at
//      lib/ecs-bluegreen-stack.ts and instantiate it from bin/app.ts:
//
//        import { EcsBlueGreenStack } from '../lib/ecs-bluegreen-stack';
//        new EcsBlueGreenStack(app, 'OrderServiceEcs', {
//          env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },
//        });
//
//   2. Deploy:  cdk deploy OrderServiceEcs
//   3. The CodeDeploy ECS deployment group is created with the canary config and
//      the alarm wired as a rollback trigger. The Exercise-1 pipeline's deploy
//      stage hands deployments to this group (see the CodeDeployEcsDeployAction
//      snippet at the bottom).
//
// THE ROLLBACK DRILL (mandatory):
//   After a clean deploy, ship a build whose handler returns HTTP 500 on /health.
//   Watch the canary take 10% of traffic, the 5XX alarm fire within the bake
//   window, and CodeDeploy revert to blue. Capture the CodeDeploy deployment
//   events (see the CLI at the bottom) showing the automatic rollback.
//
// ACCEPTANCE CRITERIA
//   [ ] ECS service uses the CODE_DEPLOY deployment controller (NOT the default ECS rolling).
//   [ ] Exactly two target groups (blue + green) behind one production listener.
//   [ ] CodeDeploy ECS deployment group uses CANARY_10PERCENT_5MINUTES.
//   [ ] A CloudWatch alarm on green-target-group 5XX is registered as a rollback trigger.
//   [ ] treatMissingData is NOT_BREACHING (no false rollback on an idle green fleet).
//   [ ] A deliberately-broken build auto-rolls-back; you captured the CodeDeploy events.
//   [ ] cdk synth has no unexplained Resource: "*" in the deploy role.

import { Construct } from 'constructs';
import { Stack, StackProps, Duration, RemovalPolicy } from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as codedeploy from 'aws-cdk-lib/aws-codedeploy';
import * as logs from 'aws-cdk-lib/aws-logs';

export class EcsBlueGreenStack extends Stack {
  public readonly deploymentGroup: codedeploy.EcsDeploymentGroup;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // ---- VPC + cluster (reuse your Week 4 VPC in production; minimal here) ----
    const vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 1, // production uses VPC endpoints to avoid NAT; see Week 4
    });
    const cluster = new ecs.Cluster(this, 'Cluster', { vpc, clusterName: 'crunch-prod' });

    const repo = ecr.Repository.fromRepositoryName(this, 'AppRepo', 'crunch/order-service');

    // ---- Task definition: arm64 (Graviton) for ~20% Fargate savings ----
    const taskDef = new ecs.FargateTaskDefinition(this, 'TaskDef', {
      cpu: 512,
      memoryLimitMiB: 1024,
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });
    taskDef.addContainer('order-service', {
      containerName: 'order-service',
      image: ecs.ContainerImage.fromEcrRepository(repo, 'release-latest'),
      portMappings: [{ containerPort: 8080 }],
      logging: ecs.LogDriver.awsLogs({
        streamPrefix: 'order-service',
        logRetention: logs.RetentionDays.TWO_WEEKS,
      }),
    });

    // ---- ALB with one production listener and (optionally) a test listener ----
    const alb = new elbv2.ApplicationLoadBalancer(this, 'Alb', { vpc, internetFacing: true });

    // TWO target groups: blue (live) and green (the new version during a deploy).
    const blueTg = new elbv2.ApplicationTargetGroup(this, 'BlueTg', {
      vpc,
      port: 8080,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: { path: '/health', interval: Duration.seconds(15), healthyThresholdCount: 2 },
      deregistrationDelay: Duration.seconds(30),
    });
    const greenTg = new elbv2.ApplicationTargetGroup(this, 'GreenTg', {
      vpc,
      port: 8080,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      healthCheck: { path: '/health', interval: Duration.seconds(15), healthyThresholdCount: 2 },
      deregistrationDelay: Duration.seconds(30),
    });

    // Production listener: starts pointing at blue.
    const prodListener = alb.addListener('Prod', {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
      defaultTargetGroups: [blueTg],
    });
    // Test listener: lets CodeDeploy validate green before the canary shift.
    const testListener = alb.addListener('Test', {
      port: 9000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      defaultTargetGroups: [greenTg],
    });

    // ---- ECS service with the CODE_DEPLOY deployment controller ----
    // This is the line that hands traffic-shifting to CodeDeploy instead of
    // letting ECS do a rolling in-place deploy.
    const service = new ecs.FargateService(this, 'Service', {
      cluster,
      taskDefinition: taskDef,
      serviceName: 'order-service',
      desiredCount: 2,
      deploymentController: { type: ecs.DeploymentControllerType.CODE_DEPLOY },
      circuitBreaker: { rollback: false }, // CodeDeploy owns rollback, not the ECS circuit breaker
    });
    service.attachToApplicationTargetGroup(blueTg);

    // ---- The rollback alarm: 5XX on the GREEN target group ----
    const green5xx = greenTg.metrics.httpCodeTarget(
      elbv2.HttpCodeTarget.TARGET_5XX_COUNT,
      { period: Duration.minutes(1), statistic: 'Sum' },
    );
    const rollbackAlarm = new cloudwatch.Alarm(this, 'Canary5xxAlarm', {
      alarmName: 'order-service-canary-5xx',
      metric: green5xx,
      threshold: 5,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      // Critical: an idle green fleet reports NO data; do not roll back on that.
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    // A second guard: p99 latency on green. Either alarm trips the rollback.
    const greenLatency = greenTg.metrics.targetResponseTime({
      period: Duration.minutes(1),
      statistic: 'p99',
    });
    const latencyAlarm = new cloudwatch.Alarm(this, 'CanaryLatencyAlarm', {
      alarmName: 'order-service-canary-p99',
      metric: greenLatency,
      threshold: 1.5, // seconds
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    // ---- The CodeDeploy ECS deployment group: canary + auto-rollback ----
    const application = new codedeploy.EcsApplication(this, 'CdApp', {
      applicationName: 'order-service',
    });
    this.deploymentGroup = new codedeploy.EcsDeploymentGroup(this, 'BlueGreen', {
      application,
      deploymentGroupName: 'order-service-bluegreen',
      service,
      blueGreenDeploymentConfig: {
        blueTargetGroup: blueTg,
        greenTargetGroup: greenTg,
        listener: prodListener,
        testListener: testListener,
        // Wait this long after green is fully shifted before terminating blue.
        terminationWaitTime: Duration.minutes(5),
      },
      deploymentConfig: codedeploy.EcsDeploymentConfig.CANARY_10PERCENT_5MINUTES,
      alarms: [rollbackAlarm, latencyAlarm], // any ALARM during the bake => rollback
      autoRollback: {
        failedDeployment: true, // roll back if the deployment itself fails
        deploymentInAlarm: true, // roll back if an alarm fires during the bake window
      },
    });
  }
}

// ===========================================================================
// PIPELINE WIRING — add this deploy stage to the Exercise 1 pipeline.
// ===========================================================================
//
// In the PipelineStack, after the Build stage, add (pseudocode-adjacent, real API):
//
//   import * as cpactions from 'aws-cdk-lib/aws-codepipeline-actions';
//
//   pipeline.addStage({
//     stageName: 'Approve',
//     actions: [ new cpactions.ManualApprovalAction({ actionName: 'PromoteToProd' }) ],
//   });
//
//   pipeline.addStage({
//     stageName: 'Deploy',
//     actions: [
//       new cpactions.CodeDeployEcsDeployAction({
//         actionName: 'BlueGreenDeploy',
//         deploymentGroup: ecsStack.deploymentGroup,
//         appSpecTemplateInput: buildOutput,     // appspec.yaml from Exercise 1's build
//         taskDefinitionTemplateInput: buildOutput, // taskdef.json from Exercise 1's build
//         containerImageInputs: [{
//           input: buildOutput,
//           taskDefinitionPlaceholder: 'IMAGE1_NAME', // substituted from imageDetail.json
//         }],
//       }),
//     ],
//   });
//
// ===========================================================================
// THE ROLLBACK DRILL — capture the evidence.
// ===========================================================================
//
//   1. Deploy a healthy build. Watch the deployment in the console go:
//        Step 1: green tasks healthy -> Step 2: 10% canary -> bake 5 min -> 100%.
//
//   2. Ship a broken build: make /health return 500. Push to main. When the
//      canary takes 10%, the 5XX alarm crosses threshold within ~1-2 minutes,
//      and CodeDeploy reverts. Capture it:
//
//        aws deploy list-deployments \
//          --application-name order-service \
//          --deployment-group-name order-service-bluegreen \
//          --query 'deployments[0]' --output text
//
//        aws deploy get-deployment --deployment-id d-XXXXXXXXX \
//          --query 'deploymentInfo.{status:status,rollback:rollbackInfo}'
//
//      Expected status: "Stopped" with a rollbackInfo block naming the alarm.
//      Blue served 100% the entire time; only 10% of requests for ~2 minutes
//      saw the broken green tasks.
//
// REFLECTION (answer in results-ex02.md):
//   1. Why must the bake window (5 min) exceed the alarm's reaction time (1-2 min)?
//      What goes wrong with a Canary10Percent5Minutes config and a 10-min alarm?
//   2. Why circuitBreaker.rollback = false on the service when CodeDeploy owns rollback?
//   3. The task runs arm64. What would you change to ship amd64 instead, and why
//      does the multi-arch image from Exercise 1 mean you do NOT have to rebuild?
//   4. treatMissingData is NOT_BREACHING. Walk through the false-rollback that
//      BREACHING would cause on a brand-new green target group.
