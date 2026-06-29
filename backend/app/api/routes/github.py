from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.project import GitHubRepo, Project
from app.schemas.github import (
    GitHubRepoConnect,
    GitHubRepoOut,
    GitHubCreateRepoRequest,
    GitHubCreateRepoResponse,
)
from app.services.github_service import GitHubService, GitHubError

router = APIRouter(prefix="/github", tags=["github"])


@router.post("/create-repo", response_model=GitHubCreateRepoResponse, status_code=201)
async def create_repo(
    payload: GitHubCreateRepoRequest,
    account_id: str = Depends(get_current_account_id),
):
    svc = GitHubService(
        token=payload.token,
        repo_full_name="",
        branch="",
        api_url=payload.api_url,
    )
    try:
        return await svc.create_repo(
            name=payload.name,
            private=payload.private,
            description=payload.description,
            org=payload.org,
            auto_init=payload.auto_init,
        )
    except GitHubError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/repos", response_model=GitHubRepoOut, status_code=201)
async def connect_repo(
    payload: GitHubRepoConnect,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    svc = GitHubService(
        token=payload.token,
        repo_full_name=payload.repo_full_name,
        branch=payload.branch,
        api_url=payload.api_url,
        base_path=payload.infrastructure_base_path,
    )
    try:
        await svc.validate()
    except GitHubError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    result = await db.execute(
        select(GitHubRepo).where(
            GitHubRepo.account_id == account_id,
            GitHubRepo.project_name == payload.project_name,
        )
    )
    record = result.scalar_one_or_none()

    if record:
        record.repo_full_name = payload.repo_full_name
        record.branch = payload.branch
        record.token = payload.token
        record.api_url = payload.api_url
        record.infrastructure_base_path = payload.infrastructure_base_path
        record.auto_merge = payload.auto_merge
        record.create_cicd = payload.create_cicd
        if payload.dev_state_bucket is not None:
            record.dev_state_bucket = payload.dev_state_bucket
        if payload.dev_state_region is not None:
            record.dev_state_region = payload.dev_state_region
        if payload.dev_state_lock_table is not None:
            record.dev_state_lock_table = payload.dev_state_lock_table
        if payload.prod_state_bucket is not None:
            record.prod_state_bucket = payload.prod_state_bucket
        if payload.prod_state_region is not None:
            record.prod_state_region = payload.prod_state_region
        if payload.prod_state_lock_table is not None:
            record.prod_state_lock_table = payload.prod_state_lock_table
    else:
        record = GitHubRepo(
            account_id=account_id,
            project_name=payload.project_name,
            repo_full_name=payload.repo_full_name,
            branch=payload.branch,
            token=payload.token,
            api_url=payload.api_url,
            infrastructure_base_path=payload.infrastructure_base_path,
            auto_merge=payload.auto_merge,
            create_cicd=payload.create_cicd,
            dev_state_bucket=payload.dev_state_bucket,
            dev_state_region=payload.dev_state_region,
            dev_state_lock_table=payload.dev_state_lock_table,
            prod_state_bucket=payload.prod_state_bucket,
            prod_state_region=payload.prod_state_region,
            prod_state_lock_table=payload.prod_state_lock_table,
        )
        db.add(record)

    await db.flush()

    bootstrapped = payload.skip_bootstrap or bool(payload.dev_state_bucket and payload.prod_state_bucket)

    proj_result = await db.execute(
        select(Project).where(
            Project.account_id == account_id,
            Project.name == payload.project_name,
        )
    )
    project = proj_result.scalar_one_or_none()
    if project:
        project.version_control_created = True
        if bootstrapped:
            project.infrastructure_bootstrapped = True
    else:
        project = Project(
            account_id=account_id,
            name=payload.project_name,
            version_control_created=True,
            infrastructure_bootstrapped=bootstrapped,
        )
        db.add(project)
    await db.flush()

    return record


@router.get("/repos/{project_name}", response_model=GitHubRepoOut)
async def get_repo(
    project_name: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(GitHubRepo).where(
            GitHubRepo.account_id == account_id,
            GitHubRepo.project_name == project_name,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this project")
    return record


@router.delete("/repos/{project_name}", status_code=204)
async def disconnect_repo(
    project_name: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(GitHubRepo).where(
            GitHubRepo.account_id == account_id,
            GitHubRepo.project_name == project_name,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this project")
    await db.delete(record)
