output "cloud_run_url" {
  description = "Public URL of the dev Cloud Run service (flip FE NEXT_PUBLIC_API_URL to this at cutover)"
  value       = module.app.cloud_run_url
}

output "runtime_service_account_email" {
  value = module.app.runtime_service_account_email
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository name the deploy workflow pushes images to"
  value       = module.app.artifact_registry_repository
}

output "neon_project_id" {
  value = module.app.neon_project_id
}
