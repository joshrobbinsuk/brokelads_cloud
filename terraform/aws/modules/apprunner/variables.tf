variable "project" {
  description = "Project name"
  type        = string
}

variable "cpu" {
  description = "CPU units (0.25 vCPU = 256, 0.5 vCPU = 512, 1 vCPU = 1024, 2 vCPU = 2048)"
  type        = string
  default     = "256"
}

variable "memory" {
  description = "Memory in MB (512, 1024, 2048, 3072, 4096)"
  type        = string
  default     = "512"
}

variable "environment_variables" {
  description = "Environment variables for the application"
  type        = map(string)
  default     = {}
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}
