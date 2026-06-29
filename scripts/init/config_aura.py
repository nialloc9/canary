API_BASE_URL = "http://backend:8000/api/v1"

ACCOUNT = {
    "account_name": "Canary Test 1",
    "account_domain": "canary.dev",
    "username": "canary-test-1",
    "email": "canary-test-1@canary.dev",
    "password": "canary-test-1!",
}

GITHUB = {
    "project_name": "aura-infra",
    "repo_full_name": "automata-tech/aura-infra",
    "branch": "develop",
    "infrastructure_base_path": "",
    "api_url": "https://api.github.com",
    "create_cicd": False,
    "auto_merge": True,
    "skip_bootstrap": True,  # repo already has remote state configured
}

WAREHOUSE = {
    "name": "aura_wh",
    "type": "snowflake",
}
