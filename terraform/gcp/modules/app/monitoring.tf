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
      # Fire when fewer than half the checks in the last 10 minutes passed, and
      # keep failing for 5. The previous recipe (REDUCE_COUNT_FALSE over
      # ALIGN_NEXT_OLDER, duration 60s) had no hysteresis against a 300s check
      # period: on 2026-09-01 one 12-hour outage arrived as 24 separate opens
      # because the wedged instance intermittently answered. One outage should
      # be one email.
      filter          = "resource.type=\"uptime_url\" AND metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.api_health.uptime_check_id}\""
      duration        = "300s"
      comparison      = "COMPARISON_LT"
      threshold_value = 0.5

      aggregations {
        alignment_period     = "600s"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields      = ["resource.label.*"]
        per_series_aligner   = "ALIGN_FRACTION_TRUE"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"

    # Matched to auto_close deliberately: this limit is per *policy*, not per
    # incident, so a longer window could swallow the opening notification of a
    # second, unrelated outage. One email per 30 minutes of sustained failure.
    notification_rate_limit {
      period = "1800s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.alert_email.name]

  depends_on = [google_project_service.apis]
}

# The cron is the only thing that moves data through the app, and it can fail
# completely while the site itself stays green — on 2026-09-01 it returned 504
# seventy-two times and nothing said a word.
#
# Built on the request log rather than Cloud Scheduler's own metrics: this
# project has never had a single cloudscheduler.googleapis.com metric written to
# it (997 metric descriptors, none matching "scheduler"), so a policy filtering
# on job/attempt_count would apply cleanly and then stay silent forever. The
# request log for this endpoint is written every minute and is what the incident
# was actually diagnosed from.
resource "google_logging_metric" "cron_failures" {
  project = var.gcp_project_id
  name    = "${local.name_prefix}-cron-failures"
  filter  = "resource.type=\"cloud_run_revision\" AND httpRequest.requestUrl:\"/rapid-api/run-jobs\" AND httpRequest.status>=400"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "cron_failures" {
  project      = var.gcp_project_id
  display_name = "${local.name_prefix}-cron-failing"
  combiner     = "OR"

  conditions {
    display_name = "Ingestion cron requests failing"

    condition_threshold {
      filter     = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.cron_failures.name}\""
      duration   = "0s"
      comparison = "COMPARISON_GT"
      # 5, not 3: crown_cup posts to this same URL with retry_count = 3, so one
      # transient blip there is 1 + 3 = 4 failing requests in a window and would
      # otherwise page as an ingestion outage. A real ingestion failure inside
      # the 12-22 window fails ~10 attempts per window, well clear of this.
      threshold_value = 5

      aggregations {
        alignment_period   = "600s"
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"

    notification_rate_limit {
      period = "1800s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.alert_email.name]

  depends_on = [google_project_service.apis]
}
