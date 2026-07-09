# AWS stack — retired (reference only)

The App Runner + RDS + EventBridge scheduler + Lambda stack that ran BrokeLads
before the migration to **GCP Cloud Run + Neon on 2026-07-09**. These resources
have been **destroyed** — this tree is kept purely as a reference for AWS /
Terraform patterns.

**Do NOT `terraform apply` anything in here.** It's a snapshot, not a deployable
stack:

- It's unmaintained, and the module paths aren't fixed for this location — e.g.
  the Cognito module these stacks referenced (`../modules/cognito`) **stayed
  live** at `terraform/modules/cognito`, so that reference no longer resolves
  from here. That's intentional; the AWS Cognito pool was extracted and kept.
- The last commit with the AWS stack live is tagged **`aws-baseline`**.

## Where the live infra is now
- `terraform/gcp/` — Cloud Run + Artifact Registry + Cloud Scheduler + Secret
  Manager + Neon (compute + data).
- `terraform/cognito/` — the alpha Cognito pool (stayed on AWS).
- `terraform/local/` — the local-dev Cognito pool.

See `../GCP_MIGRATION.md` for the full migration record.
