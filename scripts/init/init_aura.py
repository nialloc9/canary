#!/usr/bin/env python3
"""
Connects the automata-tech/aura-infra repo to Canary.

Steps:
  1. Login (account already exists from init.py)
  2. Connect GitHub repo (no CI/CD; marks infra bootstrapped via placeholder state config)
  3. Store Snowflake credentials for the aura-infra project
  4. Create warehouse record

Skips CI/CD (repo uses CircleCI) and bootstrap (state backend already configured in repo).
Landing zone creation is done via the chat API after this script.
"""
import base64
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

import config_aura as config

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
    encoded = _require_env("SNOWFLAKE_PRIVATE_KEY_B64")
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except Exception as exc:
        print(f"ERROR: SNOWFLAKE_PRIVATE_KEY_B64 is not valid base64: {exc}", file=sys.stderr)
        sys.exit(1)
    if "BEGIN" not in decoded:
        print("ERROR: decoded SNOWFLAKE_PRIVATE_KEY_B64 does not look like a PEM key", file=sys.stderr)
        sys.exit(1)
    return encoded


def login() -> str:
    with Step("Logging in"):
        resp = _post("/auth/login", {
            "username": config.ACCOUNT["username"],
            "password": config.ACCOUNT["password"],
        })
        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        print("   ✓ login successful")
        return resp.json()["access_token"]


def connect_github(access_token: str) -> None:
    github_pat = _require_env("GITHUB_PAT")
    connect_payload = {
        **config.GITHUB,
        "token": github_pat,
    }
    repo_full_name = config.GITHUB["repo_full_name"]

    with Step(f"Connecting GitHub repo '{repo_full_name}'"):
        resp = _post("/github/repos", connect_payload, token=access_token)
        if not resp.ok:
            print(f"   {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()
        print(f"   ✓ connected {data['repo_full_name']} → branch '{data['branch']}'")
        print(f"   ✓ infrastructure_base_path: '{data['infrastructure_base_path'] or '(repo root)'}'")
        print(f"   ✓ create_cicd: {data['create_cicd']}")


def store_snowflake_credentials(access_token: str, private_key_b64: str) -> None:
    project_name = config.GITHUB["project_name"]
    with Step(f"Storing Snowflake credentials for project '{project_name}'"):
        resp = _post(
            "/snowflake/credentials",
            {
                "project_name": project_name,
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
        print(f"   ✓ stored credentials for '{data['project_name']}'")


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


def main() -> None:
    print("Canary — aura-infra project setup")
    print(f"Target: {config.API_BASE_URL}")
    print(f"Repo:   {config.GITHUB['repo_full_name']}")

    with Step("Validating Snowflake private key"):
        private_key_b64 = validate_snowflake_key()
        print("   ✓ valid base64-encoded PEM key")

    access_token = login()
    connect_github(access_token)
    store_snowflake_credentials(access_token, private_key_b64)
    create_warehouse(access_token)

    print("\n" + "─" * 60)
    print("  aura-infra project ready")
    print("─" * 60)
    print(f"  API:          {config.API_BASE_URL}")
    print(f"  Project:      {config.GITHUB['project_name']}")
    print(f"  Repo:         {config.GITHUB['repo_full_name']}")
    print(f"  Branch:       {config.GITHUB['branch']}")
    print(f"  CI/CD:        skipped (repo uses CircleCI)")
    print(f"  Bootstrap:    skipped (state backend already in repo)")
    print()
    print("  Next: use the chat API to create the buttercup landing zone:")
    print("    POST /api/v1/chat")
    print("    { \"message\": \"Create a buttercup landing zone for project aura-infra\" }")
    print("─" * 60 + "\n")


if __name__ == "__main__":
    main()
