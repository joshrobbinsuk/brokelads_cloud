# bl

Internal Python Lambda function deployed via Terraform and GitHub Actions.

## Architecture

- **Dev environment**: Deployed on push/merge to `dev` branch
- **Prod environment**: Deployed on merge to `main` branch
- **Infrastructure**: AWS Lambda functions managed by Terraform
- **State**: Stored in S3 backend (`initial-terraform-state-eu-west-2`)

## Environments

### Dev
- Lambda: `bl-dev-lambda-hello`
- Deployed from: `dev` branch

### Prod
- Lambda: `bl-prod-lambda-hello`
- Deployed from: `main` branch

## Repository Structure

```
bl/
├── .github/workflows/    # GitHub Actions
├── terraform/
│   ├── modules/         # Reusable modules
│   ├── dev/            # Dev environment config
│   └── prod/           # Prod environment config
└── src/                # Lambda function code
```

## Setup

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

## Testing Lambda

```bash
# Test dev
aws lambda invoke --function-name bl-dev-lambda-hello output.json

# Test prod
aws lambda invoke --function-name bl-prod-lambda-hello output.json
```
