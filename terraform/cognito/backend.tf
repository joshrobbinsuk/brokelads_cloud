terraform {
  backend "s3" {
    bucket         = "initial-terraform-state-eu-west-2"
    key            = "bl/cognito/terraform.tfstate"
    region         = "eu-west-2"
    dynamodb_table = "initial-terraform-locks"
    encrypt        = true
  }
}
