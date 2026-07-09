resource "random_password" "cron_auth_key" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "cron_auth_key_1" {
  name                    = "${var.project}-cron-auth-key-1"
  description             = "Authentication key for EventBridge cron jobs"
  recovery_window_in_days = 0

  tags = {
    Name      = "${var.project}-cron-auth-key"
    Project   = var.project
    ManagedBy = "terraform"
  }
}

resource "aws_secretsmanager_secret_version" "cron_auth_key" {
  secret_id     = aws_secretsmanager_secret.cron_auth_key_1.id
  secret_string = random_password.cron_auth_key.result
}

# Role used by EventBridge RULE to invoke the API Destination
# (Reuses your existing name; principal is events.amazonaws.com, not scheduler.amazonaws.com)
resource "aws_iam_role" "eventbridge_scheduler" {
  name = "${var.project}-eventbridge-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
    }]
  })

  tags = {
    Name      = "${var.project}-eventbridge-scheduler-role"
    Project   = var.project
    ManagedBy = "terraform"
  }
}

# Your App Runner instance role can read the secret (unchanged)
resource "aws_iam_role_policy" "apprunner_read_secrets" {
  name = "${var.apprunner_service_name}-read-secrets"
  role = var.apprunner_instance_role_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = aws_secretsmanager_secret.cron_auth_key_1.arn
    }]
  })
}

resource "aws_cloudwatch_event_connection" "cron_auth" {
  name               = "${var.project}-cron-connection"
  description        = "Connection with auth for cron jobs"
  authorization_type = "API_KEY"

  auth_parameters {
    api_key {
      key   = "X-Cron-Auth-Key"
      value = random_password.cron_auth_key.result
    }
  }
}

resource "aws_cloudwatch_event_api_destination" "apprunner_cron" {
  name                             = "${var.project}-apprunner-cron-destination"
  description                      = "App Runner cron endpoint"
  invocation_endpoint              = "https://${var.apprunner_service_url}${var.cron_endpoint_path}"
  http_method                      = "POST"
  invocation_rate_limit_per_second = 10
  connection_arn                   = aws_cloudwatch_event_connection.cron_auth.arn
}

# Allow EventBridge to invoke the API destination
resource "aws_iam_role_policy" "eventbridge_invoke_api_destination" {
  name = "${var.project}-invoke-api-destination"
  role = aws_iam_role.eventbridge_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "events:InvokeApiDestination"
      ]
      Resource = aws_cloudwatch_event_api_destination.apprunner_cron.arn
    }]
  })
}

# Scheduled rule (cron/rate) -> API Destination -> App Runner
resource "aws_cloudwatch_event_rule" "cron_rapid_api_data" {
  name                = "cron-rapid-api-data"
  schedule_expression = var.cron_schedule_expression
}

resource "aws_cloudwatch_event_target" "cron_rapid_api_data" {
  rule     = aws_cloudwatch_event_rule.cron_rapid_api_data.name
  arn      = aws_cloudwatch_event_api_destination.apprunner_cron.arn
  role_arn = aws_iam_role.eventbridge_scheduler.arn

  input = jsonencode({
    job_name  = "data-job"
    timestamp = "scheduled_time"
  })
}
