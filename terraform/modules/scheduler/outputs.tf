output "cron_auth_key_value" {
  description = "Cron auth key value"
  value       = random_password.cron_auth_key.result
  sensitive   = true
}
