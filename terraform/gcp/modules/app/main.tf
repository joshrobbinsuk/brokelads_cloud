terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 7.0"
    }
    neon = {
      source  = "kislerdm/neon"
      version = ">= 0.13, < 1.0"
    }
    vercel = {
      source  = "vercel/vercel"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

locals {
  name_prefix = "${var.project}-${var.env}"

  # Non-secret config, injected as plain Cloud Run env vars.
  plain_env = {
    ENVIRONMENT             = var.env
    USER_POOL_ID            = var.user_pool_id
    COGNITO_CLIENT_ID       = var.cognito_client_id
    ADMIN_COGNITO_CLIENT_ID = var.admin_cognito_client_id
    OPENAI_MODEL            = var.openai_model
  }

  # Secret config: each becomes a Secret Manager secret + version, and is
  # wired into Cloud Run via a secret env valueSource (never a plain value).
  secret_env = {
    DATABASE_URL                = local.database_url
    RAPID_API_KEY               = var.rapid_api_key
    OPENAI_API_KEY              = var.openai_api_key
    CRON_AUTH_KEY               = random_password.cron_auth_key.result
    ADMIN_SESSION_SECRET        = var.admin_session_secret
    ADMIN_COGNITO_CLIENT_SECRET = var.admin_cognito_client_secret
    AWS_ACCESS_KEY_ID           = var.aws_access_key_id
    AWS_SECRET_ACCESS_KEY       = var.aws_secret_access_key
  }
}

# Self-generated, mirroring the AWS scheduler module's random_password —
# shared between the Cloud Run secret env and the Cloud Scheduler header
# below, so nothing needs to feed it in from CI.
resource "random_password" "cron_auth_key" {
  length  = 32
  special = false
}

# The app owns enabling its own APIs (mirrors the AWS side, where CI runs
# with a generic admin-equivalent role and each module provisions what it
# needs).
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
  ])

  project            = var.gcp_project_id
  service            = each.value
  disable_on_destroy = false
}

# Artifact Registry repo the deploy workflow pushes images into (mirrors the
# ECR repo the apprunner module creates on the AWS side).
resource "google_artifact_registry_repository" "api" {
  project       = var.gcp_project_id
  location      = var.region
  repository_id = local.name_prefix
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "runtime" {
  project      = var.gcp_project_id
  account_id   = "${local.name_prefix}-run"
  display_name = "${local.name_prefix} Cloud Run runtime"
}

resource "google_secret_manager_secret" "this" {
  for_each = local.secret_env

  project   = var.gcp_project_id
  secret_id = "${local.name_prefix}-${lower(replace(each.key, "_", "-"))}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "this" {
  for_each = local.secret_env

  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = each.value
}

resource "google_secret_manager_secret_iam_member" "runtime_access" {
  for_each = local.secret_env

  project   = var.gcp_project_id
  secret_id = google_secret_manager_secret.this[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name_prefix}-api"
  project  = var.gcp_project_id
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = 0
    }

    containers {
      image = var.image

      ports {
        container_port = 8000
      }

      dynamic "env" {
        for_each = local.plain_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.key].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.this,
    google_secret_manager_secret_iam_member.runtime_access,
  ]
}

# Public API — no IAM-gated invocation, mirrors App Runner's default public URL.
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.gcp_project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Ingestion cron: ~5 min, POSTs to the ingestion endpoint with the shared
# X-Cron-Auth-Key header (the app's own auth — the service itself is public,
# so no OIDC identity token is required here).
resource "google_cloud_scheduler_job" "run_jobs" {
  name      = "${local.name_prefix}-run-jobs"
  project   = var.gcp_project_id
  region    = var.region
  schedule  = "*/5 * * * *"
  time_zone = "Etc/UTC"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.api.uri}/rapid-api/run-jobs"

    headers = {
      "X-Cron-Auth-Key" = random_password.cron_auth_key.result
    }
  }

  depends_on = [google_project_service.apis]
}
