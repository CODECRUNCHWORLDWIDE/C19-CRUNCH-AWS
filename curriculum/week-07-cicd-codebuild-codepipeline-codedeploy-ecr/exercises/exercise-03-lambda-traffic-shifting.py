"""
Exercise 3 — Lambda canary / linear traffic shifting in the same pipeline

Goal: Add a SIBLING Lambda function to the delivery flow, with versions, an
      alias, and a CodeDeploy LambdaDeploymentGroup that shifts alias traffic
      with a canary (then linear) config, gated by a pre-traffic smoke-test
      hook and an error-rate alarm. Same blue/green discipline as the ECS
      service in Exercise 2 -- the mechanism is alias weights, not target groups.

Estimated time: 75 minutes.

HOW TO USE THIS FILE
  1. This is a runnable AWS CDK (Python) stack. Put it in your CDK app at
     order_pipeline/lambda_canary_stack.py and add to app.py:

        from order_pipeline.lambda_canary_stack import LambdaCanaryStack
        LambdaCanaryStack(app, "OrderEventHandler",
                          env=Environment(account=os.environ["CDK_DEFAULT_ACCOUNT"],
                                          region=os.environ["CDK_DEFAULT_REGION"]))

  2. Create the handler and hook code:
        lambda/handler/index.py          (the function being deployed)
        lambda/pre_traffic/index.py      (the smoke test CodeDeploy invokes first)

  3. Deploy:  cdk deploy OrderEventHandler

ACCEPTANCE CRITERIA
  [ ] handler.current_version publishes a new immutable Version on every code change.
  [ ] A lambda.Alias named "prod" points at the current version.
  [ ] A LambdaDeploymentGroup uses CANARY_10PERCENT_5MINUTES (then try LINEAR).
  [ ] A pre-traffic hook Lambda validates the new version BEFORE any traffic shifts.
  [ ] An error-rate alarm (Errors metric) triggers automatic rollback.
  [ ] treatMissingData is NOT_BREACHING.
  [ ] You captured a deployment that rolled back because the pre-traffic hook failed.
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_codedeploy as codedeploy,
    aws_cloudwatch as cloudwatch,
    aws_logs as logs,
)
from constructs import Construct


class LambdaCanaryStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---- The function being deployed (the sibling to the ECS service) ----
        handler = _lambda.Function(
            self,
            "Handler",
            function_name="order-event-handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,  # Graviton: cheaper Lambda too
            handler="index.handler",
            code=_lambda.Code.from_asset("lambda/handler"),
            timeout=Duration.seconds(10),
            log_retention=logs.RetentionDays.TWO_WEEKS,
        )

        # current_version publishes a NEW immutable Version each time the code
        # asset hash changes. The alias points at it; CodeDeploy shifts the alias.
        alias = _lambda.Alias(
            self,
            "ProdAlias",
            alias_name="prod",
            version=handler.current_version,
        )

        # ---- Pre-traffic hook: a smoke test CodeDeploy runs BEFORE shifting ----
        # If this returns failure to CodeDeploy, the deploy aborts before ANY
        # user invocation hits the new version.
        pre_traffic = _lambda.Function(
            self,
            "PreTraffic",
            function_name="order-event-handler-pretraffic",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            handler="index.handler",
            code=_lambda.Code.from_asset("lambda/pre_traffic"),
            timeout=Duration.seconds(30),
            environment={"TARGET_FUNCTION": handler.function_name},
        )
        # The hook needs to invoke the function-under-test and report to CodeDeploy.
        handler.grant_invoke(pre_traffic)
        pre_traffic.add_to_role_policy(
            # Scoped to CodeDeploy's PutLifecycleEventHookExecutionStatus only.
            codedeploy_put_lifecycle_statement()
        )

        # ---- The rollback alarm: function Errors during the bake window ----
        errors_metric = alias.metric_errors(
            period=Duration.minutes(1),
            statistic="Sum",
        )
        error_alarm = cloudwatch.Alarm(
            self,
            "ErrorAlarm",
            alarm_name="order-event-handler-canary-errors",
            metric=errors_metric,
            threshold=2,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            # Idle function reports no data; do not false-roll-back on missing data.
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # ---- The Lambda deployment group: canary + hook + alarm ----
        # Start with CANARY; swap to LINEAR_10PERCENT_EVERY_1MINUTE to see the
        # difference (10% steps every minute vs 10% then jump to 100%).
        codedeploy.LambdaDeploymentGroup(
            self,
            "Canary",
            alias=alias,
            deployment_config=codedeploy.LambdaDeploymentConfig.CANARY_10_PERCENT_5_MINUTES,
            alarms=[error_alarm],
            pre_hook=pre_traffic,
            # auto-rollback on a failed deployment or an alarm in ALARM state.
            auto_rollback=codedeploy.AutoRollbackConfig(
                failed_deployment=True,
                deployment_in_alarm=True,
            ),
        )


def codedeploy_put_lifecycle_statement():
    """The pre-traffic hook must report its result back to CodeDeploy."""
    from aws_cdk import aws_iam as iam

    return iam.PolicyStatement(
        actions=["codedeploy:PutLifecycleEventHookExecutionStatus"],
        # Scope to deployments of THIS application in production; widen if needed.
        resources=["*"],  # CodeDeploy lifecycle-hook reporting is deployment-scoped at call time
    )


# ===========================================================================
# THE HANDLER CODE -- lambda/handler/index.py
# ===========================================================================
#
#   def handler(event, context):
#       # Real work goes here. For the drill, a feature flag forces failure.
#       import os
#       if os.environ.get("FORCE_FAIL") == "1":
#           raise RuntimeError("deliberate canary failure for the rollback drill")
#       return {"statusCode": 200, "body": "ok"}
#
# ===========================================================================
# THE PRE-TRAFFIC HOOK -- lambda/pre_traffic/index.py
# ===========================================================================
#
#   import os, json, boto3
#
#   lambda_client = boto3.client("lambda")
#   codedeploy = boto3.client("codedeploy")
#
#   def handler(event, context):
#       # CodeDeploy passes the deployment id + lifecycle event hook execution id.
#       deployment_id = event["DeploymentId"]
#       hook_execution_id = event["LifecycleEventHookExecutionId"]
#       status = "Succeeded"
#       try:
#           # Invoke the NEW version directly (qualifier resolves to the version
#           # CodeDeploy is about to shift to) and assert it responds 200.
#           resp = lambda_client.invoke(
#               FunctionName=os.environ["TARGET_FUNCTION"],
#               Payload=json.dumps({"smoke": True}).encode("utf-8"),
#           )
#           body = json.loads(resp["Payload"].read())
#           if body.get("statusCode") != 200:
#               status = "Failed"
#       except Exception:
#           status = "Failed"
#       # Report the result so CodeDeploy proceeds or aborts BEFORE shifting traffic.
#       codedeploy.put_lifecycle_event_hook_execution_status(
#           deploymentId=deployment_id,
#           lifecycleEventHookExecutionId=hook_execution_id,
#           status=status,
#       )
#       return {"status": status}
#
# ===========================================================================
# THE DRILL -- capture the evidence
# ===========================================================================
#
#   Clean deploy: change the handler, cdk deploy. Watch the alias weight move
#   90/10 -> bake 5 min -> 0/100 in the CodeDeploy console.
#
#   Force a pre-traffic failure: set FORCE_FAIL=1 on the function env, redeploy.
#   The pre-traffic hook invokes the new version, gets a 500, reports "Failed",
#   and CodeDeploy aborts BEFORE shifting ANY traffic. Capture it:
#
#     aws deploy list-deployments --application-name <generated-app-name> \
#       --query 'deployments[0]'
#     aws deploy get-deployment --deployment-id d-XXXXXXXXX \
#       --query 'deploymentInfo.{status:status,errorInformation:errorInformation}'
#
#   Then remove FORCE_FAIL but break the handler at runtime instead (raise on a
#   fraction of invocations). This time the pre-traffic passes, the 10% canary
#   shifts, the Errors alarm fires during the bake, and CodeDeploy rolls the
#   alias back to 100% old version. Capture that deployment too -- it shows the
#   alarm-triggered rollback (vs the hook-triggered abort above).
#
# REFLECTION (answer in results-ex03.md):
#   1. The pre-traffic hook aborts BEFORE any traffic; the alarm rolls back AFTER
#      10% has flowed. When does each fire, and why do you want both?
#   2. Compare CANARY_10PERCENT_5MINUTES vs LINEAR_10PERCENT_EVERY_1MINUTE for a
#      function with bursty, uneven traffic. Which exposes the new version to a
#      more representative sample faster?
#   3. Lambda traffic shifting moves an ALIAS WEIGHT. ECS blue/green swaps a
#      LISTENER between TARGET GROUPS. Both are "blue/green." Explain the shared
#      abstraction in one sentence.
#   4. The function is arm64. Lambda arm64 (Graviton) is cheaper per GB-second.
#      What is the one thing you must verify about your dependencies before
#      flipping a Lambda from x86 to arm64? (Hint: native extensions / wheels.)
