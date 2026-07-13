variable "gcp_project_id" {
  description = "GCP project ID that hosts the Identity Platform config"
  type        = string
}

variable "authorized_domains" {
  description = "Domains allowed to complete the Google sign-in redirect (localhost, the custom domain, the vercel app domain, and <project>.firebaseapp.com)"
  type        = list(string)
}

variable "google_oauth_client_id" {
  description = "Google OAuth Web client id backing the google.com IdP (GitHub secret GOOGLE_OAUTH_CLIENT_ID)"
  type        = string
}

variable "google_oauth_client_secret" {
  description = "Google OAuth Web client secret backing the google.com IdP (GitHub secret GOOGLE_OAUTH_CLIENT_SECRET)"
  type        = string
  sensitive   = true
}
