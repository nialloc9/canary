import os
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
import app.tools.terraform.templates as templates
from app.models.project import GitHubRepo, SnowflakeCredentials, Project
from app.models.user import Account
from app.services.github_service import GitHubService, GitHubError

TERRAFORM_MODULES_DIR = Path(__file__).resolve().parents[3] / "terraform" / "modules"


class LandingZoneTool(BaseTool):

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id


    @property
    def name(self) -> str:
        return "create_landing_zone"

    @property
    def description(self) -> str:
        return (
            "Provision a full landing zone: S3 bucket, Snowflake database, "
            "medallion-arch schemas, and Snowflake storage integration. "
            "Copies Terraform modules into an upload/ directory and generates "
            "terragrunt configs for dev and prod environments with {name}-db, "
            "{name}-db-arch, and {name}-lz folders wired together via dependencies. "
            "Requires data classification, retention policy, data owner, and "
            "environment details."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Project or data-source name (used in naming all resources)",
                },
                "region": {
                    "type": "string",
                    "description": "AWS region (e.g. eu-west-1)",
                    "default": "eu-west-1",
                },
                "data_classification": {
                    "type": "string",
                    "description": "Data classification level",
                    "enum": ["public", "internal", "confidential", "restricted"],
                },
                "retention_policy": {
                    "type": "string",
                    "description": "How long data must be retained",
                    "enum": ["30-day", "90-day", "1-year", "7-year", "indefinite"],
                },
                "data_owner": {
                    "type": "string",
                    "description": "Team or person responsible for this data",
                },
                "department": {
                    "type": "string",
                    "description": "Owning department",
                    "default": "none",
                },
                "cost_center": {
                    "type": "string",
                    "description": "Cost center code for billing",
                    "default": "none",
                },
                "project_code": {
                    "type": "string",
                    "description": "Project code for tracking",
                    "default": "none",
                },
                "kms_key_arn": {
                    "type": "string",
                    "description": "ARN of a KMS key for SSE-KMS. Leave empty for AWS-managed key.",
                    "default": "",
                },
                "existing_s3_bucket_arn": {
                    "type": "string",
                    "description": "ARN of an existing bucket to reuse. Leave empty to create new.",
                    "default": "",
                },
                "s3_stage_prefix": {
                    "type": "string",
                    "description": "Key prefix within the bucket for the Snowflake stage",
                    "default": "data/",
                },
                "file_format_type": {
                    "type": "string",
                    "description": "Snowflake file format type",
                    "enum": ["JSON", "CSV", "PARQUET", "AVRO", "ORC", "XML"],
                    "default": "JSON",
                },
                "create_access_keys": {
                    "type": "boolean",
                    "description": "Create an IAM user with access keys for direct S3 access",
                    "default": False,
                },
                "schema_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Medallion schema names",
                    "default": ["bronze", "silver", "gold", "platinum"],
                },
                "tags": {
                    "type": "object",
                    "description": "Additional key-value tags",
                    "default": {},
                },
            },
            "required": [
                "name",
                "data_classification",
                "retention_policy",
                "data_owner",
            ],
        }

    async def execute(
        self,
        name: str,
        data_classification: str,
        retention_policy: str,
        data_owner: str,
        region: str = "eu-west-1",
        department: str = "none",
        cost_center: str = "none",
        project_code: str = "none",
        kms_key_arn: str = "",
        existing_s3_bucket_arn: str = "",
        s3_stage_prefix: str = "data/",
        file_format_type: str = "JSON",
        create_access_keys: bool = False,
        schema_names: list[str] = None,
        tags: dict = {},
        _action: str = "add",
    ) -> str:
        if schema_names is None:
            schema_names = ["bronze", "silver", "gold", "platinum"]

        transition_to_ia_days, transition_to_glacier_days, expiration_days = (
            self._lifecycle_days(retention_policy)
        )

        upload_root = Path(__file__).resolve().parents[3] / "upload" / name
        shutil.rmtree(upload_root, ignore_errors=True)
        os.makedirs(upload_root)

        account = await self._get_account()
        account_slug = account.name.lower().replace(" ", "-") if account else project_code

        project = await self._get_project(project_code)
        if project is None:
            return f"No project named '{project_code}' found. Connect a GitHub repo first via POST /api/v1/github/repos."
        if not project.version_control_created:
            return f"GitHub repo not yet connected for project '{project_code}'. Use POST /api/v1/github/repos."
        repo_record = await self._get_github_repo(project_code)

        if not project.infrastructure_bootstrapped and not (repo_record and repo_record.skip_bootstrap):
            return (
                f"Infrastructure not yet bootstrapped for project '{project_code}'. "
                f"Call POST /api/v1/projects/{project_code}/bootstrap first."
            )

        if repo_record and repo_record.create_cicd and not project.cicd_created:
            return (
                f"CI/CD not yet created for project '{project_code}'. "
                f"Call POST /api/v1/projects/{project_code}/cicd first."
            )

        state_configs = {
            "dev": {
                "bucket": (repo_record.dev_state_bucket if repo_record else None) or f"{project_code}-dev-terraform-state",
                "region": (repo_record.dev_state_region if repo_record else None) or region,
                "lock_table": (repo_record.dev_state_lock_table if repo_record else None) or f"{project_code}-dev-terraform-lock",
            },
            "prod": {
                "bucket": (repo_record.prod_state_bucket if repo_record else None) or f"{project_code}-prod-terraform-state",
                "region": (repo_record.prod_state_region if repo_record else None) or region,
                "lock_table": (repo_record.prod_state_lock_table if repo_record else None) or f"{project_code}-prod-terraform-lock",
            },
        }

        if not (repo_record and repo_record.skip_module_import):
            self._copy_modules(upload_root)
        if not (repo_record and repo_record.skip_bootstrap):
            self._write_root_hcl(upload_root, name, region, tags)

        schemas_hcl = ", ".join(f'"{s}"' for s in schema_names)

        for env in ("dev", "prod"):
            sc = state_configs[env]
            env_top_dir = upload_root / env
            env_dir = env_top_dir / "landing-zone"
            os.makedirs(env_dir, exist_ok=True)

            (env_top_dir / "env.hcl").write_text(templates.env_hcl(
                account_slug, env,
                state_bucket=sc["bucket"],
                state_region=sc["region"],
                state_lock_table=sc["lock_table"],
            ))
            (env_top_dir / "region.hcl").write_text(templates.region_hcl(region))

            db_dir = env_dir / f"{name}-db"
            os.makedirs(db_dir, exist_ok=True)
            (db_dir / "terragrunt.hcl").write_text(templates.db(name, env))

            db_arch_dir = env_dir / f"{name}-db-arch"
            os.makedirs(db_arch_dir, exist_ok=True)
            (db_arch_dir / "terragrunt.hcl").write_text(
                templates.db_arch(name, data_classification, schemas_hcl)
            )

            lz_dir = env_dir / f"{name}-lz"
            os.makedirs(lz_dir, exist_ok=True)
            (lz_dir / "terragrunt.hcl").write_text(
                templates.lz(
                    name=name,
                    env=env,
                    data_classification=data_classification,
                    retention_policy=retention_policy,
                    data_owner=data_owner,
                    department=department,
                    cost_center=cost_center,
                    project_code=project_code,
                    create_access_keys=create_access_keys,
                    transition_to_ia_days=transition_to_ia_days,
                    transition_to_glacier_days=transition_to_glacier_days,
                    expiration_days=expiration_days,
                    existing_s3_bucket_arn=existing_s3_bucket_arn,
                    kms_key_arn=kms_key_arn,
                )
            )

            si_dir = env_dir / f"{name}-si"
            os.makedirs(si_dir, exist_ok=True)
            (si_dir / "terragrunt.hcl").write_text(
                templates.si(
                    name=name,
                    s3_stage_prefix=s3_stage_prefix,
                    file_format_type=file_format_type,
                )
            )

        github_section = await self._open_github_pr(
            repo_project_name=project_code,
            landing_zone_name=name,
            upload_root=upload_root,
            data_classification=data_classification,
            retention_policy=retention_policy,
            schema_names=schema_names,
            action=_action,
        )

        return (
            f"Landing zone ready at {upload_root}\n\n"
            f"  Data classification: {data_classification}\n"
            f"  Retention policy:    {retention_policy}\n"
            f"  Data owner:          {data_owner}\n"
            f"  Schemas:             {', '.join(schema_names)}\n\n"
            f"Structure:\n"
            f"  upload/{name}/\n"
            f"    modules/aws/landing-zone/\n"
            f"    modules/snowflake/database/\n"
            f"    modules/snowflake/medallion-arch/\n"
            f"    modules/snowflake/s3-storage-integration/\n"
            f"    terragrunt.hcl        (root config)\n"
            f"    global.hcl\n"
            f"    dev/landing-zone/\n"
            f"      {name}-db/         (Snowflake database)\n"
            f"      {name}-db-arch/    (medallion schemas)\n"
            f"      {name}-lz/         (S3 bucket)\n"
            f"      {name}-si/         (Snowflake storage integration + stage)\n"
            f"    prod/landing-zone/\n"
            f"      {name}-db/\n"
            f"      {name}-db-arch/\n"
            f"      {name}-lz/\n"
            f"      {name}-si/\n"
            f"{github_section}\n"
            f"To deploy (dev):\n"
            f"  terragrunt run-all plan  --terragrunt-working-dir dev/landing-zone\n"
            f"  terragrunt run-all apply --terragrunt-working-dir dev/landing-zone"
        )

    async def _open_github_pr(
        self,
        repo_project_name: str,
        landing_zone_name: str,
        upload_root: Path,
        data_classification: str,
        retention_policy: str,
        schema_names: list[str],
        action: str = "add",
    ) -> str:
        result = await self._db.execute(
            select(GitHubRepo).where(
                GitHubRepo.account_id == self._account_id,
                GitHubRepo.project_name == repo_project_name,
            )
        )
        record = result.scalar_one_or_none()

        if not record:
            record = await self._create_and_store_repo(repo_project_name)
            if record is None:
                return "\n  GitHub: no base connection found — use POST /api/v1/github/repos to connect one first\n\n"

        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        conv_type = "feat" if action == "add" else "chore"
        feature_branch = f"{conv_type}/{landing_zone_name}-landing-zone-{slug}"

        commit_message = (
            f"{conv_type}(landing-zone): {action} {landing_zone_name} landing zone\n\n"
            f"- Data classification: {data_classification}\n"
            f"- Retention policy: {retention_policy}\n"
            f"- Schemas: {', '.join(schema_names)}\n"
            f"- Environments: dev, prod"
        )

        pr_title = f"{conv_type}(landing-zone): {action} {landing_zone_name} landing zone"

        summary_verb = "Adds" if action == "add" else "Updates"
        pr_body = (
            f"## Summary\n\n"
            f"{summary_verb} the landing zone for `{landing_zone_name}`.\n\n"
            f"- **`{landing_zone_name}-db`** — Snowflake database\n"
            f"- **`{landing_zone_name}-db-arch`** — Medallion schemas "
            f"({', '.join(f'`{s}`' for s in schema_names)})\n"
            f"- **`{landing_zone_name}-lz`** — S3 bucket\n"
            f"- **`{landing_zone_name}-si`** — Snowflake storage integration + external stage\n\n"
            f"## Configuration\n\n"
            f"| Setting | Value |\n"
            f"|---|---|\n"
            f"| Data classification | `{data_classification}` |\n"
            f"| Retention policy | `{retention_policy}` |\n"
            f"| Environments | `dev`, `prod` |\n\n"
            f"## Test plan\n\n"
            f"- [ ] `terragrunt run-all validate` passes in `dev/landing-zone`\n"
            f"- [ ] `terragrunt run-all plan` shows expected resources\n"
            f"- [ ] Apply to dev before prod\n\n"
            f"---\n"
            f"🤖 Generated by Canary"
        )

        svc = GitHubService(
            token=record.token,
            repo_full_name=record.repo_full_name,
            branch=record.branch,
            api_url=record.api_url,
            base_path=record.infrastructure_base_path,
        )

        try:
            pr_url, file_count = await svc.open_pull_request(
                local_dir=upload_root,
                feature_branch=feature_branch,
                commit_message=commit_message,
                pr_title=pr_title,
                pr_body=pr_body,
            )
            if record.auto_merge:
                pr_number = int(pr_url.rstrip("/").split("/")[-1])
                await svc.merge_pull_request(pr_number)
                return (
                    f"\n  GitHub: merged PR #{pr_number} with {file_count} files → {record.repo_full_name}\n"
                    f"  Branch: {feature_branch} → {record.branch}\n"
                    f"  PR:     {pr_url} (merged)\n\n"
                )
            return (
                f"\n  GitHub: opened PR with {file_count} files → {record.repo_full_name}\n"
                f"  Branch: {feature_branch} → {record.branch}\n"
                f"  PR:     {pr_url}\n\n"
            )
        except GitHubError as exc:
            return f"\n  GitHub: PR failed — {exc}\n\n"

    async def _create_and_store_repo(self, project_name: str) -> GitHubRepo | None:
        """Find the base GitHub connection, create a new repo, store and return the record."""
        base_result = await self._db.execute(
            select(GitHubRepo).where(GitHubRepo.account_id == self._account_id).limit(1)
        )
        base = base_result.scalar_one_or_none()
        if not base:
            return None

        repo_name = f"{base.project_name}-{project_name}"
        svc = GitHubService(
            token=base.token,
            repo_full_name="",
            branch=base.branch,
            api_url=base.api_url,
        )
        try:
            created = await svc.create_repo(
                name=repo_name,
                private=True,
                description=f"Infrastructure for {project_name}",
            )
        except GitHubError:
            return None

        record = GitHubRepo(
            account_id=self._account_id,
            project_name=project_name,
            repo_full_name=created["full_name"],
            branch=base.branch,
            token=base.token,
            api_url=base.api_url,
            infrastructure_base_path=base.infrastructure_base_path,
        )
        self._db.add(record)
        await self._db.flush()
        return record

    @staticmethod
    def _lifecycle_days(retention_policy: str) -> tuple[int, int, int]:
        """Return (transition_to_ia_days, transition_to_glacier_days, expiration_days)."""
        return {
            "30-day":     (0,  0,  30),
            "90-day":     (30, 0,  90),
            "1-year":     (30, 90, 365),
            "7-year":     (30, 90, 2555),
            "indefinite": (30, 90, 0),
        }.get(retention_policy, (30, 90, 365))

    async def _get_account(self) -> "Account | None":
        result = await self._db.execute(
            select(Account).where(Account.id == self._account_id)
        )
        return result.scalar_one_or_none()

    async def _get_project(self, project_name: str) -> "Project | None":
        result = await self._db.execute(
            select(Project).where(
                Project.account_id == self._account_id,
                Project.name == project_name,
            )
        )
        return result.scalar_one_or_none()

    async def _get_github_repo(self, project_name: str) -> "GitHubRepo | None":
        result = await self._db.execute(
            select(GitHubRepo).where(
                GitHubRepo.account_id == self._account_id,
                GitHubRepo.project_name == project_name,
            )
        )
        return result.scalar_one_or_none()

    async def _get_snowflake_creds(self, project_name: str) -> "SnowflakeCredentials | None":
        result = await self._db.execute(
            select(SnowflakeCredentials).where(
                SnowflakeCredentials.account_id == self._account_id,
                SnowflakeCredentials.project_name == project_name,
            )
        )
        return result.scalar_one_or_none()

    def _copy_modules(self, upload_root: Path) -> None:
        for rel_path in (
            "aws/landing-zone",
            "snowflake/database",
            "snowflake/medallion-arch",
            "snowflake/s3-storage-integration",
        ):
            src = TERRAFORM_MODULES_DIR / rel_path
            dst = upload_root / "modules" / rel_path
            if src.exists():
                os.makedirs(dst.parent, exist_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)

    def _write_root_hcl(
        self,
        upload_root: Path,
        name: str,
        region: str,
        tags: dict,
    ) -> None:
        extra_tags_hcl = "\n".join(f'    {k} = "{v}"' for k, v in tags.items())

        root_tg = upload_root / "terragrunt.hcl"
        if not root_tg.exists():
            root_tg.write_text(templates.root())

        global_hcl = upload_root / "global.hcl"
        if not global_hcl.exists():
            global_hcl.write_text(templates.global_hcl(name, extra_tags_hcl))

        account_hcl = upload_root / "account.hcl"
        if not account_hcl.exists():
            account_hcl.write_text(templates.account_hcl())
