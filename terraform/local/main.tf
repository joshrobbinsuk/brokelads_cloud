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

module "cognito" {
  source = "../modules/cognito"

  project        = var.project
  region         = var.region
  admin_password = var.admin_password
}
