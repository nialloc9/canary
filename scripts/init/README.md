# Init script

One-shot script that bootstraps a Canary test account via the API. It:

1. Registers a user account (skips if it already exists)
2. Logs in and obtains tokens
3. Connects a GitHub repository (creates it if it doesn't exist)
4. Stores Snowflake credentials
5. Creates a data warehouse
6. Sets up CI/CD (opens a PR with workflow files and repository secrets)
7. Bootstraps Terraform state infrastructure (S3 buckets + DynamoDB lock tables)

At the end it prints a refresh token — save it.

## Prerequisites

- The Canary backend stack must be running (`docker compose up` from the repo root)
- A GitHub personal access token with `repo` scope
- Snowflake credentials (RSA private key, base64-encoded)

## Configuration

Non-sensitive config (API URL, account details, repo name, warehouse, bootstrap buckets) lives in `config.py`. Edit it directly for your test account.

Secrets are read from `.env`. Copy the example and fill in your values:

```bash
cp .env.example .env
```

| Variable                        | Description                                              |
|---------------------------------|----------------------------------------------------------|
| `GITHUB_PAT`                    | GitHub personal access token (`repo` scope)              |
| `SNOWFLAKE_ACCOUNT`             | Snowflake account identifier (`org-account` format)      |
| `SNOWFLAKE_USER`                | Snowflake username                                       |
| `SNOWFLAKE_PRIVATE_KEY`         | Base64-encoded RSA private key (PEM)                     |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Passphrase for the private key (if encrypted)         |

To base64-encode your Snowflake PEM key:

```bash
base64 -i rsa_key.p8 | tr -d '\n'
```

## Run via Docker Compose

This is the recommended way. The container joins the `canary_default` network so it can reach the backend by service name.

```bash
# From the repo root, make sure the main stack is up first:
docker compose up -d

# Then from this directory:
cd scripts/init
docker compose run --rm init
```

## Run directly with Python

```bash
cd scripts/init
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python init.py
```

When running directly, `config.py` has `API_BASE_URL = "http://backend:8000/api/v1"`. If the backend is not reachable at that hostname, update `API_BASE_URL` to `http://localhost:8000/api/v1` before running.
