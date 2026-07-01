# Init script

One-shot script that bootstraps a Canary test account via the API. It:

1. Registers a user account (skips if it already exists)
2. Logs in and obtains tokens
3. Connects a GitHub repository (creates it if it doesn't exist)
4. Stores Snowflake credentials
5. Creates a data warehouse
6. Sets up CI/CD — opens a PR with workflow files and repository secrets (skippable)
7. Bootstraps Terraform state infrastructure — S3 buckets + DynamoDB lock tables (skippable)

At the end it prints a refresh token — save it.

## Prerequisites

- The Canary backend stack must be running (`docker compose up` from the repo root)
- A GitHub personal access token with `repo` scope
- Snowflake credentials (RSA private key, base64-encoded)

## Configuration

All configuration is read from `.env`. Copy the example and fill in your values:

```bash
cp .env.example .env
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `API_BASE_URL` | No | Backend URL (default: `http://backend:8000/api/v1`) |
| `ACCOUNT_NAME` | Yes | Display name for the account |
| `ACCOUNT_DOMAIN` | Yes | Domain for the account (e.g. `myproject.dev`) |
| `ACCOUNT_USERNAME` | Yes | Login username |
| `ACCOUNT_EMAIL` | Yes | Account email address |
| `ACCOUNT_PASSWORD` | Yes | Account password |
| `GITHUB_PAT` | Yes | GitHub personal access token (`repo` scope) |
| `GITHUB_PROJECT_NAME` | Yes | Internal project name (used as identifier) |
| `GITHUB_REPO_FULL_NAME` | Yes | GitHub repo in `owner/repo` format |
| `GITHUB_BRANCH` | No | Target branch (default: `develop`) |
| `GITHUB_INFRA_BASE_PATH` | No | Path to infra within the repo (default: `infrastructure`) |
| `GITHUB_API_URL` | No | GitHub API URL (default: `https://api.github.com`) |
| `GITHUB_CREATE_CICD` | No | Create CI/CD workflows and secrets (default: `true`) |
| `GITHUB_AUTO_MERGE` | No | Auto-merge PRs opened by Canary (default: `false`) |
| `GITHUB_SKIP_BOOTSTRAP` | No | Skip Terraform state bootstrap, skip root HCL files in LZ PRs (default: `false`) |
| `GITHUB_SKIP_MODULE_IMPORT` | No | Skip copying Terraform modules into LZ PRs (default: `false`) |
| `WAREHOUSE_NAME` | Yes | Snowflake warehouse name |
| `WAREHOUSE_TYPE` | No | Warehouse type (default: `snowflake`) |
| `BOOTSTRAP_DEV_STATE_BUCKET` | If bootstrapping | S3 bucket for dev Terraform state |
| `BOOTSTRAP_DEV_STATE_REGION` | If bootstrapping | AWS region for dev state bucket |
| `BOOTSTRAP_DEV_STATE_LOCK_TABLE` | If bootstrapping | DynamoDB table for dev state locking |
| `BOOTSTRAP_PROD_STATE_BUCKET` | If bootstrapping | S3 bucket for prod Terraform state |
| `BOOTSTRAP_PROD_STATE_REGION` | If bootstrapping | AWS region for prod state bucket |
| `BOOTSTRAP_PROD_STATE_LOCK_TABLE` | If bootstrapping | DynamoDB table for prod state locking |
| `AWS_ACCESS_KEY_ID` | If bootstrapping | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | If bootstrapping | AWS secret key |
| `SNOWFLAKE_ORGANIZATION_NAME` | Yes | Snowflake organization name |
| `SNOWFLAKE_ACCOUNT_NAME` | Yes | Snowflake account name |
| `SNOWFLAKE_USER` | Yes | Snowflake username |
| `SNOWFLAKE_AUTHENTICATOR` | No | Snowflake auth method (default: `SNOWFLAKE_JWT`) |
| `SNOWFLAKE_PRIVATE_KEY_B64` | Yes | Base64-encoded RSA private key (PEM) |

To base64-encode your Snowflake PEM key:

```bash
base64 -i rsa_key.p8 | tr -d '\n'
```

### Flags for repos with existing infrastructure

When connecting a repo that already has its own Terraform state backend and CI/CD (e.g. CircleCI), set:

```bash
GITHUB_SKIP_BOOTSTRAP=true
GITHUB_SKIP_MODULE_IMPORT=true
GITHUB_CREATE_CICD=false
```

This means landing zone PRs will only contain the terragrunt config files for the new landing zone — no root `terragrunt.hcl`, `global.hcl`, `account.hcl`, or module directories.

## Run via Docker Compose

This is the recommended way. The container joins the `canary_default` network so it can reach the backend by service name.

```bash
# From the repo root, make sure the main stack is up first:
docker compose --env-file .env.dev up -d

# Then from this directory:
cd scripts/init
docker compose run --rm init python init.py
```

## Run directly with Python

```bash
cd scripts/init
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python init.py
```

When running directly, update `API_BASE_URL` in `.env` to `http://localhost:8000/api/v1` if the backend is not reachable at the Docker service hostname.
