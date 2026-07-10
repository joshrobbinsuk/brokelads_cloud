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

# --- Cognito (stays on AWS, in its own standalone stack; the caller reads
# these from that stack's remote state — never fed in directly by CI). Ids
# are not secret, the admin client secret is. ---

variable "user_pool_id" {
  description = "AWS Cognito user pool ID (frontend/client pool)"
  type        = string
}

variable "cognito_client_id" {
  description = "AWS Cognito app client ID (frontend/client pool)"
  type        = string
}

variable "admin_cognito_client_id" {
  description = "AWS Cognito app client ID for the admin OIDC client"
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

variable "admin_cognito_client_secret" {
  description = "Client secret for the Cognito admin OIDC app client"
  type        = string
  sensitive   = true
}

variable "aws_access_key_id" {
  description = "AWS access key so the app can make Cognito admin calls (AdminDeleteUser etc) via boto3 from GCP"
  type        = string
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "AWS secret key paired with aws_access_key_id"
  type        = string
  sensitive   = true
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
