variable "gcp_project_id" {
  description = "GCP project ID the app stack deploys into"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run, Artifact Registry, and Cloud Scheduler"
  type        = string
  default     = "europe-west2"
}

variable "image" {
  description = "Full Artifact Registry image ref to deploy"
  type        = string
}

variable "neon_api_key" {
  description = "Neon API key (GitHub secret NEON_API_KEY)"
  type        = string
  sensitive   = true
}

variable "neon_region_id" {
  description = "Neon region id for the project"
  type        = string
  default     = "aws-eu-west-2"
}

variable "openai_model" {
  type    = string
  default = "gpt-5-mini"
}

variable "alert_email" {
  description = "Email address for the uptime alert notification channel"
  type        = string
  # Same address already hardcoded as ADMIN_EMAIL in api/src/settings.py — no
  # new secret, repo is public.
  default = "joshrobbinsukdev@gmail.com"
}

# --- Secrets: fed by CI, never invented here ---

variable "rapid_api_key" {
  type      = string
  sensitive = true
}

variable "openai_api_key" {
  type      = string
  sensitive = true
}

variable "admin_session_secret" {
  type      = string
  sensitive = true
}

# Google OAuth Web client (hand-off #1): backs the end-user google.com IdP AND
# the admin panel OIDC login. GitHub secrets GOOGLE_OAUTH_CLIENT_ID/SECRET.
variable "google_oauth_client_id" {
  type = string
}

variable "google_oauth_client_secret" {
  type      = string
  sensitive = true
}

# --- Vercel ---

variable "vercel_api_token" {
  description = "Vercel API token used to manage frontend project environment variables"
  type        = string
  sensitive   = true
}

variable "vercel_project_id" {
  description = "ID of the existing Vercel project for the frontend (referenced, never created/destroyed here)"
  type        = string
}

variable "vercel_team_id" {
  description = "Vercel team ID owning the project; null for a personal account"
  type        = string
  default     = null
}
