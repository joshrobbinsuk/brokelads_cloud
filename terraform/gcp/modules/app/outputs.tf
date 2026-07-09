output "cloud_run_url" {
  description = "Public URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.api.uri
}

output "runtime_service_account_email" {
  description = "Service account the Cloud Run container runs as"
  value       = google_service_account.runtime.email
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository name images are pushed to"
  value       = google_artifact_registry_repository.api.repository_id
}

output "neon_project_id" {
  description = "Neon project ID backing this env"
  value       = neon_project.this.id
}
