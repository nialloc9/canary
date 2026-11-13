from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
from app.models.stack import Stack
from app.services.topology_service import get_stack_topology


class CheckDeployedInfrastructureTool(BaseTool):
    """Answers questions about what's actually deployed, by reading the real
    Terragrunt config from GitHub (the same source the topology diagram uses)
    rather than trusting the app's own records of what was asked for."""

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "check_deployed_infrastructure"

    @property
    def description(self) -> str:
        return (
            "Check what infrastructure has actually been deployed, by reading the generated "
            "Terragrunt config directly from GitHub. Use this to answer questions like "
            "'Have I created a landing zone for foxglove?', 'What's deployed to prod?', or "
            "'Is the snowpipe set up for cress yet?'. If the user doesn't name a stack, use "
            "whichever stack is currently in focus; if none is in focus or they ask across "
            "everything, check every stack on the account."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "stack_name": {
                    "type": "string",
                    "description": "Stack to check (e.g. dev, prod). Omit to check every stack on the account.",
                },
                "landing_zone_name": {
                    "type": "string",
                    "description": "If asking about one specific landing zone (e.g. 'foxglove'), pass its name "
                    "for a direct yes/no answer. Omit to list everything deployed instead.",
                },
            },
        }

    async def execute(self, stack_name: str | None = None, landing_zone_name: str | None = None) -> str:
        if stack_name and stack_name.lower() != "all":
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
            topology = await get_stack_topology(self._db, self._account_id, stack, force_refresh=False)

            if not topology.connected:
                lines.append(f"{stack.name}: no GitHub repo connected yet — nothing to check.")
                continue
            if topology.error:
                lines.append(f"{stack.name}: couldn't read from GitHub ({topology.error}).")
                continue

            landing_zones = sorted({n.landing_zone for n in topology.nodes})

            if landing_zone_name:
                found = landing_zone_name.lower() in [lz.lower() for lz in landing_zones]
                if found:
                    components = sorted(
                        n.label for n in topology.nodes if n.landing_zone.lower() == landing_zone_name.lower()
                    )
                    lines.append(f"{stack.name}: yes — '{landing_zone_name}' is deployed ({', '.join(components)}).")
                else:
                    near_misses = [
                        s for s in topology.skipped if s.dir.lower().startswith(landing_zone_name.lower())
                    ]
                    if near_misses:
                        details = "; ".join(f"'{s.dir}': {s.reason}" for s in near_misses)
                        lines.append(
                            f"{stack.name}: no — but found matching director{'ies' if len(near_misses) > 1 else 'y'} "
                            f"that couldn't be recognized ({details})."
                        )
                    else:
                        lines.append(f"{stack.name}: no — '{landing_zone_name}' is not deployed.")
            elif landing_zones:
                lines.append(f"{stack.name}: {', '.join(landing_zones)}")
                if topology.skipped:
                    lines.append(
                        f"  (also found {len(topology.skipped)} unrecognized director"
                        f"{'ies' if len(topology.skipped) > 1 else 'y'} — ask about a specific name for details)"
                    )
            else:
                lines.append(f"{stack.name}: nothing deployed yet.")

        return "\n".join(lines)

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
