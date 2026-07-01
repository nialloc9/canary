from pydantic import BaseModel, field_validator
from datetime import datetime


class GitHubRepoConnect(BaseModel):
    project_name: str
    repo_full_name: str
    branch: str = "develop"
    token: str
    api_url: str = "https://api.github.com"
    infrastructure_base_path: str = "infrastructure"
    auto_merge: bool = False
    create_cicd: bool = True
    skip_bootstrap: bool = False
    skip_module_import: bool = False
    dev_state_bucket: str | None = None
    dev_state_region: str | None = None
    dev_state_lock_table: str | None = None
    prod_state_bucket: str | None = None
    prod_state_region: str | None = None
    prod_state_lock_table: str | None = None

    @field_validator("repo_full_name")
    @classmethod
    def validate_repo_full_name(cls, v: str) -> str:
        if "/" not in v or len(v.split("/")) != 2:
            raise ValueError("repo_full_name must be in 'owner/repo' format")
        return v

    @field_validator("infrastructure_base_path")
    @classmethod
    def normalise_base_path(cls, v: str) -> str:
        return v.strip("/")


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
    dev_state_bucket: str | None
    dev_state_region: str | None
    dev_state_lock_table: str | None
    prod_state_bucket: str | None
    prod_state_region: str | None
    prod_state_lock_table: str | None
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
