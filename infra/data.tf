# Shared data sources, referenced from more than one .tf file.

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
