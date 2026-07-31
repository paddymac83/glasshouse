# Least-privilege IAM. Each Lambda's role can do exactly what that
# Lambda needs and nothing else: the web Lambda can only *read*
# glasshouse.db, the ingestion Lambda can read *and* write it, and
# both are scoped to the one specific S3 object key -- not "any object
# in this bucket" -- since that's all either of them ever touches.
#
# Both roles are also the target Budget Actions (a later slice) will
# attach a deny-all policy to if AWS Budgets detects a spend threshold
# breach -- see infra/README.md's "cost circuit-breakers" section.

# ---------------------------------------------------------------------
# Web Lambda: read-only.
# ---------------------------------------------------------------------

data "aws_iam_policy_document" "web_lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "web_lambda" {
  name               = "${var.project_name}-web-lambda"
  assume_role_policy = data.aws_iam_policy_document.web_lambda_assume_role.json
}

# AWS-managed policy covering exactly what every Lambda needs to run
# and log to CloudWatch (CreateLogGroup/CreateLogStream/PutLogEvents,
# scoped by AWS to this function's own log group) -- no reason to
# hand-write an equivalent.
resource "aws_iam_role_policy_attachment" "web_lambda_basic_execution" {
  role       = aws_iam_role.web_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "web_lambda_s3_read" {
  statement {
    sid       = "ReadGlasshouseDb"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/${var.s3_db_key}"]
  }

  statement {
    sid       = "ListBucketForTheOneKeyOnly"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringEquals"
      variable = "s3:prefix"
      values   = [var.s3_db_key]
    }
  }
}

resource "aws_iam_role_policy" "web_lambda_s3_read" {
  name   = "${var.project_name}-web-lambda-s3-read"
  role   = aws_iam_role.web_lambda.id
  policy = data.aws_iam_policy_document.web_lambda_s3_read.json
}

# ---------------------------------------------------------------------
# Ingestion Lambda: read + write. No VPC config on this role's Lambda
# at all (see infra/README.md) -- it reaches Elexon/Octopus over the
# public internet the same way any non-VPC Lambda does by default, no
# extra IAM permission needed for that.
# ---------------------------------------------------------------------

data "aws_iam_policy_document" "ingestion_lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingestion_lambda" {
  name               = "${var.project_name}-ingestion-lambda"
  assume_role_policy = data.aws_iam_policy_document.ingestion_lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ingestion_lambda_basic_execution" {
  role       = aws_iam_role.ingestion_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "ingestion_lambda_s3_readwrite" {
  statement {
    sid       = "ReadWriteGlasshouseDb"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/${var.s3_db_key}"]
  }

  statement {
    sid       = "ListBucketForTheOneKeyOnly"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
    condition {
      test     = "StringEquals"
      variable = "s3:prefix"
      values   = [var.s3_db_key]
    }
  }
}

resource "aws_iam_role_policy" "ingestion_lambda_s3_readwrite" {
  name   = "${var.project_name}-ingestion-lambda-s3-readwrite"
  role   = aws_iam_role.ingestion_lambda.id
  policy = data.aws_iam_policy_document.ingestion_lambda_s3_readwrite.json
}
