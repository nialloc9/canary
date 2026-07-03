from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.stack import Stack


async def get_dev_prod_branches(account_id: str, db: AsyncSession) -> tuple[str, str]:
    """Branches the account's "dev" and "prod" stacks track — defaults to
    develop/main if those stacks somehow don't exist yet (they're auto-seeded
    on every account, so this is just a defensive fallback)."""
    result = await db.execute(
        select(Stack.name, Stack.branch).where(Stack.account_id == account_id, Stack.name.in_(["dev", "prod"]))
    )
    branches = dict(result.all())
    return branches.get("dev", "develop"), branches.get("prod", "main")
