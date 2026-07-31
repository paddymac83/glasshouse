# Input variables. This file grows with each slice -- only S3/ECR/IAM
# related variables exist so far (see infra/README.md's status table
# for what's landed). Compute (Lambda), edge (CloudFront/WAF), and cost
# controls (Budgets) each bring their own variables when they land.

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-west-2" # London -- this project's whole subject is the GB market
}

variable "project_name" {
  description = "Prefix used when naming every resource. Keeps this deployment's resources easy to find and filter in the AWS console, and easy to tear down cleanly if you ever want to delete all of it."
  type        = string
  default     = "glasshouse"
}

variable "environment" {
  description = "Deployment environment name, used in resource naming/tagging. Only one environment is expected for a personal project, but naming things as if there might be more than one costs nothing now and avoids a rename later."
  type        = string
  default     = "prod"
}

variable "s3_db_key" {
  description = "The S3 object key glasshouse.db is stored under. Both Lambdas' IAM policies are scoped to exactly this key, not the whole bucket -- see iam.tf."
  type        = string
  default     = "glasshouse.db"
}
