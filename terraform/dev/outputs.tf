output "agent_lambda_function_name" {
  description = "Name of the Lambda function"
  value       = module.lambda.agent_function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = module.lambda.agent_function_arn
}

output "ecr_repository_url" {
  value = module.apprunner.ecr_repository_url
}

output "apprunner_service_url" {
  value = module.apprunner.service_url
}
