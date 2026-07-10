# Uptime check + email alert on the Cloud Run service's /health endpoint.

resource "google_monitoring_uptime_check_config" "api_health" {
  project      = var.gcp_project_id
  display_name = "${local.name_prefix}-api-health"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.gcp_project_id
      host       = replace(google_cloud_run_v2_service.api.uri, "https://", "")
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_notification_channel" "alert_email" {
  project      = var.gcp_project_id
  display_name = "${local.name_prefix}-alert-email"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "api_uptime" {
  project      = var.gcp_project_id
  display_name = "${local.name_prefix}-api-uptime"
  combiner     = "OR"

  conditions {
    display_name = "Uptime check failed"

    condition_threshold {
      # REDUCE_COUNT_FALSE turns the per-location check_passed booleans into a
      # count of failing checker locations — fire when more than one location
      # reports failure (Google's canonical uptime-alert recipe).
      filter          = "resource.type=\"uptime_url\" AND metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.api_health.uptime_check_id}\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 1

      aggregations {
        alignment_period     = "1200s"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.*"]
        per_series_aligner   = "ALIGN_NEXT_OLDER"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.alert_email.name]

  depends_on = [google_project_service.apis]
}
