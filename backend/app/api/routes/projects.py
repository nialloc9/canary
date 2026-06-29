import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.project import Project, GitHubRepo, CiCd, SnowflakeCredentials, Warehouse
from app.schemas.project import (
    ProjectOut,
    ProjectCiCdRequest,
    ProjectCiCdResponse,
    ProjectWarehouseRequest,
    ProjectWarehouseResponse,
    ProjectBootstrapRequest,
    ProjectBootstrapResponse,
)
import app.tools.terraform.templates as templates
from app.services.github_service import GitHubService, GitHubError

router = APIRouter(prefix="/projects", tags=["projects"])


async def _get_project_or_404(name: str, account_id: str, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(
            Project.account_id == account_id,
            Project.name == name,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(Project).where(Project.account_id == account_id)
    )
    return result.scalars().all()


@router.get("/{name}", response_model=ProjectOut)
async def get_project(
    name: str,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    return await _get_project_or_404(name, account_id, db)


@router.post("/{name}/warehouse", response_model=ProjectWarehouseResponse, status_code=201)
async def create_warehouse(
    name: str,
    payload: ProjectWarehouseRequest,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    project = await _get_project_or_404(name, account_id, db)

    if not project.version_control_created:
        raise HTTPException(
            status_code=409,
            detail="GitHub repo must be connected before creating a warehouse",
        )

    sf_result = await db.execute(
        select(SnowflakeCredentials).where(
            SnowflakeCredentials.account_id == account_id,
            SnowflakeCredentials.project_name == name,
        )
    )
    sf_creds = sf_result.scalar_one_or_none()
    if not sf_creds:
        raise HTTPException(
            status_code=409,
            detail=f"No Snowflake credentials found for project '{name}'. Connect Snowflake first via POST /api/v1/snowflake/credentials.",
        )

    warehouse = Warehouse(
        account_id=account_id,
        project_name=name,
        type=payload.type,
        name=payload.name,
        warehouse_credentials_id=sf_creds.id,
    )
    db.add(warehouse)
    project.warehouse_created = True
    await db.flush()

    return warehouse


@router.post("/{name}/cicd", response_model=ProjectCiCdResponse, status_code=201)
async def create_cicd(
    name: str,
    payload: ProjectCiCdRequest = ProjectCiCdRequest(),
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    project = await _get_project_or_404(name, account_id, db)

    if not project.version_control_created:
        raise HTTPException(
            status_code=409,
            detail="GitHub repo must be connected before creating CI/CD",
        )

    if project.cicd_created:
        raise HTTPException(status_code=409, detail="CI/CD already created for this project")

    repo_result = await db.execute(
        select(GitHubRepo).where(
            GitHubRepo.account_id == account_id,
            GitHubRepo.project_name == name,
        )
    )
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this project")

    if not repo.create_cicd:
        raise HTTPException(status_code=409, detail="CI/CD was disabled when connecting this repo")

    sf_result = await db.execute(
        select(SnowflakeCredentials).where(
            SnowflakeCredentials.account_id == account_id,
            SnowflakeCredentials.project_name == name,
        )
    )
    sf_creds = sf_result.scalar_one_or_none()
    if not sf_creds:
        raise HTTPException(
            status_code=409,
            detail=f"No Snowflake credentials found for project '{name}'. Connect Snowflake first via POST /api/v1/snowflake/credentials.",
        )

    state_region = repo.dev_state_region or "eu-west-1"

    workflow = templates.ci_workflow(
        snowflake_org=sf_creds.organization_name,
        snowflake_account=sf_creds.account_name,
        snowflake_user=sf_creds.user,
        state_region=state_region,
        infrastructure_base_path=repo.infrastructure_base_path,
    )

    slug = datetime.now().strftime("%Y%m%d-%H%M%S")
    svc = GitHubService(
        token=repo.token,
        repo_full_name=repo.repo_full_name,
        branch=repo.branch,
        api_url=repo.api_url,
        base_path="",
    )

    workflows = [
        "canary-infrastructure-deploy.yml",
        "canary-bootstrap.yml",
    ]

    with tempfile.TemporaryDirectory() as staging:
        try:
            pr_url, _ = await svc.open_pull_request(
                local_dir=Path(staging),
                feature_branch=f"feat/cicd-github-actions-{slug}",
                commit_message="feat(cicd): add GitHub Actions workflows for Canary infrastructure",
                pr_title="feat(cicd): add GitHub Actions workflows",
                pr_body=(
                    "## Summary\n\n"
                    "Adds CI/CD workflows:\n"
                    "- `canary-infrastructure-deploy` — Terragrunt plan/apply for landing zones\n"
                    "- `canary-bootstrap` — Terraform plan/apply for remote state backend\n\n"
                    "## Secrets configured\n\n"
                    "| Secret | Source |\n|---|---|\n"
                    "| `SNOWFLAKE_ORGANIZATION_NAME` | Snowflake credentials |\n"
                    "| `SNOWFLAKE_ACCOUNT_NAME` | Snowflake credentials |\n"
                    "| `SNOWFLAKE_USER` | Snowflake credentials |\n"
                    "| `SNOWFLAKE_AUTHENTICATOR` | Snowflake credentials |\n"
                    "| `SNOWFLAKE_PRIVATE_KEY_B64` | Snowflake credentials |\n"
                    "| `AWS_ACCESS_KEY_ID` | Provided at setup |\n"
                    "| `AWS_SECRET_ACCESS_KEY` | Provided at setup |\n\n"
                    "---\n🤖 Generated by Canary"
                ),
                root_files={
                    ".github/workflows/canary-infrastructure-deploy.yml": workflow.encode(),
                    ".github/workflows/canary-bootstrap.yml": templates.bootstrap_workflow(
                        dev_state_region=repo.dev_state_region or "eu-west-1",
                        prod_state_region=repo.prod_state_region or "eu-west-1",
                    ).encode(),
                },
            )
        except GitHubError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    auto_merged = False
    if repo.auto_merge:
        try:
            pr_number = int(pr_url.rstrip("/").split("/")[-1])
            await svc.merge_pull_request(pr_number)
            auto_merged = True
        except GitHubError as exc:
            raise HTTPException(status_code=422, detail=f"Auto-merge failed: {exc}")

    secrets: dict[str, str] = {
        "SNOWFLAKE_ORGANIZATION_NAME": sf_creds.organization_name,
        "SNOWFLAKE_ACCOUNT_NAME": sf_creds.account_name,
        "SNOWFLAKE_USER": sf_creds.user,
        "SNOWFLAKE_AUTHENTICATOR": sf_creds.authenticator,
        "SNOWFLAKE_PRIVATE_KEY_B64": sf_creds.private_key_b64,
    }
    if payload.aws_access_key_id:
        secrets["AWS_ACCESS_KEY_ID"] = payload.aws_access_key_id
    if payload.aws_secret_access_key:
        secrets["AWS_SECRET_ACCESS_KEY"] = payload.aws_secret_access_key

    try:
        await svc.set_secrets(secrets)
    except GitHubError as exc:
        raise HTTPException(status_code=422, detail=f"Secrets upload failed: {exc}")

    cicd_result = await db.execute(
        select(CiCd).where(
            CiCd.github_repo_id == repo.id,
            CiCd.type == "github_actions",
        )
    )
    cicd_record = cicd_result.scalar_one_or_none()
    if cicd_record:
        cicd_record.bootstrapped = True
    else:
        db.add(CiCd(
            account_id=account_id,
            github_repo_id=repo.id,
            type="github_actions",
            bootstrapped=True,
        ))

    project.cicd_created = True
    await db.flush()

    return ProjectCiCdResponse(
        message="CI/CD setup complete",
        cicd_created=True,
        pull_requests=[pr_url],
        auto_merged=auto_merged,
        secrets_created=list(secrets.keys()),
        workflows_created=workflows,
    )


@router.post("/{name}/bootstrap", response_model=ProjectBootstrapResponse, status_code=201)
async def bootstrap_infrastructure(
    name: str,
    payload: ProjectBootstrapRequest,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    project = await _get_project_or_404(name, account_id, db)

    if not project.version_control_created:
        raise HTTPException(
            status_code=409,
            detail="GitHub repo must be connected before bootstrapping infrastructure",
        )

    if project.infrastructure_bootstrapped:
        raise HTTPException(status_code=409, detail="Infrastructure already bootstrapped")

    repo_result = await db.execute(
        select(GitHubRepo).where(
            GitHubRepo.account_id == account_id,
            GitHubRepo.project_name == name,
        )
    )
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this project")

    if repo.create_cicd and not project.cicd_created:
        raise HTTPException(
            status_code=409,
            detail="CI/CD must be created before bootstrapping infrastructure. Call POST /api/v1/projects/{name}/cicd first.",
        )

    dev_state_bucket = payload.dev_state_bucket or f"{name}-dev-terraform-state"
    dev_state_region = payload.dev_state_region or "eu-west-1"
    dev_state_lock_table = payload.dev_state_lock_table or f"{name}-dev-terraform-lock"
    prod_state_bucket = payload.prod_state_bucket or f"{name}-prod-terraform-state"
    prod_state_region = payload.prod_state_region or "eu-west-1"
    prod_state_lock_table = payload.prod_state_lock_table or f"{name}-prod-terraform-lock"

    repo.dev_state_bucket = dev_state_bucket
    repo.dev_state_region = dev_state_region
    repo.dev_state_lock_table = dev_state_lock_table
    repo.prod_state_bucket = prod_state_bucket
    repo.prod_state_region = prod_state_region
    repo.prod_state_lock_table = prod_state_lock_table

    slug = datetime.now().strftime("%Y%m%d-%H%M%S")
    svc = GitHubService(
        token=repo.token,
        repo_full_name=repo.repo_full_name,
        branch=repo.branch,
        api_url=repo.api_url,
        base_path="",
    )

    bootstrap_files = {
        "bootstrap/dev/main.tf": templates.state_bootstrap_main(dev_state_bucket, dev_state_region, dev_state_lock_table).encode(),
        "bootstrap/dev/outputs.tf": templates.state_bootstrap_outputs().encode(),
        "bootstrap/dev/versions.tf": templates.state_bootstrap_versions().encode(),
        "bootstrap/prod/main.tf": templates.state_bootstrap_main(prod_state_bucket, prod_state_region, prod_state_lock_table).encode(),
        "bootstrap/prod/outputs.tf": templates.state_bootstrap_outputs().encode(),
        "bootstrap/prod/versions.tf": templates.state_bootstrap_versions().encode(),
    }

    pr_body = (
        f"## Summary\n\n"
        f"Provisions S3 remote state backends for dev and prod before any infrastructure is applied.\n\n"
        f"| Environment | S3 Bucket | Region | DynamoDB Table |\n|---|---|---|---|\n"
        f"| dev | `{dev_state_bucket}` | `{dev_state_region}` | `{dev_state_lock_table}` |\n"
        f"| prod | `{prod_state_bucket}` | `{prod_state_region}` | `{prod_state_lock_table}` |\n\n"
        f"## ⚠️ Apply before creating any landing zones\n\n"
        f"```bash\ncd bootstrap/dev && terraform init && terraform apply\n"
        f"cd bootstrap/prod && terraform init && terraform apply\n```\n\n"
        f"---\n🤖 Generated by Canary"
    )

    with tempfile.TemporaryDirectory() as staging:
        try:
            pr_url, _ = await svc.open_pull_request(
                local_dir=Path(staging),
                feature_branch=f"feat/terraform-state-bootstrap-{slug}",
                commit_message=(
                    "feat(bootstrap): provision Terraform state backends for dev and prod\n\n"
                    f"- dev: {dev_state_bucket} ({dev_state_region})\n"
                    f"- prod: {prod_state_bucket} ({prod_state_region})"
                ),
                pr_title="feat(bootstrap): provision Terraform state backends",
                pr_body=pr_body,
                root_files=bootstrap_files,
            )
        except GitHubError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    project.infrastructure_bootstrapped = True
    await db.flush()

    return ProjectBootstrapResponse(
        pr_url=pr_url,
        dev_state_bucket=dev_state_bucket,
        dev_state_region=dev_state_region,
        dev_state_lock_table=dev_state_lock_table,
        prod_state_bucket=prod_state_bucket,
        prod_state_region=prod_state_region,
        prod_state_lock_table=prod_state_lock_table,
    )
