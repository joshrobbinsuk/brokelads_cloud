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

# example
module "lambda" {
  source = "../modules/lambda"

  project       = var.project
}

# create similar to dev but with production settings for all other resources