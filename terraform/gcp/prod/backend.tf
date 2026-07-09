terraform {
  # SCAFFOLD — never applied (see terraform/GCP_MIGRATION.md: "prod
  # scaffolded, never applied"; AWS prod was never deployed either).
  # Bucket is supplied at `terraform init -backend-config="bucket=<state_bucket_name>"`.
  backend "gcs" {
    prefix = "brokelads/prod"
  }
}
