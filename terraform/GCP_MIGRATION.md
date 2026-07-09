# GCP Migration — App Runner → Cloud Run + Neon

**Supersedes `FARGATE_MIGRATION.md`** (Fargate rejected: always-on task + ALB
flat cost + loses free HTTPS). This is the plan of record for moving BrokeLads
compute + data off AWS to GCP, **keeping Cognito on AWS**.

Status: planning. Bootstrap shipped (`tf_bootstrap` PR #1). App stack next.

---

## Why

App Runner closed to new customers 2026-04-30 (maintenance clock). The move also
takes running cost from **~$35/mo → ~$0–9/mo** (Cloud Run scale-to-zero + Neon;
see `costs/`). Cost is the tailwind; the deprecation is the forcing function.

## Locked decisions (from the 2026-07-09 grill)

| # | Decision |
|---|---|
| Data | **Start fresh** on GCP — no pg_dump. Leagues/fixtures re-ingest; users JIT-provision from Cognito on first login. Only throwaway test bets/cup history lost. |
| Cognito | Stays AWS, but **extract** from the retiring `terraform/dev` stack into its own standalone AWS stack, stood up **fresh** (new empty pool + client id). Old pool `eu-west-2_HSV4yaBye` torn down at cutover. The local pool (`terraform/local`) is untouched. |
| Postgres | **Neon** (not Cloud SQL — no scale-to-zero; not Supabase). Provisioned in Terraform via the Neon provider; pooled connection string → Cloud Run env, mirroring RDS→App Runner today. |
| Compute | **Cloud Run** (min-instances 0, request-billed). Free managed HTTPS. |
| Ingestion cron | **Cloud Scheduler ~5 min** (was EventBridge `rate(1m)`). Reversible knob; jobs self-gate on `min_interval_seconds`, so freshness barely moves. |
| Env model | **One GCP project**, `dev`/`prod` as separate stacks/state (`prefix <app>/<env>` in the one state bucket). **prod scaffolded, never applied.** Only dev is live (AWS prod was never deployed). |
| Naming | Adopt correct naming green-field: `project = "brokelads"` (constant) + `env = dev\|prod\|local`. Archived AWS modules left as frozen reference (not renamed). |
| CI → GCP | **Keyless WIF** (no static key). Bootstrap = `tf_bootstrap` `gcp/` root (PR #1). |
| Cutover | **Parallel-run then flip** (see runbook). |

## Target architecture

```
Browser ──idToken──> Cognito (AWS, unchanged; JWKS verify is provider-agnostic)
   │
   │ NEXT_PUBLIC_API_URL (flip at cutover: App Runner URL → Cloud Run URL)
   ▼
Cloud Run (GCP) ──DATABASE_URL──> Neon (serverless Postgres, scale-to-zero)
   ▲  reads AWS access key + secrets from Secret Manager (boto3 Cognito admin calls)
   │
Cloud Scheduler (~5m) ──X-Cron-Auth-Key──> POST /rapid-api/run-jobs
```

## The bootstrap (done — `tf_bootstrap` gcp/ root, PR #1)

App-agnostic foundation, applied once locally with owner creds:
- GCS Terraform state bucket (versioned, `prevent_destroy`).
- WIF (GitHub OIDC → deployer SA), pinned to repo + `dev` branch.
- Deployer SA granted one **generic** project role (`deployer_role`, default
  `roles/editor`) so it can stand up app stacks itself — like AWS CI-as-admin,
  but keyless + branch-pinned. Generic, not app-specific.

Outputs consumed downstream: `state_bucket_name`, `workload_identity_provider`,
`deployer_service_account_email`.

## App stack to build (`terraform/gcp/`)

Mirror the AWS module+env layout. Composes the **`google`** and **`neon`**
providers in one stack so a single apply stands up DB + compute together.

```
terraform/gcp/
  modules/app/            # one env's worth of the app
    main.tf               # google_project_service (run, artifactregistry,
                          #   cloudscheduler, secretmanager) — APP owns these;
                          #   Cloud Run v2 service; Cloud Scheduler job;
                          #   Secret Manager secrets; runtime SA
    neon.tf               # neon_project / _branch / _database / _role → conn string
    variables.tf          # env, project, region, image_tag, cognito ids, secrets
    outputs.tf            # cloud_run_url
  dev/                    # backend "gcs" prefix brokelads/dev — LIVE
    main.tf, backend.tf, variables.tf, outputs.tf
  prod/                   # backend "gcs" prefix brokelads/prod — SCAFFOLD, never applied
```

**Cloud Run service env** (from the current App Runner env): `DATABASE_URL`
(Neon output), `USER_POOL_ID`/`COGNITO_CLIENT_ID` (new fresh pool), `RAPID_API_KEY`,
`OPENAI_API_KEY`, `CRON_AUTH_KEY`, `ADMIN_SESSION_SECRET`, admin OIDC vars, and
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` via Secret Manager (boto3 needs them
for the Cognito admin calls — App Runner's instance role gave these free; Cloud
Run injects them from Secret Manager). No app code changes.

**Neon provider:** verify current provider source + resource names before writing
(community `kislerdm/neon` vs any official). API key from GitHub secret `NEON_API_KEY`.

## Deployer permissions — RESOLVED

The deployer SA gets a single **generic** project role at bootstrap
(`deployer_role`, default `roles/owner`), so the GCP app **stands itself up**
exactly like the AWS side (whose CI runs as a full admin) — no separate
owner-applied grants step. Owner (not `editor`) because the app stack sets
resource-level IAM — the public Cloud Run invoker binding and the runtime SA's
secret access — and `editor` can't set IAM policy at all. It's still generic
(not `run.admin`/etc.), so the bootstrap stays app-agnostic; and via keyless WIF
+ branch-pinning it's safer than the AWS static admin key.

## Deploy workflow (new `.github/workflows/gcp-deploy.yml`)

Replaces `dev.yml`'s AWS path. On push to `dev`: `google-github-actions/auth`
(WIF, keyless) → build image → push to Artifact Registry → `terraform apply` the
`gcp/dev` stack → patch the Cognito admin-client callback to the Cloud Run host
(the App-Runner-host patch dev.yml does today, retargeted).

## Cutover runbook

1. Apply bootstrap (done-by-Josh) → outputs.
2. Apply the fresh **Cognito** stack (AWS) → new pool/client ids.
3. CI applies `gcp/dev` → Cloud Run live on an empty Neon DB; seed re-ingests.
4. Smoke-test the Cloud Run URL directly (login round-trip vs the new pool).
5. **Flip** FE `NEXT_PUBLIC_API_URL` → Cloud Run URL; repoint FE Cognito ids.
6. Verify end-to-end on the real FE.
7. **Destroy AWS**: `terraform destroy` the App Runner + RDS + scheduler stack
   (stops ~$35/mo). Keep the code.

## AWS wind-down (after cutover proven healthy)

- Move `modules/{apprunner,rds,scheduler}` + `terraform/{dev,prod}` → `terraform/aws/`
  as **reference only** (README banner), NOT a branch.
- Tag the last all-AWS commit **`aws-baseline`** (annotated) — immutable snapshot.
- Cognito stack stays live (it's the extracted AWS Cognito).

## Prerequisites (Josh)

- [x] GCP account, new project, billing linked, region `europe-west2`.
- [x] `NEON_API_KEY` GitHub secret (confirm set).
- [ ] Apply `tf_bootstrap` #1, return `workload_identity_provider`.
- [ ] Neon account + API key generated.
- [ ] Budget alert set in console (kept out of app TF — billing-account governance).
