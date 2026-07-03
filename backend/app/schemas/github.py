from pydantic import BaseModel, field_validator
from datetime import datetime


class GitHubRepoConnect(BaseModel):
    """repo_full_name is always required — it identifies which repo the call
    is about. Every other field is optional: omitting one means "keep the
    existing value" when updating, or falls back to a sensible default when
    connecting for the first time. See connect_repo() for how these resolve."""

    repo_full_name: str
    branch: str | None = None
    token: str | None = None
    api_url: str | None = None
    infrastructure_base_path: str | None = None
    auto_merge: bool | None = None
    create_cicd: bool | None = None
    skip_bootstrap: bool | None = None
    skip_module_import: bool | None = None

    @field_validator("repo_full_name")
    @classmethod
    def validate_repo_full_name(cls, v: str) -> str:
        if "/" not in v or len(v.split("/")) != 2:
            raise ValueError("repo_full_name must be in 'owner/repo' format")
        return v

    @field_validator("infrastructure_base_path")
    @classmethod
    def normalise_base_path(cls, v: str | None) -> str | None:
        return v.strip("/") if v is not None else v


class GitHubRepoOut(BaseModel):
    id: str
    project_name: str
    repo_full_name: str
    branch: str
    api_url: str
    infrastructure_base_path: str
    auto_merge: bool
    create_cicd: bool
    skip_bootstrap: bool
    skip_module_import: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GitHubCreateRepoRequest(BaseModel):
    name: str
    token: str
    private: bool = True
    description: str = ""
    org: str | None = None
    auto_init: bool = True
    api_url: str = "https://api.github.com"


class GitHubCreateRepoResponse(BaseModel):
    full_name: str
    html_url: str
    clone_url: str
    default_branch: str
    private: bool


class GitHubCommitResult(BaseModel):
    project_name: str
    repo_full_name: str
    branch: str
    commit_url: str
    files_committed: int
