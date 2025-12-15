locals {
  agent_function_name = "${var.project}-agent"
}


# Archive the Lambda function code
data "archive_file" "agent_lambda_zip" {
  type        = "zip"
  source_dir = "${path.module}/../../../functions/agent"
  output_path = "${path.module}/agent_lambda_function.zip"
}

# IAM role for Lambda execution
resource "aws_iam_role" "agent_lambda_role" {
  name = "${local.agent_function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = local.agent_function_name
    Project     = var.project
    ManagedBy   = "terraform"
  }
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "agent_lambda_basic" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.agent_lambda_role.name
}

# Lambda function
resource "aws_lambda_function" "agent_function" {
  filename         = data.archive_file.agent_lambda_zip.output_path
  function_name    = local.agent_function_name
  role            = aws_iam_role.agent_lambda_role.arn
  handler         = "main.agent_handler"
  source_code_hash = data.archive_file.agent_lambda_zip.output_base64sha256
  runtime         = var.runtime
  timeout         = var.timeout
  memory_size     = var.memory_size

  tags = {
    Name        = local.agent_function_name
    Project     = var.project
    ManagedBy   = "terraform"
  }
}
