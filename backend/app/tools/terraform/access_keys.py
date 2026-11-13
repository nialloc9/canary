from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
from app.models.stack import Stack
from app.models.project import Project
from app.services.aws_secrets_service import get_landing_zone_access_keys


class GetLandingZoneAccessKeysTool(BaseTool):
    """Retrieves the S3 access keys for a landing zone from AWS Secrets Manager
    (never from Terraform state or our own DB — Canary never stores the raw
    key values itself)."""

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "get_landing_zone_access_keys"

    @property
    def description(self) -> str:
        return (
            "Fetch the S3 access key ID and secret access key for a landing zone, straight from "
            "AWS Secrets Manager. Only works once the landing zone's PR has been merged and applied "
            "— if it hasn't, say so and suggest asking again later. Use this whenever the user asks "
            "for the access keys/credentials for a landing zone's bucket."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "landing_zone_name": {
                    "type": "string",
                    "description": "Landing zone name (e.g. loveable, foxglove)",
                },
                "stack_name": {
                    "type": "string",
                    "description": "Stack to check (e.g. dev, prod). Omit to check every stack on the account.",
                },
            },
            "required": ["landing_zone_name"],
        }

    async def execute(self, landing_zone_name: str, stack_name: str | None = None) -> str:
        project = await self._get_project()
        if not project:
            return "No project found for this account."

        if stack_name:
            stack = await self._get_stack(stack_name)
            if not stack:
                return f"No stack named '{stack_name}' found for this account."
            stacks = [stack]
        else:
            stacks = await self._get_all_stacks()
            if not stacks:
                return "No stacks configured for this account."

        lines = []
        for stack in stacks:
            keys = await get_landing_zone_access_keys(stack, project.name, landing_zone_name)
            if keys is None:
                lines.append(
                    f"{stack.name}: not available yet — either '{landing_zone_name}' doesn't have "
                    f"access keys enabled, hasn't been applied yet, or this stack has no cloud "
                    f"credentials configured."
                )
            else:
                lines.append(
                    f"{stack.name}:\n"
                    f"  Access key ID:     {keys['access_key_id']}\n"
                    f"  Secret access key: {keys['secret_access_key']}"
                )

        return "\n".join(lines)

    async def _get_project(self) -> "Project | None":
        result = await self._db.execute(select(Project).where(Project.account_id == self._account_id))
        return result.scalar_one_or_none()

    async def _get_stack(self, name: str) -> Stack | None:
        result = await self._db.execute(
            select(Stack).where(Stack.account_id == self._account_id, Stack.name == name)
        )
        return result.scalar_one_or_none()

    async def _get_all_stacks(self) -> list[Stack]:
        result = await self._db.execute(
            select(Stack).where(Stack.account_id == self._account_id).order_by(Stack.sort_order)
        )
        return list(result.scalars().all())
