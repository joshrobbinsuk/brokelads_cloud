
locals {
  rds_identifier = "${var.project}-rds"
}
# Security group for RDS
resource "aws_security_group" "rds" {
  name        = "${local.rds_identifier}-sg"
  description = "Security group for ${local.rds_identifier} RDS instance"

  # Allow PostgreSQL from anywhere (will be restricted by password)
  # In production, we'd limit this to specific IPs/CIDR blocks
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "PostgreSQL access"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = {
    Name        = "${local.rds_identifier}-sg"
    Project     = var.project
    ManagedBy   = "terraform"
  }
}

# RDS instance
resource "aws_db_instance" "postgres" {
  identifier     = local.rds_identifier
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = var.storage_type
  storage_encrypted     = var.storage_encrypted

  db_name  = "bl"
  username = var.username
  password = var.password

  publicly_accessible    = true
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = var.backup_retention_period
  backup_window          = var.backup_window
  maintenance_window     = var.maintenance_window

  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${local.rds_identifier}-final-snapshot"

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = {
    Name        = local.rds_identifier
    Project     = var.project
    ManagedBy   = "terraform"
  }
}
