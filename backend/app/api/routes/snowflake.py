import base64

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.project import SnowflakeCredentials
from app.schemas.snowflake import SnowflakeCredentialsConnect, SnowflakeCredentialsOut

router = APIRouter(prefix="/snowflake", tags=["snowflake"])


def decode_private_key(encoded: str) -> str:
    """Decode the stored base64 private key to PEM string at point of use."""
    return base64.b64decode(encoded).decode("utf-8")


@router.post("/credentials", response_model=SnowflakeCredentialsOut, status_code=201)
async def connect_credentials(
    payload: SnowflakeCredentialsConnect,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(SnowflakeCredentials).where(
            SnowflakeCredentials.account_id == account_id,
            SnowflakeCredentials.project_name == payload.project_name,
        )
    )
    record = result.scalar_one_or_none()

    if record:
        record.organization_name = payload.organization_name
        record.account_name = payload.account_name
        record.user = payload.user
        record.authenticator = payload.authenticator
        record.private_key_b64 = payload.private_key_b64
    else:
        record = SnowflakeCredentials(
            account_id=account_id,
            project_name=payload.project_name,
            organization_name=payload.organization_name,
            account_name=payload.account_name,
            user=payload.user,
            authenticator=payload.authenticator,
            private_key_b64=payload.private_key_b64,
        )
        db.add(record)

    await db.flush()
    return record


@router.get("/credentials/{project_name}", response_model=SnowflakeCredentialsOut)
async def get_credentials(
    project_name: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(SnowflakeCredentials).where(
            SnowflakeCredentials.account_id == account_id,
            SnowflakeCredentials.project_name == project_name,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No Snowflake credentials for this project")
    return record


@router.delete("/credentials/{project_name}", status_code=204)
async def delete_credentials(
    project_name: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(SnowflakeCredentials).where(
            SnowflakeCredentials.account_id == account_id,
            SnowflakeCredentials.project_name == project_name,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No Snowflake credentials for this project")
    await db.delete(record)
