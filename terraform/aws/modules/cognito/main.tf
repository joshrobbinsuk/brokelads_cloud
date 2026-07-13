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

  # Branded sign-up email (replaces the bare Cognito default). {####} is the
  # required confirmation-code placeholder.
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Your BrokeLads code"
    email_message        = "Welcome to BrokeLads. Your confirmation code is {####}. Enter it to finish setting up and get in on this week's cup."
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

# Admin client (Cognito-hosted OAuth login for the sqladmin UI)
resource "aws_cognito_user_pool_client" "admin_client" {
  name         = "${var.project}-admin-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret                      = true
  supported_identity_providers         = ["COGNITO"]
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "email", "profile"]

  # Placeholders only. The real callback is the App Runner service URL, which consumes this
  # client's id/secret — wiring it here would create a Terraform dependency cycle. CI patches
  # the real URL post-apply via `aws cognito-idp update-user-pool-client`, so we ignore drift.
  callback_urls = ["https://localhost/auth/callback"]
  logout_urls   = ["https://localhost"]

  lifecycle {
    ignore_changes = [callback_urls, logout_urls]
  }
}

resource "aws_cognito_user_group" "admins" {
  name         = "admins"
  user_pool_id = aws_cognito_user_pool.main.id
}

resource "aws_cognito_user" "admin" {
  user_pool_id   = aws_cognito_user_pool.main.id
  username       = var.admin_email
  password       = var.admin_password
  message_action = "SUPPRESS"

  attributes = {
    email          = var.admin_email
    email_verified = "true"
  }
}

resource "aws_cognito_user_in_group" "admin" {
  user_pool_id = aws_cognito_user_pool.main.id
  group_name   = aws_cognito_user_group.admins.name
  username     = aws_cognito_user.admin.username
}
