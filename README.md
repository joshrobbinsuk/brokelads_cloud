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

## Deployment

Changes are automatically deployed via GitHub Actions:
- Push to `dev` → Deploys to dev environment
- Merge to `main` → Deploys to prod environment
