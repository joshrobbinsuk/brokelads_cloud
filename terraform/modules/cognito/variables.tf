variable "project" {
  description = "Project name"
  type        = string
}

variable "admin_email" {
  description = "Email address for the initial admin user"
  type        = string
  default     = "joshrobbinsukdev@gmail.com"
}

variable "region" {
  description = "AWS region"
  type        = string
}
