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

module "identity_platform" {
  source = "../../modules/identity-platform"

  gcp_project_id             = var.gcp_project_id
  google_oauth_client_id     = var.google_oauth_client_id
  google_oauth_client_secret = var.google_oauth_client_secret

  authorized_domains = [
    "localhost",
    "dev.brokelads.co.uk",
    "brokelads.co.uk",
    "www.brokelads.co.uk",
    "bl-fe.vercel.app",
    "${var.gcp_project_id}.firebaseapp.com",
  ]
}

module "app" {
  source = "../modules/app"

  env            = "dev"
  gcp_project_id = var.gcp_project_id
  region         = var.region
  image          = var.image
  neon_region_id = var.neon_region_id

  # One Google OAuth client (hand-off #1) backs both the end-user IdP and the
  # admin panel OIDC login.
  admin_google_client_id     = var.google_oauth_client_id
  admin_google_client_secret = var.google_oauth_client_secret
  firebase_api_key           = module.identity_platform.firebase_api_key
  openai_model               = var.openai_model

  cors_origins = [
    "https://dev.brokelads.co.uk",
    "https://brokelads.co.uk",
    "https://www.brokelads.co.uk",
    "https://bl-fe.vercel.app",
  ]
  alert_email = var.alert_email

  rapid_api_key        = var.rapid_api_key
  openai_api_key       = var.openai_api_key
  admin_session_secret = var.admin_session_secret

  vercel_api_token  = var.vercel_api_token
  vercel_project_id = var.vercel_project_id
  vercel_team_id    = var.vercel_team_id
}
