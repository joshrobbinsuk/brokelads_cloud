output "user_pool_id" {
  description = "Cognito user pool id"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito frontend app client id"
  value       = module.cognito.cognito_client_id
}
