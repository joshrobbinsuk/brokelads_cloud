variable "project" {
  description = "Naming discriminator for the pool. Kept distinct from bl-dev (old dev), bl-local, bl-prod so nothing collides during the parallel run."
  type        = string
  default     = "brokelads-dev"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-2"
}

variable "admin_password" {
  description = "Permanent password for the initial admin user"
  type        = string
  sensitive   = true
}
