from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.user import Account, AccountWarehouseConfig, AccountCloudConfig

router = APIRouter(prefix="/org", tags=["org"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrgSettings(BaseModel):
    name: str
    domain: str


class WarehouseConfigIn(BaseModel):
    type: str = "snowflake"
    account: str
    username: str
    authenticator: str = "SNOWFLAKE"
    password: str | None = None
    privateKeyB64: str | None = None
    database: str | None = None
    sf_schema: str | None = Field(default=None, validation_alias="schema")
    warehouse: str | None = None
    role: str | None = None

    model_config = {"populate_by_name": True}


class CloudConfig(BaseModel):
    provider: str = "aws"
    accessKeyId: str = ""
    secretAccessKey: str | None = None
    region: str = "us-east-1"


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str


def _warehouse_dict(record: AccountWarehouseConfig) -> dict:
    return {
        "type": record.type,
        "account": record.sf_account or "",
        "username": record.sf_username or "",
        "authenticator": record.sf_authenticator,
        "password": "••••••••" if record.sf_password else None,
        "privateKeyB64": "••••••••" if record.sf_private_key_b64 else None,
        "database": record.sf_database or "",
        "schema": record.sf_schema or "",
        "warehouse": record.sf_warehouse or "",
        "role": record.sf_role or "",
    }


def _cloud_dict(record: AccountCloudConfig) -> dict:
    return {
        "provider": record.provider,
        "accessKeyId": record.access_key_id or "",
        "secretAccessKey": "••••••••" if record.secret_access_key else None,
        "region": record.region or "us-east-1",
    }


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


# ── Warehouse ─────────────────────────────────────────────────────────────────

@router.get("/warehouse")
async def get_warehouse(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
) -> dict:
    result = await db.execute(
        select(AccountWarehouseConfig).where(AccountWarehouseConfig.account_id == account_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        return {"type": "snowflake", "account": "", "username": "", "authenticator": "SNOWFLAKE",
                "password": None, "privateKeyB64": None,
                "database": "", "schema": "", "warehouse": "", "role": ""}
    return _warehouse_dict(record)


@router.put("/warehouse")
async def update_warehouse(
    payload: WarehouseConfigIn,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
) -> dict:
    result = await db.execute(
        select(AccountWarehouseConfig).where(AccountWarehouseConfig.account_id == account_id)
    )
    record = result.scalar_one_or_none()

    def _apply(record: AccountWarehouseConfig) -> None:
        record.type = payload.type
        record.sf_account = payload.account
        record.sf_username = payload.username
        record.sf_authenticator = payload.authenticator
        record.sf_database = payload.database
        record.sf_schema = payload.sf_schema
        record.sf_warehouse = payload.warehouse
        record.sf_role = payload.role
        if payload.password and not payload.password.startswith("••"):
            record.sf_password = payload.password
        if payload.privateKeyB64 and not payload.privateKeyB64.startswith("••"):
            record.sf_private_key_b64 = payload.privateKeyB64

    if record:
        _apply(record)
    else:
        record = AccountWarehouseConfig(account_id=account_id, type=payload.type)
        db.add(record)
        _apply(record)
    await db.flush()
    return _warehouse_dict(record)


@router.post("/warehouse/test", response_model=ConnectionTestResult)
async def test_warehouse(payload: WarehouseConfigIn) -> ConnectionTestResult:
    try:
        import snowflake.connector  # type: ignore
        import base64, tempfile, os

        kwargs: dict = {
            "account": payload.account,
            "user": payload.username,
        }
        if payload.database:
            kwargs["database"] = payload.database
        if payload.sf_schema:
            kwargs["schema"] = payload.sf_schema
        if payload.warehouse:
            kwargs["warehouse"] = payload.warehouse
        if payload.role:
            kwargs["role"] = payload.role

        if payload.authenticator == "SNOWFLAKE_JWT" and payload.privateKeyB64:
            pem = base64.b64decode(payload.privateKeyB64)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".p8") as f:
                f.write(pem)
                key_path = f.name
            try:
                kwargs["authenticator"] = "snowflake_jwt"
                kwargs["private_key_file"] = key_path
                conn = snowflake.connector.connect(**kwargs)
                conn.close()
            finally:
                os.unlink(key_path)
        else:
            kwargs["password"] = payload.password
            conn = snowflake.connector.connect(**kwargs)
            conn.close()

        return ConnectionTestResult(ok=True, message="Connection successful")
    except ImportError:
        return ConnectionTestResult(ok=False, message="snowflake-connector-python not installed")
    except Exception as exc:
        return ConnectionTestResult(ok=False, message=str(exc))


# ── Cloud ─────────────────────────────────────────────────────────────────────

@router.get("/cloud")
async def get_cloud(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
) -> dict:
    result = await db.execute(
        select(AccountCloudConfig).where(AccountCloudConfig.account_id == account_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        return {"provider": "aws", "accessKeyId": "", "secretAccessKey": None, "region": "us-east-1"}
    return _cloud_dict(record)


@router.put("/cloud")
async def update_cloud(
    payload: CloudConfig,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
) -> dict:
    result = await db.execute(
        select(AccountCloudConfig).where(AccountCloudConfig.account_id == account_id)
    )
    record = result.scalar_one_or_none()
    if record:
        record.provider = payload.provider
        record.access_key_id = payload.accessKeyId
        if payload.secretAccessKey and not payload.secretAccessKey.startswith("••"):
            record.secret_access_key = payload.secretAccessKey
        record.region = payload.region
    else:
        record = AccountCloudConfig(
            account_id=account_id,
            provider=payload.provider,
            access_key_id=payload.accessKeyId,
            secret_access_key=payload.secretAccessKey if payload.secretAccessKey and not payload.secretAccessKey.startswith("••") else None,
            region=payload.region,
        )
        db.add(record)
    await db.flush()
    return _cloud_dict(record)
