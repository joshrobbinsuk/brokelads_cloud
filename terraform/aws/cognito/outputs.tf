# Non-secret ids — safe to print in CI and set as GitHub secrets for the GCP deploy.
output "user_pool_id" {
  description = "Cognito user pool id (also the admin pool id — same pool)"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "Frontend app client id"
  value       = module.cognito.cognito_client_id
}

output "admin_client_id" {
  description = "Admin OIDC app client id"
  value       = module.cognito.admin_client_id
}

output "cognito_issuer" {
  description = "Token issuer URL"
  value       = module.cognito.cognito_issuer
}

# Sensitive — never printed in CI. Read locally with
# `terraform output -raw admin_client_secret` and set as a GitHub secret.
output "admin_client_secret" {
  description = "Admin OIDC app client secret"
  value       = module.cognito.admin_client_secret
  sensitive   = true
}
