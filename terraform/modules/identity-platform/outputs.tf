# The browser API key GCIP auto-provisions for the config. Public by design —
# it ships to the FE as NEXT_PUBLIC_FIREBASE_API_KEY.
output "firebase_api_key" {
  description = "Web API key for the Identity Platform config (FE apiKey)"
  value       = google_identity_platform_config.default.client[0].api_key
}

output "project_id" {
  description = "GCP project id hosting the config"
  value       = var.gcp_project_id
}
