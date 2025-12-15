output "service_id" {
  description = "App Runner service ID"
  value       = aws_apprunner_service.api.service_id
}

output "service_arn" {
  description = "App Runner service ARN"
  value       = aws_apprunner_service.api.arn
}

output "service_url" {
  description = "App Runner service URL"
  value       = aws_apprunner_service.api.service_url
}

output "service_name" {
  description = "App Runner service name"
  value       = aws_apprunner_service.api.service_name
}

output "instance_role_id" {
  description = "App Runner instance role ID"
  value       = aws_iam_role.apprunner_instance.id
}

output "instance_role_arn" {
  description = "App Runner instance role ARN"
  value       = aws_iam_role.apprunner_instance.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.api.repository_url
}

output "ecr_repository_name" {
  description = "ECR repository name"
  value       = aws_ecr_repository.api.name
}
