# The single source of truth for glasshouse.db, downloaded/uploaded by
# both Lambdas at runtime rather than living on a VPC-attached EFS
# mount -- see infra/README.md's "Why S3, not EFS" section for the
# reasoning (avoiding a VPC avoids the NAT Gateway that comes with it,
# a flat ~$32-35/month regardless of usage).

resource "aws_s3_bucket" "data" {
  # Bucket names are globally unique across ALL of AWS, not just this
  # account -- suffixing with the account ID avoids ever colliding with
  # someone else's "glasshouse-data" bucket.
  bucket = "${var.project_name}-data-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Versioning with no lifecycle rule means old versions accumulate
# forever -- harmless in principle but pointless cost on a file that
# gets fully overwritten roughly daily. Keep 14 days of prior versions
# (enough to recover from one bad ingestion run) and let the rest expire.
resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 14
    }
  }
}
