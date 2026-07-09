terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 7.0"
    }
    neon = {
      source  = "kislerdm/neon"
      version = ">= 0.13, < 1.0"
    }
    vercel = {
      source  = "vercel/vercel"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.region
}

provider "neon" {
  api_key = var.neon_api_key
}

provider "vercel" {
  api_token = var.vercel_api_token
  team      = var.vercel_team_id
}

# The standalone Cognito stack (terraform/cognito) is applied first in the
# migration sequence; this stack composes off its outputs instead of taking
# Cognito ids as CI-fed input vars.
data "terraform_remote_state" "cognito" {
  backend = "s3"

  config = {
    bucket = "initial-terraform-state-eu-west-2"
    key    = "bl/cognito/terraform.tfstate"
    region = "eu-west-2"
  }
}

module "app" {
  source = "../modules/app"

  env            = "dev"
  gcp_project_id = var.gcp_project_id
  region         = var.region
  image          = var.image
  neon_region_id = var.neon_region_id

  user_pool_id                = data.terraform_remote_state.cognito.outputs.user_pool_id
  cognito_client_id           = data.terraform_remote_state.cognito.outputs.cognito_client_id
  admin_cognito_client_id     = data.terraform_remote_state.cognito.outputs.admin_client_id
  admin_cognito_client_secret = data.terraform_remote_state.cognito.outputs.admin_client_secret
  openai_model                = var.openai_model

  rapid_api_key         = var.rapid_api_key
  openai_api_key        = var.openai_api_key
  admin_session_secret  = var.admin_session_secret
  aws_access_key_id     = var.aws_access_key_id
  aws_secret_access_key = var.aws_secret_access_key

  vercel_api_token  = var.vercel_api_token
  vercel_project_id = var.vercel_project_id
  vercel_team_id    = var.vercel_team_id
}
