# Frontend env-var management, mirroring the AWS stack's terraform/dev/vercel.tf.
# The `vercel` provider itself is configured by the caller (dev/main.tf,
# prod/main.tf) — same pattern as the `neon` provider in neon.tf.

# These four values are public-by-design: they ship to the browser as
# NEXT_PUBLIC_* and the Cognito client has generate_secret = false.
resource "vercel_project_environment_variable" "api_url" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_API_URL"
  value      = google_cloud_run_v2_service.api.uri
  target     = ["production"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "user_pool_id" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_AMPLIFY_USER_POOL_ID"
  value      = var.user_pool_id
  target     = ["production"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "user_pool_client_id" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_AMPLIFY_USER_POOL_CLIENT_ID"
  value      = var.cognito_client_id
  target     = ["production"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "region" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_AMPLIFY_REGION"
  # Amplify talks to Cognito, which stays on AWS in eu-west-2 — this is NOT
  # var.region (europe-west2), which is where the GCP compute lives.
  value     = "eu-west-2"
  target    = ["production"]
  sensitive = false
}
