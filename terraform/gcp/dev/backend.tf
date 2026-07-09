terraform {
  # Bucket is supplied at `terraform init -backend-config="bucket=<state_bucket_name>"`
  # (the tf_bootstrap gcp/ root's output) — never hardcoded here.
  backend "gcs" {
    prefix = "brokelads/dev"
  }
}
