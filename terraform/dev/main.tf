terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    vercel = {
      source  = "vercel/vercel"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = "eu-west-2"
}

resource "random_password" "db" {
  length = 32
  # Alphanumeric only: the password is interpolated into DATABASE_URL, so any
  # URL-reserved char (#, %, etc.) would corrupt the connection string and crash
  # create_engine() at app startup. RDS doesn't require symbols.
  special = false
}

module "rds" {
  source  = "../modules/rds"
  project = var.project

  username = var.db_username
  password = random_password.db.result

  skip_final_snapshot = true # Set to false for production
}

module "apprunner" {
  source = "../modules/apprunner"

  project   = var.project
  image_tag = var.image_tag
  environment_variables = {
    DATABASE_URL                = module.rds.connection_string
    RAPID_API_KEY               = var.rapid_api_key
    OPENAI_API_KEY              = var.openai_api_key
    CRON_AUTH_KEY               = module.scheduler.cron_auth_key_value
    ADMIN_SESSION_SECRET        = var.admin_session_secret
    ADMIN_COGNITO_CLIENT_ID     = module.cognito.admin_client_id
    ADMIN_COGNITO_CLIENT_SECRET = module.cognito.admin_client_secret
    USER_POOL_ID                = module.cognito.user_pool_id
    COGNITO_CLIENT_ID           = module.cognito.cognito_client_id
  }

  depends_on = [module.rds]
}

module "scheduler" {
  source = "../modules/scheduler"

  project                    = var.project
  apprunner_service_url      = module.apprunner.service_url
  apprunner_instance_role_id = module.apprunner.instance_role_id
  apprunner_service_name     = module.apprunner.service_name
  cron_schedule_expression   = "rate(1 minute)"
  cron_endpoint_path         = "/rapid-api/run-jobs"
}

module "cognito" {
  source = "../modules/cognito"

  project        = var.project
  region         = var.region
  admin_password = var.admin_password
}

module "lambda" {
  source = "../modules/lambda"

  project = var.project
}
