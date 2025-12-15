variable "project" {
  description = "Project name"
  type        = string
  default     = "bl-prod"
}

variable "admin_session_secret" {
  description = "Secret used to sign admin sessions"
  type        = string
  sensitive   = true
}

variable "google_client_id" {
  description = "Google OAuth client ID"
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth client secret"
  type        = string
  sensitive   = true
}

