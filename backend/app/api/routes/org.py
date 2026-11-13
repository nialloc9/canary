from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.user import Account

router = APIRouter(prefix="/org", tags=["org"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrgSettings(BaseModel):
    name: str
    domain: str


# ── Org settings ──────────────────────────────────────────────────────────────

@router.get("/settings", response_model=OrgSettings)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return OrgSettings(name=account.name, domain=account.domain)


@router.put("/settings", response_model=OrgSettings)
async def update_settings(
    payload: OrgSettings,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.name = payload.name
    account.domain = payload.domain.lower().strip()
    await db.flush()
    return OrgSettings(name=account.name, domain=account.domain)
