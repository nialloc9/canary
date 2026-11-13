from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.project import GitHubRepo, Project
from app.models.user import Account
from app.schemas.github import (
    GitHubRepoConnect,
    GitHubRepoOut,
    GitHubCreateRepoRequest,
    GitHubCreateRepoResponse,
)
from app.schemas.stack import ModuleVersionOut, ModuleRefreshResponse
from app.services.github_service import GitHubService, GitHubError
from app.services.module_versions_service import list_module_versions, module_version_exists
from app.services.module_refresh_service import hard_refresh_modules, ModuleRefreshError

router = APIRouter(prefix="/github", tags=["github"])


async def _project_slug(account_id: str, db: AsyncSession) -> str:
    """One project per account — its name is just derived from the account name."""
    result = await db.execute(select(Account.name).where(Account.id == account_id))
    name = result.scalar_one_or_none() or "project"
    return name.lower().replace(" ", "-")


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
    result = await db.execute(select(GitHubRepo).where(GitHubRepo.account_id == account_id))
    record = result.scalar_one_or_none()

    # Every field but repo_full_name is optional — resolve what this save
    # will actually end up with (existing DB value if updating and the field
    # was omitted, else a sensible default) *before* validating or writing
    # anything, so we always check the real end state, not just what changed.
    def _resolve(payload_value, db_attr: str, default):
        if payload_value is not None:
            return payload_value
        if record is not None:
            return getattr(record, db_attr)
        return default

    # Masked-secret convention: a blank/masked token means "keep the existing one".
    token_given = payload.token and not payload.token.startswith("••")
    effective_token = payload.token if token_given else _resolve(None, "token", None)
    if effective_token is None:
        raise HTTPException(status_code=422, detail="A GitHub token is required to connect a new repository")

    branch = _resolve(payload.branch, "branch", "main")
    module_version = _resolve(payload.module_version, "module_version", "1.0.0")
    if not module_version_exists(module_version):
        raise HTTPException(status_code=422, detail=f"Unknown module version '{module_version}'")
    api_url = _resolve(payload.api_url, "api_url", "https://api.github.com")
    base_path = _resolve(payload.infrastructure_base_path, "infrastructure_base_path", "infrastructure")
    auto_merge = _resolve(payload.auto_merge, "auto_merge", False)
    create_cicd = _resolve(payload.create_cicd, "create_cicd", True)
    cicd_provider = _resolve(payload.cicd_provider, "cicd_provider", "github_actions")
    skip_bootstrap = _resolve(payload.skip_bootstrap, "skip_bootstrap", False)
    skip_module_import = _resolve(payload.skip_module_import, "skip_module_import", False)

    svc = GitHubService(
        token=effective_token,
        repo_full_name=payload.repo_full_name,
        branch=branch,
        api_url=api_url,
        base_path=base_path,
    )
    try:
        await svc.validate()
    except GitHubError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        if not await svc.branch_exists(branch):
            raise HTTPException(
                status_code=422,
                detail=f"'{branch}' branch doesn't exist in {payload.repo_full_name} — create it first "
                "or connect a different branch.",
            )
    except GitHubError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    project_name = await _project_slug(account_id, db)

    if record:
        record.repo_full_name = payload.repo_full_name
        record.branch = branch
        record.module_version = module_version
        record.token = effective_token
        record.api_url = api_url
        record.infrastructure_base_path = base_path
        record.auto_merge = auto_merge
        record.create_cicd = create_cicd
        record.cicd_provider = cicd_provider
        record.skip_bootstrap = skip_bootstrap
        record.skip_module_import = skip_module_import
    else:
        record = GitHubRepo(
            account_id=account_id,
            project_name=project_name,
            repo_full_name=payload.repo_full_name,
            branch=branch,
            module_version=module_version,
            token=effective_token,
            api_url=api_url,
            infrastructure_base_path=base_path,
            auto_merge=auto_merge,
            create_cicd=create_cicd,
            cicd_provider=cicd_provider,
            skip_bootstrap=skip_bootstrap,
            skip_module_import=skip_module_import,
        )
        db.add(record)

    await db.flush()

    bootstrapped = skip_bootstrap

    proj_result = await db.execute(select(Project).where(Project.account_id == account_id))
    project = proj_result.scalar_one_or_none()
    if project:
        project.version_control_created = True
        if bootstrapped:
            project.infrastructure_bootstrapped = True
    else:
        project = Project(
            account_id=account_id,
            name=project_name,
            version_control_created=True,
            infrastructure_bootstrapped=bootstrapped,
        )
        db.add(project)
    await db.flush()

    return record


@router.get("/repos", response_model=GitHubRepoOut)
async def get_repo(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(GitHubRepo).where(GitHubRepo.account_id == account_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this account")
    return record


@router.delete("/repos", status_code=204)
async def disconnect_repo(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(GitHubRepo).where(GitHubRepo.account_id == account_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this account")
    await db.delete(record)


@router.get("/repos/module-versions", response_model=list[ModuleVersionOut])
async def list_repo_module_versions():
    return [ModuleVersionOut(**v.model_dump()) for v in list_module_versions()]


@router.post("/repos/refresh-modules", response_model=ModuleRefreshResponse)
async def refresh_modules(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(select(GitHubRepo).where(GitHubRepo.account_id == account_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this account")

    try:
        refresh_result = await hard_refresh_modules(record)
    except ModuleRefreshError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if refresh_result.pr_url is None:
        return ModuleRefreshResponse(pr_url=None, files_removed=0, files_added=0, message="Already up to date")

    return ModuleRefreshResponse(
        pr_url=refresh_result.pr_url,
        files_removed=refresh_result.files_removed,
        files_added=refresh_result.files_added,
    )
