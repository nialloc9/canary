from pydantic import BaseModel, field_validator
from datetime import datetime


class DbtRepoConnect(BaseModel):
    """repo_full_name is always required — it identifies which repo the call
    is about. Every other field is optional: omitting one means "keep the
    existing value" when updating, or falls back to a sensible default when
    connecting for the first time."""

    repo_full_name: str
    branch: str | None = None
    token: str | None = None
    api_url: str | None = None
    dbt_base_path: str | None = None
    cicd_provider: str | None = None

    @field_validator("repo_full_name")
    @classmethod
    def validate_repo_full_name(cls, v: str) -> str:
        if "/" not in v or len(v.split("/")) != 2:
            raise ValueError("repo_full_name must be in 'owner/repo' format")
        return v

    @field_validator("cicd_provider")
    @classmethod
    def validate_cicd_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in ("github_actions", "circleci"):
            raise ValueError("cicd_provider must be 'github_actions' or 'circleci'")
        return v

    @field_validator("dbt_base_path")
    @classmethod
    def normalise_base_path(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip("/")
        return stripped if stripped else "."


class DbtRepoOut(BaseModel):
    id: str
    repo_full_name: str
    branch: str
    api_url: str
    dbt_base_path: str
    cicd_provider: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
