# Frontend env-var management, mirroring the AWS stack's terraform/dev/vercel.tf.
# The `vercel` provider itself is configured by the caller (dev/main.tf,
# prod/main.tf) — same pattern as the `neon` provider in neon.tf.

# These values are public-by-design: they ship to the browser as NEXT_PUBLIC_*
# (the Firebase web apiKey is a public client identifier, not a secret).
resource "vercel_project_environment_variable" "api_url" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_API_URL"
  value      = google_cloud_run_v2_service.api.uri
  target     = ["production", "preview"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "firebase_api_key" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_FIREBASE_API_KEY"
  value      = var.firebase_api_key
  target     = ["production", "preview"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "firebase_auth_domain" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN"
  value      = var.firebase_auth_domain
  target     = ["production", "preview"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "firebase_project_id" {
  project_id = var.vercel_project_id
  key        = "NEXT_PUBLIC_FIREBASE_PROJECT_ID"
  value      = var.gcp_project_id
  target     = ["production", "preview"]
  sensitive  = false
}

# Real domain for the frontend. The API stays on its run.app URL — only the
# Vercel-hosted frontend gets the custom domain. The dev subdomain is the one
# actually served; apex and www are 308 redirects onto it (no double hop).
resource "vercel_project_domain" "dev" {
  project_id = var.vercel_project_id
  domain     = "dev.brokelads.co.uk"
}

resource "vercel_project_domain" "apex" {
  project_id           = var.vercel_project_id
  domain               = "brokelads.co.uk"
  redirect             = vercel_project_domain.dev.domain
  redirect_status_code = 308
}

resource "vercel_project_domain" "www" {
  project_id           = var.vercel_project_id
  domain               = "www.brokelads.co.uk"
  redirect             = vercel_project_domain.dev.domain
  redirect_status_code = 308
}
