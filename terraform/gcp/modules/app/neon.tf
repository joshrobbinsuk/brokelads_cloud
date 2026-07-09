# Neon (serverless Postgres) — provisions one project per env, mirroring the
# AWS RDS module's one-instance-per-env shape. The `neon` provider is
# configured by the caller (dev/main.tf, prod/main.tf); it isn't declared here.

resource "neon_project" "this" {
  name       = local.name_prefix
  region_id  = var.neon_region_id
  pg_version = 16
}

resource "neon_branch" "this" {
  project_id = neon_project.this.id
  parent_id  = neon_project.this.default_branch_id
  name       = var.env
}

resource "neon_role" "app" {
  project_id = neon_project.this.id
  branch_id  = neon_branch.this.id
  name       = "brokelads"
}

resource "neon_database" "app" {
  project_id = neon_project.this.id
  branch_id  = neon_branch.this.id
  name       = "bl"
  owner_name = neon_role.app.name
}

resource "neon_endpoint" "app" {
  project_id     = neon_project.this.id
  branch_id      = neon_branch.this.id
  type           = "read_write"
  pooler_enabled = true
}

locals {
  # Neon's pooled hostname convention inserts "-pooler" before the first dot
  # of the endpoint host (e.g. ep-foo.eu-west-2.aws.neon.tech ->
  # ep-foo-pooler.eu-west-2.aws.neon.tech) — see
  # https://neon.com/docs/connect/connect-from-any-app. The provider doesn't
  # expose a separate pooled-host attribute on neon_endpoint, so this is
  # constructed rather than read directly; verify against the Neon console
  # after the first apply.
  neon_host_parts  = split(".", neon_endpoint.app.host)
  neon_pooler_host = format("%s-pooler.%s", local.neon_host_parts[0], join(".", slice(local.neon_host_parts, 1, length(local.neon_host_parts))))

  database_url = "postgresql://${neon_role.app.name}:${urlencode(neon_role.app.password)}@${local.neon_pooler_host}/${neon_database.app.name}?sslmode=require"
}
