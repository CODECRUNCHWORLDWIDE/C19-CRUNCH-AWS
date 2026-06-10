###############################################################################
# Exercise 3 — The OpenTofu equivalent
#
# Goal: Build the SAME stack from Exercises 1 & 2 (VPC + KMS-encrypted S3 with
#       lifecycle rules + a Lambda that reads from the bucket with least-privilege
#       IAM) in OpenTofu, then DIFF the result against the CDK-synthesized
#       CloudFormation template and NAME the structural differences.
#
# Estimated time: 90 minutes.
#
# HOW TO USE THIS FILE
#
#   1. Make a folder and drop this file in as main.tf:
#        mkdir crunch-iac-tofu && cd crunch-iac-tofu
#        cp <this file> main.tf
#
#   2. Copy the lambda/read_object.py handler from Exercise 1 into ./lambda/.
#
#   3. FREE path — run against LocalStack with the tflocal wrapper:
#        pip install terraform-local
#        docker run --rm -d --name localstack -p 4566:4566 \
#          -v /var/run/docker.sock:/var/run/docker.sock localstack/localstack
#        tflocal init
#        tflocal plan
#        tflocal apply -auto-approve
#
#      REAL path — point at your dev account instead:
#        export AWS_PROFILE=crunch-dev
#        tofu init
#        tofu plan
#        tofu apply
#        # ...look at it...
#        tofu destroy
#
# ACCEPTANCE CRITERIA
#   [ ] `tofu plan` (or tflocal plan) reports a plan with NO errors and the
#       resource count you expect (~12-16 resources; OpenTofu's count differs
#       from CloudFormation's — see the diff notes at the bottom).
#   [ ] The aws_iam_role_policy for the Lambda contains s3:GetObject scoped to the
#       bucket AND kms:Decrypt scoped to the key — which here you WROTE BY HAND,
#       unlike CDK's grantRead. Feel the difference.
#   [ ] You wrote down at least four structural differences between this OpenTofu
#       config and the CDK-synthesized CloudFormation template (see prompts below).
###############################################################################

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  # For real AWS, set AWS_PROFILE=crunch-dev in the environment.
  # tflocal injects the LocalStack endpoint + dummy creds for you.
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

###############################################################################
# VPC — two AZs, public + isolated subnets, NO NAT Gateway.
# NOTE: unlike the CDK Vpc L2 (one construct → ~20 CFN resources), in OpenTofu
# you assemble each piece by hand. This is the L2-vs-flat-resource difference.
###############################################################################

resource "aws_vpc" "main" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "crunch-iac-tofu" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "crunch-iac-tofu" }
}

# Two AZs. We hard-list two subnet pairs to keep the example explicit.
locals {
  azs = ["us-east-1a", "us-east-1b"]
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)       # 10.42.0/24, 10.42.1/24
  availability_zone = local.azs[count.index]
  tags              = { Name = "crunch-iac-tofu-public-${count.index}" }
}

resource "aws_subnet" "isolated" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 10)  # 10.42.10/24, 10.42.11/24
  availability_zone = local.azs[count.index]
  tags              = { Name = "crunch-iac-tofu-isolated-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "crunch-iac-tofu-public" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

###############################################################################
# KMS customer-managed key with rotation.
###############################################################################

resource "aws_kms_key" "data" {
  description             = "CMK for the Crunch IaC starter data bucket"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "data" {
  name          = "alias/crunch-iac-tofu-data"
  target_key_id = aws_kms_key.data.key_id
}

###############################################################################
# S3 bucket — KMS-encrypted, versioned, locked down, lifecycle rules.
# NOTE: the CDK Bucket L2 expresses all of this as ONE construct. The AWS
# provider splits it into FIVE separate resources. This is structural diff #1.
###############################################################################

resource "aws_s3_bucket" "data" {
  bucket_prefix = "crunch-iac-tofu-data-"
  force_destroy = true # dev only; lets `tofu destroy` empty the bucket
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    id     = "tier-and-expire"
    status = "Enabled"
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    expiration {
      days = 365
    }
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# enforce_ssl equivalent: a bucket policy denying non-TLS access.
# CDK's `enforceSSL: true` generated this for you. Here you write it by hand.
resource "aws_s3_bucket_policy" "data" {
  bucket = aws_s3_bucket.data.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.data.arn,
        "${aws_s3_bucket.data.arn}/*",
      ]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

###############################################################################
# Lambda + its least-privilege IAM — written BY HAND.
# CDK's `bucket.grantRead(reader)` produced the equivalent of everything below
# in one line. This block is the cost of not having grant*.
###############################################################################

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "reader" {
  name               = "crunch-iac-tofu-reader"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# VPC access for the Lambda (ENIs in the isolated subnets).
resource "aws_iam_role_policy_attachment" "vpc" {
  role       = aws_iam_role.reader.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# The hand-written least-privilege read policy — the grantRead equivalent.
data "aws_iam_policy_document" "reader_read" {
  statement {
    sid     = "ReadBucket"
    actions = ["s3:GetObject", "s3:GetObjectVersion", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.data.arn,
      "${aws_s3_bucket.data.arn}/*",
    ]
  }
  statement {
    sid       = "DecryptWithCmk"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [aws_kms_key.data.arn]
  }
}

resource "aws_iam_role_policy" "reader_read" {
  name   = "read-bucket"
  role   = aws_iam_role.reader.id
  policy = data.aws_iam_policy_document.reader_read.json
}

# Zip the handler at plan time so the Lambda has code.
data "archive_file" "reader" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/.build/reader.zip"
}

resource "aws_lambda_function" "reader" {
  function_name    = "crunch-iac-tofu-reader"
  role             = aws_iam_role.reader.arn
  runtime          = "python3.12"
  handler          = "read_object.handler"
  timeout          = 15
  filename         = data.archive_file.reader.output_path
  source_code_hash = data.archive_file.reader.output_base64sha256

  environment {
    variables = { BUCKET_NAME = aws_s3_bucket.data.bucket }
  }

  vpc_config {
    subnet_ids         = aws_subnet.isolated[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }
}

resource "aws_security_group" "lambda" {
  name_prefix = "crunch-iac-tofu-lambda-"
  vpc_id      = aws_vpc.main.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

###############################################################################
# Outputs — the OpenTofu equivalent of CfnOutput.
###############################################################################

output "bucket_name" {
  value = aws_s3_bucket.data.bucket
}

output "key_arn" {
  value = aws_kms_key.data.arn
}

output "function_name" {
  value = aws_lambda_function.reader.function_name
}

###############################################################################
# DIFF PROMPTS — write these answers in your engineering journal.
#
# After `tofu plan`, compare this config to the CDK-synthesized template
# (cdk.out/CrunchIacTsStack.template.json). Name at least four structural
# differences. The expected answers:
#
#  1. SUBSTRATE. CDK rides CloudFormation: the state lives server-side in the
#     CloudFormation service, and `cdk deploy` makes a change set. OpenTofu rides
#     a STATE FILE (terraform.tfstate) that lives on your disk (or an S3 backend),
#     and `tofu plan` diffs code vs state vs reality on YOUR machine.
#
#  2. BUCKET DECOMPOSITION. The CDK Bucket L2 emits ONE AWS::S3::Bucket plus an
#     inline BucketEncryption/Versioning/Lifecycle/PublicAccessBlock. The AWS
#     provider models each of those as a SEPARATE resource (aws_s3_bucket +
#     aws_s3_bucket_versioning + ..._encryption_configuration + ..._lifecycle_
#     configuration + ..._public_access_block + ..._policy). Same outcome, more
#     resources in the OpenTofu graph.
#
#  3. IAM. CDK's grantRead wrote the read policy AND the kms:Decrypt for you. Here
#     you wrote both by hand (aws_iam_role_policy + the kms statement). The
#     least-privilege scoping is identical; the EFFORT is not.
#
#  4. VPC EXPANSION. The CDK Vpc L2 is one construct that expands into subnets,
#     route tables, an IGW, and route-table associations at synth. In OpenTofu you
#     declared each of those resources explicitly. CDK hid the boilerplate; OpenTofu
#     made it visible. (Terraform's terraform-aws-modules/vpc module restores the
#     one-call ergonomics — at the cost of pulling in a third-party module.)
#
#  5. DRIFT. CloudFormation trusts its recorded state until you run
#     `detect-stack-drift`. OpenTofu's `tofu plan` inherently refreshes from
#     reality and shows you out-of-band changes every time. Different default
#     posture toward drift.
###############################################################################
