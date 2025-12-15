resource "aws_cognito_user_pool" "main" {
  name                     = "${var.project}-user-pool"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "INACTIVE"

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "brokelads-auth-${var.project}"
  user_pool_id = aws_cognito_user_pool.main.id
}


# frontend client
resource "aws_cognito_user_pool_client" "frontend_client" {
  name         = "${var.project}-fe-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret              = false
  supported_identity_providers = ["COGNITO"]

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]
}
