// Exercise 3 — Three AWS Budgets ($5 / $25 / $80) wired to email alerts
//
// Goal: Use AWS CDK (TypeScript) to create three cost budgets with email
//       notifications, so you get the email before you get the bill. Each
//       budget alerts when ACTUAL spend crosses its threshold AND when
//       FORECASTED spend is on track to cross it.
//
// Estimated time: 60 minutes.
//
// Cost: $0. AWS Budgets gives you the first budgets free; this stays well
//       inside the free allotment.
//
// ---------------------------------------------------------------------------
// HOW TO USE THIS FILE
// ---------------------------------------------------------------------------
//
// 1. Install Node.js 20+ and the CDK:  npm install -g aws-cdk
//    Verify:  node --version  &&  cdk --version   (expect cdk 2.x)
//
// 2. Scaffold a CDK app and drop this file in as the stack:
//
//        mkdir budgets && cd budgets
//        cdk init app --language typescript
//        npm install
//        # Replace lib/budgets-stack.ts with THIS file's BudgetsStack class,
//        # OR keep this file and import it from bin/budgets.ts (see step 4).
//
// 3. Authenticate as an admin principal in the account you want budgets in
//    (the management account is the natural home, since it sees consolidated
//    cost):
//
//        aws sso login --profile mgmt-admin
//        export AWS_PROFILE=mgmt-admin
//        aws sts get-caller-identity
//
// 4. Wire the stack into bin/budgets.ts:
//
//        import { App } from 'aws-cdk-lib';
//        import { BudgetsStack } from '../lib/budgets-stack';
//        const app = new App();
//        new BudgetsStack(app, 'Week1BudgetsStack', {
//          env: { region: 'us-east-1' }, // Budgets API lives in us-east-1
//          notifyEmail: process.env.BUDGET_EMAIL ?? 'you@example.com',
//        });
//
//    NOTE: The Budgets service is GLOBAL but its API is hosted in us-east-1.
//    Deploy this stack to us-east-1 even if the rest of your stacks live
//    elsewhere. (This is one of the "us-east-1 is special" cases from
//    Lecture 1.)
//
// 5. Bootstrap (first time only) and deploy:
//
//        export BUDGET_EMAIL="you@example.com"
//        cdk bootstrap
//        cdk synth          # inspect the CloudFormation it generates
//        cdk deploy
//
//    Email budget notifications are delivered directly -- there is NO
//    subscription-confirmation step like SNS has. That makes a typo silent:
//    a wrong address simply never receives an alert. Double-check the address.
//
// ---------------------------------------------------------------------------
// ACCEPTANCE CRITERIA
// ---------------------------------------------------------------------------
//
//   [ ] `cdk synth` produces valid CloudFormation with three AWS::Budgets::Budget.
//   [ ] `cdk deploy` succeeds; three budgets appear in the Billing console.
//   [ ] Each budget has BOTH an ACTUAL>=100% and a FORECASTED>=100% notification.
//   [ ] Each notification targets your email.
//   [ ] You can explain why this stack must deploy to us-east-1.
//
// ---------------------------------------------------------------------------

import { App, Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { CfnBudget } from 'aws-cdk-lib/aws-budgets';
import { Construct } from 'constructs';

export interface BudgetsStackProps extends StackProps {
  /** Email address that receives every budget alert. */
  readonly notifyEmail: string;
}

/**
 * Creates three monthly cost budgets at $5 / $25 / $80, each with an
 * "actual spend crossed the limit" alert and a "forecast to cross the limit"
 * alert, all delivered to a single email address.
 */
export class BudgetsStack extends Stack {
  constructor(scope: Construct, id: string, props: BudgetsStackProps) {
    super(scope, id, props);

    if (!props.notifyEmail.includes('@')) {
      throw new Error(`notifyEmail does not look like an email: ${props.notifyEmail}`);
    }

    const thresholds = [5, 25, 80];

    for (const limit of thresholds) {
      this.makeBudget(limit, props.notifyEmail);
    }

    new CfnOutput(this, 'NotifyEmail', { value: props.notifyEmail });
    new CfnOutput(this, 'BudgetCount', { value: String(thresholds.length) });
  }

  /**
   * One monthly COST budget at `limitUsd` with two notifications:
   *   - ACTUAL    spend >= 100% of the limit  (you already crossed it)
   *   - FORECASTED spend >= 100% of the limit (you are on track to cross it)
   */
  private makeBudget(limitUsd: number, email: string): CfnBudget {
    const subscriber: CfnBudget.SubscriberProperty = {
      subscriptionType: 'EMAIL',
      address: email,
    };

    const notifications: CfnBudget.NotificationWithSubscribersProperty[] = [
      {
        notification: {
          notificationType: 'ACTUAL',
          comparisonOperator: 'GREATER_THAN',
          threshold: 100, // percent of the limit
          thresholdType: 'PERCENTAGE',
        },
        subscribers: [subscriber],
      },
      {
        notification: {
          notificationType: 'FORECASTED',
          comparisonOperator: 'GREATER_THAN',
          threshold: 100,
          thresholdType: 'PERCENTAGE',
        },
        subscribers: [subscriber],
      },
    ];

    return new CfnBudget(this, `Budget${limitUsd}Usd`, {
      budget: {
        budgetName: `monthly-cost-${limitUsd}-usd`,
        budgetType: 'COST',
        timeUnit: 'MONTHLY',
        budgetLimit: {
          amount: limitUsd,
          unit: 'USD',
        },
        // Only count unblended cost; ignore credits/refunds so the alert
        // reflects real spend. Adjust if your account runs on credits.
        costTypes: {
          includeCredit: false,
          includeRefund: false,
          includeTax: true,
          includeSubscription: true,
          useBlended: false,
        },
      },
      notificationsWithSubscribers: notifications,
    });
  }
}

// ---------------------------------------------------------------------------
// Optional: a self-contained app entrypoint so this single file can be the
// whole CDK app. If you used `cdk init`, prefer wiring BudgetsStack from
// bin/budgets.ts (step 4) and delete the block below to avoid two apps.
// ---------------------------------------------------------------------------

if (require.main === module) {
  const app = new App();
  new BudgetsStack(app, 'Week1BudgetsStack', {
    // Budgets API is hosted in us-east-1; deploy here regardless of your
    // primary working Region.
    env: { region: 'us-east-1' },
    notifyEmail: process.env.BUDGET_EMAIL ?? 'you@example.com',
  });
  app.synth();
}

// ---------------------------------------------------------------------------
// EXPECTED `cdk synth` (excerpt — your logical ids/order may vary)
// ---------------------------------------------------------------------------
//
//   Resources:
//     Budget5Usd...:
//       Type: AWS::Budgets::Budget
//       Properties:
//         Budget:
//           BudgetName: monthly-cost-5-usd
//           BudgetType: COST
//           TimeUnit: MONTHLY
//           BudgetLimit: { Amount: 5, Unit: USD }
//         NotificationsWithSubscribers:
//           - Notification: { NotificationType: ACTUAL,   Threshold: 100, ... }
//             Subscribers:   [ { SubscriptionType: EMAIL, Address: you@... } ]
//           - Notification: { NotificationType: FORECASTED, Threshold: 100, ... }
//             Subscribers:   [ { SubscriptionType: EMAIL, Address: you@... } ]
//     Budget25Usd...: ...
//     Budget80Usd...: ...
//
// ---------------------------------------------------------------------------
// VERIFY FROM THE CLI (after deploy)
// ---------------------------------------------------------------------------
//
//   ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
//   aws budgets describe-budgets --account-id "$ACCOUNT_ID" \
//     --query 'Budgets[].{Name:BudgetName, Limit:BudgetLimit.Amount}' \
//     --output table
//
//   Expected three rows: monthly-cost-5-usd (5), -25-usd (25), -80-usd (80).
//
// ---------------------------------------------------------------------------
// CLEAN UP
// ---------------------------------------------------------------------------
//
//   cdk destroy
//
// Budgets cost nothing, so you may also just leave them -- in fact you WANT
// these alive for the rest of the course. Recommended: keep them.
//
// ---------------------------------------------------------------------------
// HINTS (read only if stuck >15 min)
// ---------------------------------------------------------------------------
//
// - "No emails arrive": Budget alerts only fire when a threshold is actually
//   crossed (or forecast to be). On a near-$0 account, the FORECASTED alert
//   may fire once real usage appears; the ACTUAL alert fires the day spend
//   crosses the dollar amount. To test the wiring without spending, set a
//   temporary $0.01 budget and incur a cent of S3/Athena cost from the
//   Challenge -- you'll get the email within ~24h (budget evaluation is not
//   instantaneous).
//
// - "cdk deploy fails with region errors": deploy to us-east-1. The Budgets
//   service endpoint lives there. Set env.region = 'us-east-1'.
//
// - "Construct not found: aws-budgets": you're on an old CDK. `aws-cdk-lib`
//   v2 ships CfnBudget under 'aws-cdk-lib/aws-budgets'. Run `npm update
//   aws-cdk-lib`.
//
// - There is no high-level (L2) Budget construct; CfnBudget (L1) is the
//   correct, current way. That's fine -- L1 maps 1:1 to CloudFormation.
//
// ---------------------------------------------------------------------------
