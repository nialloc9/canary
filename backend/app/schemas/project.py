from pydantic import BaseModel
from datetime import datetime


class ProjectOut(BaseModel):
    id: str
    name: str
    version_control_created: bool
    cicd_created: bool
    infrastructure_bootstrapped: bool
    default_retention_policy: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectSettingsUpdate(BaseModel):
    default_retention_policy: str | None = None


class ProjectCiCdResponse(BaseModel):
    message: str
    cicd_created: bool
    pull_requests: list[str]
    auto_merged: bool
    secrets_created: list[str]
    workflows_created: list[str]


class StackStateOverride(BaseModel):
    bucket: str | None = None
    region: str | None = None
    lock_table: str | None = None


class StackStateOut(BaseModel):
    name: str
    bucket: str
    region: str
    lock_table: str


class ProjectBootstrapRequest(BaseModel):
    overrides: dict[str, StackStateOverride] | None = None


class ProjectBootstrapResponse(BaseModel):
    pr_url: str | None
    stacks: list[StackStateOut]
