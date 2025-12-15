variable "project" {
  type        = string
  description = "Project name"
}

variable "apprunner_service_url" {
  type        = string
  description = "App Runner service URL"
}

variable "apprunner_instance_role_id" {
  type        = string
  description = "App Runner instance role ID"
}

variable "apprunner_service_name" {
  type        = string
  description = "App Runner service name"
}

variable "cron_schedule_expression" {
  type        = string
  description = "EventBridge schedule expression"
  default     = "rate(1 minute)"
}

variable "cron_endpoint_path" {
  type        = string
  description = "Path for cron endpoint"
  default     = "rapid-api/run-jobs"
}
