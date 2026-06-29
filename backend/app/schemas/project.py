from pydantic import BaseModel
from datetime import datetime


class ProjectOut(BaseModel):
    id: str
    name: str
    version_control_created: bool
    cicd_created: bool
    warehouse_created: bool
    infrastructure_bootstrapped: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectWarehouseRequest(BaseModel):
    name: str
    type: str = "snowflake"


class ProjectWarehouseResponse(BaseModel):
    id: str
    name: str
    type: str
    warehouse_credentials_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectCiCdRequest(BaseModel):
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None


class ProjectCiCdResponse(BaseModel):
    message: str
    cicd_created: bool
    pull_requests: list[str]
    auto_merged: bool
    secrets_created: list[str]
    workflows_created: list[str]


class ProjectBootstrapRequest(BaseModel):
    dev_state_bucket: str | None = None
    dev_state_region: str | None = None
    dev_state_lock_table: str | None = None
    prod_state_bucket: str | None = None
    prod_state_region: str | None = None
    prod_state_lock_table: str | None = None


class ProjectBootstrapResponse(BaseModel):
    pr_url: str
    dev_state_bucket: str
    dev_state_region: str
    dev_state_lock_table: str
    prod_state_bucket: str
    prod_state_region: str
    prod_state_lock_table: str
