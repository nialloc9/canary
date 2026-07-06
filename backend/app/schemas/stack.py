from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


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
    verify_before_pr: bool | None = None
    verify_max_attempts: int | None = Field(default=None, ge=1, le=10)
    module_version: str | None = None
    warehouse: WarehouseUpdate | None = None
    cloud: CloudUpdate | None = None


class StackUpdate(BaseModel):
    name: str | None = None
    branch: str | None = None
    verify_before_pr: bool | None = None
    verify_max_attempts: int | None = Field(default=None, ge=1, le=10)
    module_version: str | None = None
    warehouse: WarehouseUpdate | None = None
    cloud: CloudUpdate | None = None


class StackOut(BaseModel):
    id: str
    name: str
    branch: str
    verify_before_pr: bool
    verify_max_attempts: int
    module_version: str
    sort_order: int
    is_default: bool
    warehouse: WarehouseOut
    cloud: CloudOut
    created_at: datetime
    updated_at: datetime


class ModuleVersionOut(BaseModel):
    version: str
    released_at: str
    notes: str


class ModuleRefreshResponse(BaseModel):
    pr_url: str | None
    files_removed: int
    files_added: int
    message: str | None = None


class ReorderRequest(BaseModel):
    stack_ids: list[str]


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str


class ReleaseRequest(BaseModel):
    target: Literal["prod", "develop"]
    resolutions: dict[str, Literal["ours", "theirs"]] | None = None


class TopologyNodeOut(BaseModel):
    id: str
    landing_zone: str
    type: str
    label: str
    fields: dict[str, str]


class TopologyEdgeOut(BaseModel):
    source: str
    target: str


class TopologySkippedOut(BaseModel):
    dir: str
    reason: str


class TopologyOut(BaseModel):
    nodes: list[TopologyNodeOut]
    edges: list[TopologyEdgeOut]
    fetched_at: datetime
    connected: bool
    error: str | None = None
    skipped: list[TopologySkippedOut] = []


class ConflictOut(BaseModel):
    path: str
    ours: str | None
    theirs: str | None


class ReleaseResponse(BaseModel):
    pr_urls: list[str] = []
    branch: str | None = None
    conflicts: list[ConflictOut] | None = None
    source_branch: str | None = None
    target_branch: str | None = None


class AccessKeysOut(BaseModel):
    access_key_id: str
    secret_access_key: str
