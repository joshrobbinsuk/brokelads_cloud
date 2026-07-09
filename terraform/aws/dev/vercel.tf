provider "vercel" {
  api_token = var.vercel_api_token
  team      = var.vercel_team_id
}

# These four values are public-by-design: they ship to the browser as
# NEXT_PUBLIC_* and the Cognito client has generate_secret = false.
resource "vercel_project_environment_variable" "api_url" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_API_URL"
  value      = "https://${module.apprunner.service_url}"
  target     = ["production"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "user_pool_id" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_AMPLIFY_USER_POOL_ID"
  value      = module.cognito.user_pool_id
  target     = ["production"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "user_pool_client_id" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_AMPLIFY_USER_POOL_CLIENT_ID"
  value      = module.cognito.cognito_client_id
  target     = ["production"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "region" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_AMPLIFY_REGION"
  value      = var.region
  target     = ["production"]
  sensitive  = false
}
