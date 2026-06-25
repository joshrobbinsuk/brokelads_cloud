variable "project" {
  description = "Project name"
  type        = string
  default     = "bl-dev"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "bladmin"
  sensitive   = true
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "rapid_api_key" {
  description = "Rapid API Key for external API access"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key for the Ask the Pundit feature"
  type        = string
  sensitive   = true
}

variable "admin_session_secret" {
  description = "Secret used to sign admin sessions"
  type        = string
  sensitive   = true
}

variable "admin_password" {
  description = "Permanent password for the Cognito admin user"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-2"
}

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
