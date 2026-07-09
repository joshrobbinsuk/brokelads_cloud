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
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.region
}

provider "neon" {
  api_key = var.neon_api_key
}

module "app" {
  source = "../modules/app"

  env            = "dev"
  gcp_project_id = var.gcp_project_id
  region         = var.region
  image          = var.image
  neon_region_id = var.neon_region_id

  user_pool_id            = var.user_pool_id
  cognito_client_id       = var.cognito_client_id
  admin_cognito_client_id = var.admin_cognito_client_id
  openai_model            = var.openai_model

  rapid_api_key               = var.rapid_api_key
  openai_api_key              = var.openai_api_key
  cron_auth_key               = var.cron_auth_key
  admin_session_secret        = var.admin_session_secret
  admin_cognito_client_secret = var.admin_cognito_client_secret
  aws_access_key_id           = var.aws_access_key_id
  aws_secret_access_key       = var.aws_secret_access_key
}
