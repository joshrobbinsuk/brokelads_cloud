terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "eu-west-2"
}

# The cloud user pool, extracted from the retiring terraform/dev stack into its
# own standalone stack (own state key) so it survives the App Runner + RDS
# teardown. Stood up FRESH: a new empty pool with new ids, wired into the GCP
# app stack + FE at cutover. The old dev pool (project "bl-dev") is a distinct
# resource and is destroyed with terraform/dev at teardown.
module "cognito" {
  source = "../modules/cognito"

  project        = var.project
  region         = var.region
  admin_password = var.admin_password
}
