terraform {
  backend "s3" {
    bucket         = "initial-terraform-state-eu-west-2"
    key            = "bl/prod/terraform.tfstate"
    region         = "eu-west-2"
    dynamodb_table = "initial-terraform-locks"
    encrypt        = true
  }
}
