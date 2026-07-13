terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 7.0"
    }
  }
}

resource "google_project_service" "identitytoolkit" {
  project            = var.gcp_project_id
  service            = "identitytoolkit.googleapis.com"
  disable_on_destroy = false
}

# GCIP (Firebase Auth) tenant config: email+password on, anonymous off, one
# account per email (Firebase default that Cognito couldn't give us).
resource "google_identity_platform_config" "default" {
  project = var.gcp_project_id

  sign_in {
    allow_duplicate_emails = false

    email {
      enabled           = true
      password_required = true
    }

    anonymous {
      enabled = false
    }
  }

  authorized_domains = var.authorized_domains

  depends_on = [google_project_service.identitytoolkit]
}

# Google sign-in from our own page (signInWithPopup), not a hosted-UI interstitial.
resource "google_identity_platform_default_supported_idp_config" "google" {
  project       = var.gcp_project_id
  enabled       = true
  idp_id        = "google.com"
  client_id     = var.google_oauth_client_id
  client_secret = var.google_oauth_client_secret

  depends_on = [google_identity_platform_config.default]
}
