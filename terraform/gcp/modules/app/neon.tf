# Neon (serverless Postgres) — provisions one project per env, mirroring the
# AWS RDS module's one-instance-per-env shape. The `neon` provider is
# configured by the caller (dev/main.tf, prod/main.tf); it isn't declared here.

resource "neon_project" "this" {
  name       = local.name_prefix
  region_id  = var.neon_region_id
  pg_version = 16

  # The provider defaults PITR retention to 86400s (1 day), which exceeds this
  # Neon tier's 21600s (6h) cap and fails the apply. A fresh-start demo doesn't
  # need much history — keep a small window, comfortably under the cap.
  history_retention_seconds = 3600
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

  # Neon rejects role creation on a branch that has no read-write endpoint yet
  # ("no read-write endpoint for branch"). The endpoint and role otherwise
  # create in parallel — force the endpoint first. (database owner_name -> role,
  # so the database follows transitively.)
  depends_on = [neon_endpoint.app]
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
  # With pooler_enabled = true, neon_endpoint.host ALREADY returns the pooled
  # host (ep-...-pooler.<region>.aws.neon.tech). Use it directly — appending
  # "-pooler" again produced "-pooler-pooler", which misroutes Neon's SNI and
  # surfaces as "password authentication failed".
  database_url = "postgresql://${neon_role.app.name}:${urlencode(neon_role.app.password)}@${neon_endpoint.app.host}/${neon_database.app.name}?sslmode=require"
}
