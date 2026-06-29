API_BASE_URL = "http://backend:8000/api/v1"

ACCOUNT = {
    "account_name": "Canary Test 1",
    "account_domain": "canary.dev",
    "username": "canary-test-1",
    "email": "canary-test-1@canary.dev",
    "password": "canary-test-1!",
}

GITHUB = {
    "project_name": "canary-test-1",
    "repo_full_name": "nialloc9/canary-test-1",
    "branch": "develop",
    "infrastructure_base_path": "infrastructure",
    "api_url": "https://api.github.com",
}

WAREHOUSE = {
    "name": "canary_wh",
    "type": "snowflake",
}

BOOTSTRAP = {
    "dev_state_bucket": "canary-test-1-dev-terraform-state",
    "dev_state_region": "eu-west-1",
    "dev_state_lock_table": "canary-test-1-dev-terraform-lock",
    "prod_state_bucket": "canary-test-1-prod-terraform-state",
    "prod_state_region": "eu-west-1",
    "prod_state_lock_table": "canary-test-1-prod-terraform-lock",
}
