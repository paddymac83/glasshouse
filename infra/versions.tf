# Terraform + provider version pins. Not yet run through `terraform
# init` in the environment this was written in -- see infra/README.md.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Local backend (the default -- no `backend` block needed to get it)
  # is fine for a single personal deployment with one operator: state
  # just lives in terraform.tfstate next to these files. If you ever
  # want remote state (working from more than one machine, or just
  # wanting a backup that isn't "don't lose this file"), the simplest
  # path is: `terraform apply` once with the local backend to create
  # the S3 bucket this project already defines (s3.tf), then add an S3
  # backend block pointing at it and run `terraform init -migrate-state`.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
      Repo      = "glasshouse"
    }
  }
}
