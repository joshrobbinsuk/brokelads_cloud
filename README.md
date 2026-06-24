# BL

Backend services for a sports betting app. The repo contains the FastAPI API, data ingestion from a sports odds provider, and AWS infrastructure managed with Terraform.

## Highlights

- **FastAPI + PostgreSQL** for the core API and data model
- **Odds & fixtures ingestion** via RapidAPI (API-Football)
- **Bet settlement jobs** exposed via an admin UI
- **AWS Cognito auth** for client-facing endpoints
- **Infrastructure-as-code** with Terraform and CI/CD via GitHub Actions

## Repository Structure

```
bl/
├── .github/workflows/    # GitHub Actions
├── api/                  # FastAPI service, migrations, tests
├── functions/            # Additional serverless functions
├── terraform/
│   ├── modules/         # Reusable modules
│   ├── dev/            # Dev environment config
│   └── prod/           # Prod environment config
```

## Local Development

- API setup and Docker workflow: see `api/README.md`
- Local dev notes: see `LOCAL_DEV.md`

## Deployment

Managed with Terraform and GitHub Actions. Branch-based deploys are configured in `.github/workflows/`.

### Prerequisites
- AWS CLI configured
- Terraform >= 1.0
- GitHub repository with AWS credentials in secrets

### GitHub Secrets Required
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `ADMIN_PASSWORD` (permanent password for the Cognito admin user; must satisfy the Cognito pool password policy — at least 12 characters with upper- and lower-case letters, a number, and a symbol — or `terraform apply` fails opaquely)
- `VERCEL_API_TOKEN` (project-scoped token used by Terraform to manage frontend env vars)
- `VERCEL_PROJECT_ID` (ID of the existing Vercel frontend project)
- `VERCEL_DEPLOY_HOOK_URL` (deploy hook used to trigger the frontend rebuild after apply)

Admin login is Cognito-native. The DB master credentials and the admin user are generated/managed by Terraform, so the old `DB_USERNAME`, `DB_PASSWORD`, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` GitHub secrets are no longer used and should be removed. After the first deploy and confirming admin login works, delete the old Google OAuth client in GCP.

The `dev` deploy propagates the Cognito values and the App Runner API URL into the Vercel frontend project (as `NEXT_PUBLIC_*` env vars) and then triggers a frontend rebuild via the deploy hook, so the frontend no longer needs these values pasted in by hand. The Vercel project is referenced by ID and is never created or destroyed by Terraform.

### Branch-based deploys
Changes are automatically deployed via GitHub Actions:
- Push to `dev` → Deploys to dev environment
- Merge to `main` → Deploys to prod environment
