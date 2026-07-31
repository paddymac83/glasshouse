# Outputs. Grows with each slice, same as variables.tf.

output "s3_bucket_name" {
  description = "S3 bucket holding glasshouse.db"
  value       = aws_s3_bucket.data.bucket
}

output "ecr_web_repository_url" {
  description = "Push the web (frontend) Lambda's image here"
  value       = aws_ecr_repository.web.repository_url
}

output "ecr_ingestion_repository_url" {
  description = "Push the ingestion Lambda's image here"
  value       = aws_ecr_repository.ingestion.repository_url
}

output "web_lambda_role_arn" {
  description = "IAM role the web Lambda runs as (referenced when the Lambda function itself is added)"
  value       = aws_iam_role.web_lambda.arn
}

output "ingestion_lambda_role_arn" {
  description = "IAM role the ingestion Lambda runs as"
  value       = aws_iam_role.ingestion_lambda.arn
}
