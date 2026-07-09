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

# --- Cognito ids are NOT vars here: this stack reads them straight from the
# standalone Cognito stack's remote state (see the data source in main.tf). ---

variable "openai_model" {
  type    = string
  default = "gpt-5-mini"
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

variable "aws_access_key_id" {
  type      = string
  sensitive = true
}

variable "aws_secret_access_key" {
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
