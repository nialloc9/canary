import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_account_id
from app.core.database import get_db
from app.models.project import Project, GitHubRepo, CiCd
from app.models.stack import Stack, StackStateBackend
from app.schemas.project import (
    ProjectOut,
    ProjectCiCdResponse,
    ProjectBootstrapRequest,
    ProjectBootstrapResponse,
    ProjectSettingsUpdate,
    StackStateOut,
)
import app.tools.terraform.templates as templates
from app.tools.terraform.verify import verify_bootstrap_plan
from app.services.github_service import GitHubService, GitHubError

router = APIRouter(prefix="/projects", tags=["projects"])


def _secret_suffix(stack_name: str) -> str:
    return stack_name.upper().replace("-", "_")


async def _get_project_or_404(account_id: str, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.account_id == account_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=404, detail="No project found for this account — connect a GitHub repo first"
        )
    return project


async def _get_account_stacks(account_id: str, db: AsyncSession) -> list[Stack]:
    result = await db.execute(
        select(Stack).where(Stack.account_id == account_id).order_by(Stack.sort_order)
    )
    return list(result.scalars().all())


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    result = await db.execute(
        select(Project).where(Project.account_id == account_id)
    )
    return result.scalars().all()


@router.get("/current", response_model=ProjectOut)
async def get_project(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    return await _get_project_or_404(account_id, db)


# Kept in sync with LandingZoneTool._lifecycle_days' keys — every value this
# accepts must have a lifecycle-days mapping there or retention math breaks.
_VALID_RETENTION_POLICIES = {"30-day", "90-day", "1-year", "7-year", "indefinite"}


@router.put("/current/settings", response_model=ProjectOut)
async def update_project_settings(
    payload: ProjectSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    project = await _get_project_or_404(account_id, db)
    if payload.default_retention_policy is not None and payload.default_retention_policy not in _VALID_RETENTION_POLICIES:
        raise HTTPException(
            status_code=422,
            detail=f"default_retention_policy must be one of {sorted(_VALID_RETENTION_POLICIES)} or null",
        )
    project.default_retention_policy = payload.default_retention_policy
    await db.flush()
    return project


@router.post("/cicd", response_model=ProjectCiCdResponse, status_code=201)
async def create_cicd(
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    project = await _get_project_or_404(account_id, db)

    if not project.version_control_created:
        raise HTTPException(
            status_code=409,
            detail="GitHub repo must be connected before creating CI/CD",
        )

    if project.cicd_created:
        raise HTTPException(status_code=409, detail="CI/CD already created for this project")

    repo_result = await db.execute(select(GitHubRepo).where(GitHubRepo.account_id == account_id))
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this project")

    if not repo.create_cicd:
        raise HTTPException(status_code=409, detail="CI/CD was disabled when connecting this repo")

    stacks = await _get_account_stacks(account_id, db)
    if not stacks:
        raise HTTPException(status_code=409, detail="No stacks configured for this account")

    if repo.cicd_provider == "circleci":
        return await _create_cicd_circleci(project, repo, stacks, db, account_id)
    return await _create_cicd_github_actions(project, repo, stacks, db, account_id)


async def _create_cicd_github_actions(
    project: Project,
    repo: GitHubRepo,
    stacks: list[Stack],
    db: AsyncSession,
    account_id: str,
) -> ProjectCiCdResponse:
    missing_warehouse = [s.name for s in stacks if not s.sf_private_key_b64]
    if missing_warehouse:
        raise HTTPException(
            status_code=409,
            detail=f"The following stacks are missing Snowflake credentials: {', '.join(missing_warehouse)}. "
            "Configure them under Admin → Stacks first.",
        )
    missing_cloud = [s.name for s in stacks if not (s.cloud_access_key_id and s.cloud_secret_access_key)]
    if missing_cloud:
        raise HTTPException(
            status_code=409,
            detail=f"The following stacks are missing AWS credentials: {', '.join(missing_cloud)}. "
            "Configure them under Admin → Stacks first.",
        )

    state_backend_result = await db.execute(
        select(StackStateBackend).where(StackStateBackend.github_repo_id == repo.id)
    )
    state_backend_by_stack = {r.stack_id: r for r in state_backend_result.scalars().all()}

    workflow_stacks = [
        {
            "name": s.name,
            "region": state_backend_by_stack[s.id].state_region if s.id in state_backend_by_stack else (s.cloud_region or "eu-west-1"),
            "sf_organization_name": s.sf_organization_name,
            "sf_account_name": s.sf_account_name,
            "sf_user": s.sf_user,
        }
        for s in stacks
    ]

    workflow = templates.ci_workflow(
        stacks=workflow_stacks,
        infrastructure_base_path=repo.infrastructure_base_path,
        branch=repo.branch,
    )
    bootstrap_workflow_yaml = templates.bootstrap_workflow(
        stacks=[{"name": s["name"], "region": s["region"]} for s in workflow_stacks],
        branch=repo.branch,
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

    secrets: dict[str, str] = {}
    for s in stacks:
        suffix = _secret_suffix(s.name)
        secrets[f"SNOWFLAKE_ORGANIZATION_NAME__{suffix}"] = s.sf_organization_name
        secrets[f"SNOWFLAKE_ACCOUNT_NAME__{suffix}"] = s.sf_account_name
        secrets[f"SNOWFLAKE_USER__{suffix}"] = s.sf_user
        secrets[f"SNOWFLAKE_AUTHENTICATOR__{suffix}"] = s.sf_authenticator
        secrets[f"SNOWFLAKE_PRIVATE_KEY_B64__{suffix}"] = s.sf_private_key_b64
        secrets[f"AWS_ACCESS_KEY_ID__{suffix}"] = s.cloud_access_key_id
        secrets[f"AWS_SECRET_ACCESS_KEY__{suffix}"] = s.cloud_secret_access_key

    secrets_table = "\n".join(
        f"| `SNOWFLAKE_ORGANIZATION_NAME__{_secret_suffix(s.name)}` / "
        f"`SNOWFLAKE_ACCOUNT_NAME__{_secret_suffix(s.name)}` / "
        f"`SNOWFLAKE_USER__{_secret_suffix(s.name)}` / "
        f"`SNOWFLAKE_AUTHENTICATOR__{_secret_suffix(s.name)}` / "
        f"`SNOWFLAKE_PRIVATE_KEY_B64__{_secret_suffix(s.name)}` / "
        f"`AWS_ACCESS_KEY_ID__{_secret_suffix(s.name)}` / "
        f"`AWS_SECRET_ACCESS_KEY__{_secret_suffix(s.name)}` | Stack '{s.name}' |"
        for s in stacks
    )

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
                    "- `canary-infrastructure-deploy` — Terragrunt plan/apply for landing zones, one job per stack\n"
                    "- `canary-bootstrap` — Terraform plan/apply for remote state backend, one job per stack\n\n"
                    "## Secrets configured (per stack)\n\n"
                    "| Secrets | Source |\n|---|---|\n"
                    f"{secrets_table}\n\n"
                    "---\n🤖 Generated by Canary"
                ),
                root_files={
                    ".github/workflows/canary-infrastructure-deploy.yml": workflow.encode(),
                    ".github/workflows/canary-bootstrap.yml": bootstrap_workflow_yaml.encode(),
                },
            )
        except GitHubError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    auto_merged = False
    if repo.auto_merge and pr_url:
        try:
            pr_number = int(pr_url.rstrip("/").split("/")[-1])
            await svc.merge_pull_request(pr_number)
            auto_merged = True
        except GitHubError as exc:
            raise HTTPException(status_code=422, detail=f"Auto-merge failed: {exc}")

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
        message="CI/CD setup complete" if pr_url else "CI/CD setup complete — workflows already up to date, no PR needed",
        cicd_created=True,
        pull_requests=[pr_url] if pr_url else [],
        auto_merged=auto_merged,
        secrets_created=list(secrets.keys()),
        workflows_created=workflows,
    )


async def _create_cicd_circleci(
    project: Project,
    repo: GitHubRepo,
    stacks: list[Stack],
    db: AsyncSession,
    account_id: str,
) -> ProjectCiCdResponse:
    """Unlike GitHub Actions, Canary never pushes secret values here — every
    stack must already have a circleci_context (a CircleCI context the user
    created themselves, in Project Settings -> Contexts, populated with that
    stack's SNOWFLAKE_*/AWS_* env vars) and the generated config only ever
    references it by name."""
    missing_context = [s.name for s in stacks if not s.circleci_context]
    if missing_context:
        raise HTTPException(
            status_code=409,
            detail=f"The following stacks are missing a CircleCI context: {', '.join(missing_context)}. "
            "Create the context in CircleCI's Project Settings, populate it with SNOWFLAKE_*/AWS_* env vars, "
            "then set its name under Admin → Stacks first.",
        )

    state_backend_result = await db.execute(
        select(StackStateBackend).where(StackStateBackend.github_repo_id == repo.id)
    )
    state_backend_by_stack = {r.stack_id: r for r in state_backend_result.scalars().all()}

    workflow_stacks = [
        {
            "name": s.name,
            "region": state_backend_by_stack[s.id].state_region if s.id in state_backend_by_stack else (s.cloud_region or "eu-west-1"),
            "circleci_context": s.circleci_context,
        }
        for s in stacks
    ]

    config_yaml = templates.circleci_config(
        infra_stacks=workflow_stacks,
        bootstrap_stacks=workflow_stacks,
        infrastructure_base_path=repo.infrastructure_base_path,
        branch=repo.branch,
    )

    slug = datetime.now().strftime("%Y%m%d-%H%M%S")
    svc = GitHubService(
        token=repo.token,
        repo_full_name=repo.repo_full_name,
        branch=repo.branch,
        api_url=repo.api_url,
        base_path="",
    )

    contexts_table = "\n".join(f"| {s['name']} | `{s['circleci_context']}` |" for s in workflow_stacks)

    with tempfile.TemporaryDirectory() as staging:
        try:
            pr_url, _ = await svc.open_pull_request(
                local_dir=Path(staging),
                feature_branch=f"feat/cicd-circleci-{slug}",
                commit_message="feat(cicd): add CircleCI config for Canary infrastructure",
                pr_title="feat(cicd): add CircleCI config",
                pr_body=(
                    "## Summary\n\n"
                    "Adds `.circleci/config.yml` with two workflows:\n"
                    "- `canary-infrastructure-deploy` — Terragrunt plan/apply for landing zones, one job pair per stack\n"
                    "- `canary-bootstrap` — Terraform plan/apply for remote state backend, one job pair per stack\n\n"
                    "No secrets were pushed by Canary — each stack's jobs reference a CircleCI context you must "
                    "already have populated yourself:\n\n"
                    "| Stack | Context |\n|---|---|\n"
                    f"{contexts_table}\n\n"
                    "---\n🤖 Generated by Canary"
                ),
                root_files={".circleci/config.yml": config_yaml.encode()},
            )
        except GitHubError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    auto_merged = False
    if repo.auto_merge and pr_url:
        try:
            pr_number = int(pr_url.rstrip("/").split("/")[-1])
            await svc.merge_pull_request(pr_number)
            auto_merged = True
        except GitHubError as exc:
            raise HTTPException(status_code=422, detail=f"Auto-merge failed: {exc}")

    cicd_result = await db.execute(
        select(CiCd).where(CiCd.github_repo_id == repo.id, CiCd.type == "circleci")
    )
    cicd_record = cicd_result.scalar_one_or_none()
    if cicd_record:
        cicd_record.bootstrapped = True
    else:
        db.add(CiCd(account_id=account_id, github_repo_id=repo.id, type="circleci", bootstrapped=True))

    project.cicd_created = True
    await db.flush()

    return ProjectCiCdResponse(
        message="CI/CD setup complete" if pr_url else "CI/CD setup complete — config already up to date, no PR needed",
        cicd_created=True,
        pull_requests=[pr_url] if pr_url else [],
        auto_merged=auto_merged,
        secrets_created=[],
        workflows_created=[".circleci/config.yml"],
    )


@router.post("/bootstrap", response_model=ProjectBootstrapResponse, status_code=201)
async def bootstrap_infrastructure(
    payload: ProjectBootstrapRequest,
    db: AsyncSession = Depends(get_db),
    account_id: str = Depends(get_current_account_id),
):
    project = await _get_project_or_404(account_id, db)

    if not project.version_control_created:
        raise HTTPException(
            status_code=409,
            detail="GitHub repo must be connected before bootstrapping infrastructure",
        )

    if project.infrastructure_bootstrapped:
        raise HTTPException(status_code=409, detail="Infrastructure already bootstrapped")

    repo_result = await db.execute(select(GitHubRepo).where(GitHubRepo.account_id == account_id))
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="No GitHub repo connected for this project")

    if repo.create_cicd and not project.cicd_created:
        raise HTTPException(
            status_code=409,
            detail="CI/CD must be created before bootstrapping infrastructure. Call POST /api/v1/projects/cicd first.",
        )

    stacks = await _get_account_stacks(account_id, db)
    if not stacks:
        raise HTTPException(status_code=409, detail="No stacks configured for this account")

    overrides = payload.overrides or {}
    stack_states: list[dict] = []
    for s in stacks:
        override = overrides.get(s.name)
        stack_states.append({
            "stack": s,
            "bucket": (override.bucket if override else None) or f"{project.name}-{s.name}-terraform-state",
            "region": (override.region if override else None) or "eu-west-1",
            "lock_table": (override.lock_table if override else None) or f"{project.name}-{s.name}-terraform-lock",
        })

    slug = datetime.now().strftime("%Y%m%d-%H%M%S")
    svc = GitHubService(
        token=repo.token,
        repo_full_name=repo.repo_full_name,
        branch=repo.branch,
        api_url=repo.api_url,
        base_path="",
    )

    bootstrap_files: dict[str, bytes] = {}
    for st in stack_states:
        stack_name = st["stack"].name
        bootstrap_files[f"bootstrap/{stack_name}/main.tf"] = templates.state_bootstrap_main(
            st["bucket"], st["region"], st["lock_table"]
        ).encode()
        bootstrap_files[f"bootstrap/{stack_name}/outputs.tf"] = templates.state_bootstrap_outputs().encode()
        bootstrap_files[f"bootstrap/{stack_name}/versions.tf"] = templates.state_bootstrap_versions().encode()

    table_rows = "\n".join(
        f"| {st['stack'].name} | `{st['bucket']}` | `{st['region']}` | `{st['lock_table']}` |"
        for st in stack_states
    )
    apply_commands = "\n".join(
        f"cd bootstrap/{st['stack'].name} && terraform init && terraform apply" for st in stack_states
    )
    commit_lines = "\n".join(
        f"- {st['stack'].name}: {st['bucket']} ({st['region']})" for st in stack_states
    )

    pr_body = (
        f"## Summary\n\n"
        f"Provisions S3 remote state backends for every stack before any infrastructure is applied.\n\n"
        f"| Stack | S3 Bucket | Region | DynamoDB Table |\n|---|---|---|---|\n"
        f"{table_rows}\n\n"
        f"## ⚠️ Apply before creating any landing zones\n\n"
        f"```bash\n{apply_commands}\n```\n\n"
        f"---\n🤖 Generated by Canary"
    )

    with tempfile.TemporaryDirectory() as staging:
        staging_path = Path(staging)
        for rel_path, content in bootstrap_files.items():
            file_path = staging_path / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

        verify_failures: list[str] = []
        for st in stack_states:
            stack = st["stack"]
            if not stack.verify_before_pr:
                continue
            result = await verify_bootstrap_plan(
                staging_path / "bootstrap" / stack.name, stack, max_attempts=stack.verify_max_attempts
            )
            if not result.ok:
                verify_failures.append(
                    f"Stack '{stack.name}' failed `terraform plan` after {result.attempts} attempt(s):\n"
                    f"{result.log[-2000:]}"
                )
        if verify_failures:
            raise HTTPException(
                status_code=422,
                detail="Bootstrap files failed pre-PR verification — no PR was opened.\n\n"
                + "\n\n".join(verify_failures),
            )

        try:
            pr_url, _ = await svc.open_pull_request(
                local_dir=staging_path,
                feature_branch=f"feat/terraform-state-bootstrap-{slug}",
                commit_message=(
                    "feat(bootstrap): provision Terraform state backends for all stacks\n\n"
                    f"{commit_lines}"
                ),
                pr_title="feat(bootstrap): provision Terraform state backends",
                pr_body=pr_body,
                root_files=bootstrap_files,
            )
        except GitHubError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    for st in stack_states:
        existing = await db.execute(
            select(StackStateBackend).where(
                StackStateBackend.github_repo_id == repo.id,
                StackStateBackend.stack_id == st["stack"].id,
            )
        )
        record = existing.scalar_one_or_none()
        if record:
            record.state_bucket = st["bucket"]
            record.state_region = st["region"]
            record.state_lock_table = st["lock_table"]
        else:
            db.add(StackStateBackend(
                account_id=account_id,
                github_repo_id=repo.id,
                stack_id=st["stack"].id,
                state_bucket=st["bucket"],
                state_region=st["region"],
                state_lock_table=st["lock_table"],
            ))

    project.infrastructure_bootstrapped = True
    await db.flush()

    return ProjectBootstrapResponse(
        pr_url=pr_url,
        stacks=[
            StackStateOut(
                name=st["stack"].name,
                bucket=st["bucket"],
                region=st["region"],
                lock_table=st["lock_table"],
            )
            for st in stack_states
        ],
    )
