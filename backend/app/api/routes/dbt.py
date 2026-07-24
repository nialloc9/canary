from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.project import DbtRepo
from app.schemas.dbt import DbtRepoConnect, DbtRepoOut
from app.services.github_service import GitHubService, GitHubError

router = APIRouter(prefix="/dbt", tags=["dbt"])


@router.post("/repo", response_model=DbtRepoOut, status_code=201)
async def connect_repo(
    payload: DbtRepoConnect,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(DbtRepo).where(DbtRepo.account_id == account_id))
    record = result.scalar_one_or_none()

    # Same "resolve the real end state before validating" approach as
    # connect_repo() in github.py — every field but repo_full_name is
    # optional, falling back to the existing value (if updating) or a
    # default (if connecting for the first time).
    def _resolve(payload_value, db_attr: str, default):
        if payload_value is not None:
            return payload_value
        if record is not None:
            return getattr(record, db_attr)
        return default

    token_given = payload.token and not payload.token.startswith("••")
    effective_token = payload.token if token_given else _resolve(None, "token", None)
    if effective_token is None:
        raise HTTPException(status_code=422, detail="A GitHub token is required to connect a new repository")

    branch = _resolve(payload.branch, "branch", "main")
    api_url = _resolve(payload.api_url, "api_url", "https://api.github.com")
    dbt_base_path = _resolve(payload.dbt_base_path, "dbt_base_path", ".")
    cicd_provider = _resolve(payload.cicd_provider, "cicd_provider", "github_actions")

    svc = GitHubService(
        token=effective_token,
        repo_full_name=payload.repo_full_name,
        branch=branch,
        api_url=api_url,
    )
    try:
        await svc.validate()
        if not await svc.branch_exists(branch):
            raise HTTPException(status_code=422, detail=f"Branch '{branch}' does not exist in {payload.repo_full_name}")
    except GitHubError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if record:
        record.repo_full_name = payload.repo_full_name
        record.branch = branch
        record.token = effective_token
        record.api_url = api_url
        record.dbt_base_path = dbt_base_path
        record.cicd_provider = cicd_provider
    else:
        record = DbtRepo(
            account_id=account_id,
            repo_full_name=payload.repo_full_name,
            branch=branch,
            token=effective_token,
            api_url=api_url,
            dbt_base_path=dbt_base_path,
            cicd_provider=cicd_provider,
        )
        db.add(record)

    await db.flush()
    return record


@router.get("/repo", response_model=DbtRepoOut)
async def get_repo(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(DbtRepo).where(DbtRepo.account_id == account_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No dbt repo connected for this account")
    return record


@router.delete("/repo", status_code=204)
async def disconnect_repo(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(DbtRepo).where(DbtRepo.account_id == account_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No dbt repo connected for this account")
    await db.delete(record)
    await db.flush()
