output "agent_function_name" {
  description = "Name of the Agent Lambda function"
  value       = aws_lambda_function.agent_function.function_name
}

output "agent_function_arn" {
  description = "ARN of the Agent Lambda function"
  value       = aws_lambda_function.agent_function.arn
}

output "agent_invoke_arn" {
  description = "Invoke ARN of the Agent Lambda function"
  value       = aws_lambda_function.agent_function.invoke_arn
}

output "agent_role_arn" {
  description = "ARN of the Agent Lambda execution role"
  value       = aws_iam_role.agent_lambda_role.arn
}
