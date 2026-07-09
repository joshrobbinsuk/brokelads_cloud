variable "project" {
  description = "Project name"
  type        = string
  default     = "bl-local"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-2"
}

variable "admin_password" {
  description = "Permanent password for the Cognito admin user"
  type        = string
  sensitive   = true
}
