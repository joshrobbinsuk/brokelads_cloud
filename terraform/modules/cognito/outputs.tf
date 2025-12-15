output "cognito_issuer" {
  value = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
}

output "cognito_hosted_ui_base" {
  value = "https://${aws_cognito_user_pool_domain.main.domain}.auth.${var.region}.amazoncognito.com"
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.frontend_client.id
}

output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}
