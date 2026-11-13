"""Reads secrets that Terraform wrote into a stack's own AWS Secrets Manager
(e.g. S3 access keys for a landing zone) — authenticated with that stack's own
cloud credentials, since Canary doesn't hold any separate AWS identity."""
import asyncio
import json

import boto3
from botocore.exceptions import ClientError

from app.models.stack import Stack


def access_keys_secret_name(project_name: str, stack_name: str, landing_zone_name: str) -> str:
    """Must match the naming convention used by templates.lz() /
    modules/aws/landing-zone: project_name/stack_name/secret_name."""
    return f"{project_name}/{stack_name}/{landing_zone_name}-s3-access-keys"


def _get_secret_json_sync(stack: Stack, secret_name: str) -> dict | None:
    if not stack.cloud_access_key_id or not stack.cloud_secret_access_key:
        return None

    client = boto3.client(
        "secretsmanager",
        aws_access_key_id=stack.cloud_access_key_id,
        aws_secret_access_key=stack.cloud_secret_access_key,
        region_name=stack.cloud_region or "us-east-1",
    )
    try:
        resp = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            return None
        raise
    return json.loads(resp["SecretString"])


async def get_landing_zone_access_keys(
    stack: Stack, project_name: str, landing_zone_name: str
) -> dict | None:
    """Returns {"access_key_id": ..., "secret_access_key": ...} or None if the
    secret doesn't exist yet (landing zone not applied) or the stack has no
    cloud credentials configured."""
    secret_name = access_keys_secret_name(project_name, stack.name, landing_zone_name)
    return await asyncio.to_thread(_get_secret_json_sync, stack, secret_name)
