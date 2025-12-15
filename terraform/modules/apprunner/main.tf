# ECR repository for container images

locals {
  service_name = "${var.project}-api-service"
}
resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name      = "${var.project}-api-ecr"
    Project   = var.project
    ManagedBy = "terraform"
  }
}

# ECR lifecycle policy to clean up old images
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# IAM role for App Runner
resource "aws_iam_role" "apprunner_instance" {
  name = "${local.service_name}-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "tasks.apprunner.amazonaws.com"
      }
    }]
  })

  tags = {
    Name      = "${local.service_name}-instance-role"
    Project   = var.project
    ManagedBy = "terraform"
  }
}

# IAM role for App Runner access to ECR
resource "aws_iam_role" "apprunner_ecr" {
  name = "${local.service_name}-ecr-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "build.apprunner.amazonaws.com"
      }
    }]
  })

  tags = {
    Name      = "${local.service_name}-ecr-role"
    Project   = var.project
    ManagedBy = "terraform"
  }
}

# Attach ECR access policy
resource "aws_iam_role_policy_attachment" "apprunner_ecr" {
  role       = aws_iam_role.apprunner_ecr.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# App Runner service
resource "aws_apprunner_service" "api" {
  service_name = local.service_name

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr.arn
    }

    image_repository {
      image_configuration {
        port = "8000"

        runtime_environment_variables = var.environment_variables
      }

      image_identifier      = "${aws_ecr_repository.api.repository_url}:${var.image_tag}" # Changed this line
      image_repository_type = "ECR"
    }

    auto_deployments_enabled = false
  }

  instance_configuration {
    cpu               = var.cpu
    memory            = var.memory
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }


  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }

  tags = {
    Name      = local.service_name
    Project   = var.project
    ManagedBy = "terraform"
  }
}
