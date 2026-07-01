from datetime import datetime
from pydantic import BaseModel


class WarehouseUpdate(BaseModel):
    type: str | None = None
    organization_name: str | None = None
    account_name: str | None = None
    user: str | None = None
    authenticator: str | None = None
    private_key_b64: str | None = None
    database: str | None = None
    schema_: str | None = None
    warehouse: str | None = None
    role: str | None = None


class WarehouseOut(BaseModel):
    type: str
    organization_name: str
    account_name: str
    user: str
    authenticator: str
    private_key_b64: str | None
    database: str | None
    schema_: str | None
    warehouse: str | None
    role: str | None


class CloudUpdate(BaseModel):
    provider: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    region: str | None = None


class CloudOut(BaseModel):
    provider: str
    access_key_id: str
    secret_access_key: str | None
    region: str


class StackCreate(BaseModel):
    name: str
    branch: str | None = None
    warehouse: WarehouseUpdate | None = None
    cloud: CloudUpdate | None = None


class StackUpdate(BaseModel):
    name: str | None = None
    branch: str | None = None
    warehouse: WarehouseUpdate | None = None
    cloud: CloudUpdate | None = None


class StackOut(BaseModel):
    id: str
    name: str
    branch: str
    sort_order: int
    is_default: bool
    warehouse: WarehouseOut
    cloud: CloudOut
    created_at: datetime
    updated_at: datetime


class ReorderRequest(BaseModel):
    stack_ids: list[str]


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
