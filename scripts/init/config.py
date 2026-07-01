import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() == "true"


API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000/api/v1")

ACCOUNT = {
    "account_name": os.getenv("ACCOUNT_NAME", ""),
    "account_domain": os.getenv("ACCOUNT_DOMAIN", ""),
    "username": os.getenv("ACCOUNT_USERNAME", ""),
    "email": os.getenv("ACCOUNT_EMAIL", ""),
    "password": os.getenv("ACCOUNT_PASSWORD", ""),
}

GITHUB = {
    "project_name": os.getenv("GITHUB_PROJECT_NAME", ""),
    "repo_full_name": os.getenv("GITHUB_REPO_FULL_NAME", ""),
    "branch": os.getenv("GITHUB_BRANCH", "develop"),
    "infrastructure_base_path": os.getenv("GITHUB_INFRA_BASE_PATH", "infrastructure"),
    "api_url": os.getenv("GITHUB_API_URL", "https://api.github.com"),
    "create_cicd": _bool("GITHUB_CREATE_CICD", True),
    "auto_merge": _bool("GITHUB_AUTO_MERGE", False),
    "skip_bootstrap": _bool("GITHUB_SKIP_BOOTSTRAP", False),
    "skip_module_import": _bool("GITHUB_SKIP_MODULE_IMPORT", False),
}

WAREHOUSE = {
    "name": os.getenv("WAREHOUSE_NAME", ""),
    "type": os.getenv("WAREHOUSE_TYPE", "snowflake"),
}

BOOTSTRAP = {
    "dev_state_bucket": os.getenv("BOOTSTRAP_DEV_STATE_BUCKET", ""),
    "dev_state_region": os.getenv("BOOTSTRAP_DEV_STATE_REGION", "eu-west-1"),
    "dev_state_lock_table": os.getenv("BOOTSTRAP_DEV_STATE_LOCK_TABLE", ""),
    "prod_state_bucket": os.getenv("BOOTSTRAP_PROD_STATE_BUCKET", ""),
    "prod_state_region": os.getenv("BOOTSTRAP_PROD_STATE_REGION", "eu-west-1"),
    "prod_state_lock_table": os.getenv("BOOTSTRAP_PROD_STATE_LOCK_TABLE", ""),
}
