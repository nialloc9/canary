import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
import app.tools.terraform.templates as templates
from app.models.project import GitHubRepo, SnowflakeCredentials
from app.services.github_service import GitHubService, GitHubError

MODULES_DIR = Path(__file__).resolve().parents[4] / "terraform" / "modules" / "aws"


class SnowflakePipeTool(BaseTool):

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "create_snowflake_pipe"

    @property
    def description(self) -> str:
        return (
            "Add Snowpipe auto-ingest to an existing landing zone. "
            "Creates a Snowflake pipe that automatically ingests files dropped "
            "into the landing zone S3 bucket into a target Snowflake table. "
            "Generates terragrunt config for dev and prod and opens a GitHub PR."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Landing zone name to attach the pipe to (must match an existing landing zone)",
                },
                "project_code": {
                    "type": "string",
                    "description": "Project code used to look up the GitHub repo connection",
                },
                "snowflake_database": {
                    "type": "string",
                    "description": "Snowflake database that contains the target schema and table",
                },
                "snowflake_schema": {
                    "type": "string",
                    "description": "Snowflake schema that contains the target table",
                },
                "target_table": {
                    "type": "string",
                    "description": "Unqualified target table name for COPY INTO (e.g. RAW_DATA)",
                },
                "filter_prefix": {
                    "type": "string",
                    "description": "S3 key prefix to filter event notifications (optional)",
                    "default": "",
                },
                "filter_suffix": {
                    "type": "string",
                    "description": "S3 key suffix to filter event notifications, e.g. .json (optional)",
                    "default": "",
                },
            },
            "required": ["name", "project_code", "snowflake_database", "snowflake_schema", "target_table"],
        }

    async def execute(
        self,
        name: str,
        project_code: str,
        snowflake_database: str,
        snowflake_schema: str,
        target_table: str,
        filter_prefix: str = "",
        filter_suffix: str = "",
    ) -> str:
        with tempfile.TemporaryDirectory() as staging:
            staging_path = Path(staging)

            src = MODULES_DIR / "snowflake-pipe"
            if src.exists():
                shutil.copytree(src, staging_path / "modules" / "aws" / "snowflake-pipe")

            for env in ("dev", "prod"):
                pipe_dir = staging_path / env / "landing-zone" / f"{name}-pipe"
                pipe_dir.mkdir(parents=True, exist_ok=True)
                (pipe_dir / "terragrunt.hcl").write_text(
                    templates.pipe(
                        name=name,
                        snowflake_database=snowflake_database,
                        snowflake_schema=snowflake_schema,
                        target_table=target_table,
                        filter_prefix=filter_prefix,
                        filter_suffix=filter_suffix,
                    )
                )

            github_section = await self._open_pr(
                project_code=project_code,
                name=name,
                staging_path=staging_path,
                snowflake_database=snowflake_database,
                snowflake_schema=snowflake_schema,
                target_table=target_table,
            )

        return (
            f"Snowpipe added to '{name}' landing zone\n\n"
            f"  Database:     {snowflake_database}\n"
            f"  Schema:       {snowflake_schema}\n"
            f"  Target table: {target_table}\n"
            f"  Filter:       prefix='{filter_prefix}' suffix='{filter_suffix}'\n"
            f"{github_section}\n"
            f"To deploy:\n"
            f"  terragrunt run-all apply --terragrunt-working-dir dev/landing-zone/{name}-pipe"
        )

    async def _get_snowflake_creds(self, project_name: str) -> "SnowflakeCredentials | None":
        result = await self._db.execute(
            select(SnowflakeCredentials).where(
                SnowflakeCredentials.account_id == self._account_id,
                SnowflakeCredentials.project_name == project_name,
            )
        )
        return result.scalar_one_or_none()

    async def _open_pr(
        self,
        project_code: str,
        name: str,
        staging_path: Path,
        snowflake_database: str,
        snowflake_schema: str,
        target_table: str,
    ) -> str:
        result = await self._db.execute(
            select(GitHubRepo).where(
                GitHubRepo.account_id == self._account_id,
                GitHubRepo.project_name == project_code,
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return "\n  GitHub: no repo connected for this project — use POST /api/v1/github/repos first\n"

        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        feature_branch = f"feat/{name}-snowpipe-{slug}"
        commit_message = (
            f"feat(snowpipe): add {name} auto-ingest pipe\n\n"
            f"- Target: {snowflake_database}.{snowflake_schema}.{target_table}\n"
            f"- Environments: dev, prod"
        )
        pr_title = f"feat(snowpipe): add {name} auto-ingest pipe"
        pr_body = (
            f"## Summary\n\n"
            f"Adds Snowpipe auto-ingest for the `{name}` landing zone.\n\n"
            f"- **Pipe** auto-ingests files from the `{name}` S3 bucket into "
            f"`{snowflake_database}.{snowflake_schema}.{target_table}`\n"
            f"- S3 event notifications wired to Snowpipe's managed SQS queue\n\n"
            f"## Test plan\n\n"
            f"- [ ] `terragrunt validate` passes in `dev/landing-zone/{name}-pipe`\n"
            f"- [ ] `terragrunt plan` shows `snowflake_pipe` and `aws_s3_bucket_notification`\n"
            f"- [ ] Drop a test file into the bucket and confirm it appears in `{target_table}`\n\n"
            f"---\n🤖 Generated by Canary"
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
                local_dir=staging_path,
                feature_branch=feature_branch,
                commit_message=commit_message,
                pr_title=pr_title,
                pr_body=pr_body,
            )
            if record.auto_merge:
                pr_number = int(pr_url.rstrip("/").split("/")[-1])
                await svc.merge_pull_request(pr_number)
                return (
                    f"\n  GitHub: merged PR #{pr_number} with {file_count} files\n"
                    f"  Branch: {feature_branch} → {record.branch}\n"
                    f"  PR:     {pr_url} (merged)\n"
                )
            return (
                f"\n  GitHub: opened PR with {file_count} files\n"
                f"  Branch: {feature_branch} → {record.branch}\n"
                f"  PR:     {pr_url}\n"
            )
        except GitHubError as exc:
            return f"\n  GitHub: PR failed — {exc}\n"
