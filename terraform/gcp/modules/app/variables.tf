variable "project" {
  description = "Project name constant"
  type        = string
  default     = "brokelads"
}

variable "env" {
  description = "Environment (dev|prod)"
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env must be \"dev\" or \"prod\"."
  }
}

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
  description = "Full Artifact Registry image ref to deploy, e.g. europe-west2-docker.pkg.dev/<gcp_project_id>/brokelads-dev/api:<tag>"
  type        = string
}

# --- Admin panel Google OIDC. The client id is not secret; the secret is. ---

variable "admin_google_client_id" {
  description = "Google OAuth Web client id for the admin panel OIDC login"
  type        = string
}

variable "openai_model" {
  description = "OpenAI model id for Ask-the-Pundit"
  type        = string
  default     = "gpt-5-mini"
}

variable "cors_origins" {
  description = "Allowed CORS origins for the API, joined into the CORS_ORIGINS env var"
  type        = list(string)
}

variable "alert_email" {
  description = "Email address for the uptime alert notification channel"
  type        = string
}

# --- Secrets: values fed by CI (GitHub secrets), never invented here ---

variable "rapid_api_key" {
  description = "RapidAPI key for API-Football ingestion"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key for Ask-the-Pundit"
  type        = string
  sensitive   = true
}

variable "admin_session_secret" {
  description = "Secret used to sign admin panel sessions"
  type        = string
  sensitive   = true
}

variable "admin_google_client_secret" {
  description = "Client secret for the admin panel Google OIDC login"
  type        = string
  sensitive   = true
}

# --- Firebase / Identity Platform (FE env vars; api_key is public-by-design) ---

variable "firebase_api_key" {
  description = "Identity Platform web API key (from the identity-platform module), shipped to the FE as NEXT_PUBLIC_FIREBASE_API_KEY"
  type        = string
}

variable "firebase_auth_domain" {
  description = "authDomain the FE initialises Firebase with (the branded custom domain). No default — each env root names its own domain so prod can never silently inherit dev's."
  type        = string
}

# --- Neon ---

variable "neon_region_id" {
  description = "Neon region id for the project (aws-eu-west-2 keeps data alongside the Cognito pool in London)"
  type        = string
  default     = "aws-eu-west-2"
}

# --- Vercel (frontend env vars, mirrors the AWS stack's vercel.tf) ---

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
