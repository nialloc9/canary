#!/usr/bin/env python3
"""
Initialises a Canary test account via the API.

Reads secrets from .env and non-sensitive config from config.py.
Run directly or via docker-compose.
"""
import base64
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

import config

load_dotenv(Path(__file__).parent / ".env")


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        print(f"ERROR: {key} is not set in .env", file=sys.stderr)
        sys.exit(1)
    return value


def _post(path: str, body: dict, token: str | None = None) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(f"{config.API_BASE_URL}{path}", json=body, headers=headers)


def _post_empty(path: str, token: str) -> requests.Response:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    return requests.post(f"{config.API_BASE_URL}{path}", headers=headers)


def _gh_headers(pat: str) -> dict:
    return {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _ensure_branch(pat: str, branch: str) -> None:
    """Create branch from the repo's default branch if it doesn't already exist."""
    api_url = config.GITHUB["api_url"]
    repo = config.GITHUB["repo_full_name"]
    headers = _gh_headers(pat)

    r = requests.get(f"{api_url}/repos/{repo}", headers=headers)
    if not r.ok:
        return
    default_branch = r.json().get("default_branch", "main")

    sha_r = requests.get(f"{api_url}/repos/{repo}/git/ref/heads/{default_branch}", headers=headers)
    if not sha_r.ok:
        return
    sha = sha_r.json()["object"]["sha"]

    ref_r = requests.post(
        f"{api_url}/repos/{repo}/git/refs",
        headers=headers,
        json={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    if ref_r.ok or ref_r.status_code == 422:
        print(f"   ✓ '{branch}' branch ready")
    else:
        print(f"   WARNING: could not create '{branch}' branch: {ref_r.text}", file=sys.stderr)


class Step:
    def __init__(self, label: str):
        self.label = label

    def __enter__(self):
        print(f"\n▶  {self.label}")
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            print("   ✗ failed")
        return False


def validate_snowflake_key() -> str:
    """Read the base64-encoded private key from env and validate it decodes cleanly."""
    encoded = _require_env("SNOWFLAKE_PRIVATE_KEY_B64")
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except Exception as exc:
        print(f"ERROR: SNOWFLAKE_PRIVATE_KEY_B64 is not valid base64: {exc}", file=sys.stderr)
        sys.exit(1)
    if "BEGIN" not in decoded:
        print("ERROR: decoded SNOWFLAKE_PRIVATE_KEY_B64 does not look like a PEM key", file=sys.stderr)
        sys.exit(1)
    # Return the original encoded value — API stores and receives it base64 encoded
    return encoded


def register() -> None:
    with Step("Registering account"):
        resp = _post("/auth/register", config.ACCOUNT)
        if resp.status_code == 409:
            print("   account already exists — skipping")
            return
        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        user = resp.json()
        print(f"   ✓ created user '{user['username']}' ({user['email']})")


def login() -> tuple[str, str]:
    with Step("Logging in"):
        resp = _post("/auth/login", {
            "username": config.ACCOUNT["username"],
            "password": config.ACCOUNT["password"],
        })
        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        tokens = resp.json()
        print("   ✓ login successful")
        return tokens["access_token"], tokens["refresh_token"]


def connect_github(access_token: str) -> None:
    github_pat = _require_env("GITHUB_PAT")
    connect_payload = {**config.GITHUB, "token": github_pat}
    api_url = config.GITHUB["api_url"]
    repo_full_name = config.GITHUB["repo_full_name"]

    with Step(f"Connecting GitHub repo '{repo_full_name}'"):
        resp = _post("/github/repos", connect_payload, token=access_token)

        if resp.status_code == 422 and "Not Found" in resp.text:
            _, repo_name = repo_full_name.split("/", 1)
            print(f"   repo not found — creating '{repo_full_name}'")
            create_resp = _post(
                "/github/create-repo",
                {
                    "name": repo_name,
                    "token": github_pat,
                    "private": True,
                    "auto_init": True,
                    "api_url": api_url,
                },
                token=access_token,
            )
            if not create_resp.ok:
                print(f"   {create_resp.status_code}: {create_resp.text}", file=sys.stderr)
                sys.exit(1)
            print(f"   ✓ created repo '{create_resp.json()['full_name']}'")
            _ensure_branch(github_pat, config.GITHUB["branch"])
            resp = _post("/github/repos", connect_payload, token=access_token)

        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        print(f"   ✓ connected {data['repo_full_name']} → branch '{data['branch']}'")


def store_snowflake_credentials(access_token: str, private_key_b64: str) -> None:
    with Step("Storing Snowflake credentials"):
        resp = _post(
            "/snowflake/credentials",
            {
                "project_name": config.GITHUB["project_name"],
                "organization_name": _require_env("SNOWFLAKE_ORGANIZATION_NAME"),
                "account_name": _require_env("SNOWFLAKE_ACCOUNT_NAME"),
                "user": _require_env("SNOWFLAKE_USER"),
                "authenticator": os.getenv("SNOWFLAKE_AUTHENTICATOR", "SNOWFLAKE_JWT"),
                "private_key_b64": private_key_b64,
            },
            token=access_token,
        )
        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        print(f"   ✓ stored credentials for project '{data['project_name']}'")


def create_warehouse(access_token: str) -> None:
    project_name = config.GITHUB["project_name"]
    with Step(f"Creating warehouse '{config.WAREHOUSE['name']}' for project '{project_name}'"):
        resp = _post(
            f"/projects/{project_name}/warehouse",
            config.WAREHOUSE,
            token=access_token,
        )
        if resp.status_code == 409:
            print("   warehouse already created — skipping")
            return
        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        print(f"   ✓ warehouse '{data['name']}' ({data['type']}) created")


def create_cicd(access_token: str) -> None:
    project_name = config.GITHUB["project_name"]
    body: dict = {}
    aws_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    if aws_key:
        body["aws_access_key_id"] = aws_key
    if aws_secret:
        body["aws_secret_access_key"] = aws_secret

    with Step(f"Creating CI/CD for project '{project_name}'"):
        resp = _post(f"/projects/{project_name}/cicd", body, token=access_token)
        if resp.status_code == 409:
            print("   CI/CD already created — skipping")
            return
        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        print(f"   ✓ {data['message']}")
        for pr in data["pull_requests"]:
            merged = " (auto-merged)" if data["auto_merged"] else ""
            print(f"   ✓ PR: {pr}{merged}")
        print(f"   ✓ workflows: {', '.join(data['workflows_created'])}")
        print(f"   ✓ secrets:   {', '.join(data['secrets_created'])}")


def bootstrap_infrastructure(access_token: str) -> None:
    project_name = config.GITHUB["project_name"]
    with Step(f"Bootstrapping infrastructure for project '{project_name}'"):
        resp = _post(
            f"/projects/{project_name}/bootstrap",
            config.BOOTSTRAP,
            token=access_token,
        )
        if resp.status_code == 409:
            print("   infrastructure already bootstrapped — skipping")
            return
        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        print(f"   ✓ bootstrap PR opened: {data['pr_url']}")
        print(f"   ✓ dev  state bucket:  {data['dev_state_bucket']} ({data['dev_state_region']})")
        print(f"   ✓ dev  lock table:    {data['dev_state_lock_table']}")
        print(f"   ✓ prod state bucket:  {data['prod_state_bucket']} ({data['prod_state_region']})")
        print(f"   ✓ prod lock table:    {data['prod_state_lock_table']}")


def print_summary(refresh_token: str) -> None:
    print("\n" + "─" * 60)
    print("  Canary initialisation complete")
    print("─" * 60)
    print(f"  API:              {config.API_BASE_URL}")
    print(f"  Username:         {config.ACCOUNT['username']}")
    print(f"  GitHub repo:      {config.GITHUB['repo_full_name']}")
    print(f"  Snowflake org:    {os.getenv('SNOWFLAKE_ORGANIZATION_NAME', '(not set)')}")
    print(f"  Snowflake acct:   {os.getenv('SNOWFLAKE_ACCOUNT_NAME', '(not set)')}")
    print(f"  Snowflake user:   {os.getenv('SNOWFLAKE_USER', '(not set)')}")
    print(f"\n  Refresh token (store this):\n")
    print(f"  {refresh_token}")
    print("─" * 60 + "\n")


def main() -> None:
    print("Canary — test account initialisation")
    print(f"Target: {config.API_BASE_URL}")

    with Step("Validating Snowflake private key"):
        private_key_b64 = validate_snowflake_key()
        print("   ✓ valid base64-encoded PEM key")

    register()
    access_token, refresh_token = login()
    connect_github(access_token)
    store_snowflake_credentials(access_token, private_key_b64)
    create_warehouse(access_token)
    create_cicd(access_token)
    bootstrap_infrastructure(access_token)
    print_summary(refresh_token)


if __name__ == "__main__":
    main()
