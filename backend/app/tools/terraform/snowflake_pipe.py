import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
import app.tools.terraform.templates as templates
from app.tools.terraform.verify import verify_stack_plan
from app.models.project import GitHubRepo
from app.models.stack import Stack
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
            "By default this applies to every stack configured on the account — always pass "
            "stack_name when the user's request is specific to one environment (e.g. 'only in dev'), "
            "otherwise you will silently change every other stack too."
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
                "stack_name": {
                    "type": "string",
                    "description": "Restrict this to a single stack (e.g. 'dev'). Required whenever the "
                    "request is scoped to one environment. Omit only when the user explicitly wants it "
                    "added to every stack on the account.",
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
            "required": ["name", "snowflake_database", "snowflake_schema", "target_table"],
        }

    async def execute(
        self,
        name: str,
        snowflake_database: str,
        snowflake_schema: str,
        target_table: str,
        stack_name: str | None = None,
        filter_prefix: str = "",
        filter_suffix: str = "",
    ) -> str:
        all_stacks_result = await self._db.execute(
            select(Stack).where(Stack.account_id == self._account_id).order_by(Stack.sort_order)
        )
        all_stacks = list(all_stacks_result.scalars().all())
        if not all_stacks:
            return "No stacks configured for this account. Add one under Admin → Stacks first."

        if stack_name:
            stacks = [s for s in all_stacks if s.name == stack_name]
            if not stacks:
                return f"No stack named '{stack_name}' found for this account."
        else:
            stacks = all_stacks
        stack_names = [s.name for s in stacks]
        target_branch = stacks[0].branch if stack_name and len(stacks) == 1 else None

        with tempfile.TemporaryDirectory() as staging:
            staging_path = Path(staging)

            src = MODULES_DIR / "snowflake-pipe"
            if src.exists():
                shutil.copytree(src, staging_path / "modules" / "aws" / "snowflake-pipe")

            for env in stack_names:
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

            verify_error = await self._verify_stacks(name, staging_path, stacks, target_branch)
            if verify_error:
                return verify_error

            github_section = await self._open_pr(
                name=name,
                staging_path=staging_path,
                snowflake_database=snowflake_database,
                snowflake_schema=snowflake_schema,
                target_table=target_table,
                stack_names=stack_names,
                target_branch=target_branch,
            )

        return (
            f"Snowpipe added to '{name}' landing zone\n\n"
            f"  Database:     {snowflake_database}\n"
            f"  Schema:       {snowflake_schema}\n"
            f"  Target table: {target_table}\n"
            f"  Filter:       prefix='{filter_prefix}' suffix='{filter_suffix}'\n"
            f"{github_section}\n"
            f"To deploy:\n"
            f"  terragrunt run-all apply --terragrunt-working-dir {stack_names[0]}/landing-zone/{name}-pipe"
        )

    async def _verify_stacks(
        self, name: str, staging_path: Path, stacks: list[Stack], target_branch: str | None = None
    ) -> str | None:
        """Run terragrunt plan for any stack with verify_before_pr enabled before opening a PR.

        Unlike a fresh landing zone, a pipe is added to an *existing* repo tree — the
        generated pipe config alone has no root terragrunt.hcl/account.hcl to resolve
        against, so we clone the real repo and merge the new files in before planning.
        Returns an error string if verification fails (in which case no PR should be
        opened), or None if everything passed / nothing needed checking.
        """
        to_verify = [s for s in stacks if s.verify_before_pr]
        if not to_verify:
            return None

        result = await self._db.execute(select(GitHubRepo).where(GitHubRepo.account_id == self._account_id))
        repo = result.scalar_one_or_none()
        if not repo:
            return None  # no repo connected yet — _open_pr will report that clearly

        # Each stack's content actually lives on that stack's own branch (e.g.
        # dev -> develop) — only fall back to the repo's account-level default
        # when verifying across multiple stacks with potentially different branches.
        clone_branch = target_branch or repo.branch

        clone_dir = tempfile.mkdtemp(prefix="pipe-verify-")
        try:
            clone_url = f"https://{repo.token}@github.com/{repo.repo_full_name}.git"
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", clone_branch, clone_url, clone_dir],
                check=True,
                capture_output=True,
            )

            base = Path(clone_dir) / repo.infrastructure_base_path
            failures: list[str] = []
            for s in to_verify:
                src_pipe_dir = staging_path / s.name / "landing-zone" / f"{name}-pipe"
                dst_pipe_dir = base / s.name / "landing-zone" / f"{name}-pipe"
                if not src_pipe_dir.exists():
                    continue
                shutil.copytree(src_pipe_dir, dst_pipe_dir, dirs_exist_ok=True)

                src_module = staging_path / "modules" / "aws" / "snowflake-pipe"
                dst_module = base / "modules" / "aws" / "snowflake-pipe"
                if src_module.exists():
                    shutil.copytree(src_module, dst_module, dirs_exist_ok=True)

                result = await verify_stack_plan(base / s.name, s, max_attempts=s.verify_max_attempts)
                if not result.ok:
                    failures.append(
                        f"Stack '{s.name}' failed `terragrunt plan` after {result.attempts} attempt(s):\n"
                        f"{result.log[-2000:]}"
                    )

            if failures:
                return (
                    "Snowpipe config generated but failed pre-PR verification — no PR was opened.\n\n"
                    + "\n\n".join(failures)
                    + "\n\nFix the issue and try again, or disable 'Verify before PR' for the affected "
                    "stack(s) in Admin → Stacks."
                )
            return None
        except subprocess.CalledProcessError as exc:
            return f"Could not verify: failed to clone {repo.repo_full_name}: {exc.stderr.decode()}"
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    async def _open_pr(
        self,
        name: str,
        staging_path: Path,
        snowflake_database: str,
        snowflake_schema: str,
        target_table: str,
        stack_names: list[str],
        target_branch: str | None = None,
    ) -> str:
        result = await self._db.execute(select(GitHubRepo).where(GitHubRepo.account_id == self._account_id))
        record = result.scalar_one_or_none()
        if not record:
            return "\n  GitHub: no repo connected for this project — use POST /api/v1/github/repos first\n"

        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        feature_branch = f"feat/{name}-snowpipe-{slug}"
        commit_message = (
            f"feat(snowpipe): add {name} auto-ingest pipe\n\n"
            f"- Target: {snowflake_database}.{snowflake_schema}.{target_table}\n"
            f"- Stacks: {', '.join(stack_names)}"
        )
        pr_title = f"feat(snowpipe): add {name} auto-ingest pipe"
        pr_body = (
            f"## Summary\n\n"
            f"Adds Snowpipe auto-ingest for the `{name}` landing zone.\n\n"
            f"- **Pipe** auto-ingests files from the `{name}` S3 bucket into "
            f"`{snowflake_database}.{snowflake_schema}.{target_table}`\n"
            f"- S3 event notifications wired to Snowpipe's managed SQS queue\n\n"
            f"## Test plan\n\n"
            f"- [ ] `terragrunt validate` passes in `{stack_names[0]}/landing-zone/{name}-pipe`\n"
            f"- [ ] `terragrunt plan` shows `snowflake_pipe` and `aws_s3_bucket_notification`\n"
            f"- [ ] Drop a test file into the bucket and confirm it appears in `{target_table}`\n\n"
            f"---\n🤖 Generated by Canary"
        )

        base_branch = target_branch or record.branch
        svc = GitHubService(
            token=record.token,
            repo_full_name=record.repo_full_name,
            branch=base_branch,
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
            if pr_url is None:
                return f"\n  GitHub: no changes — {record.repo_full_name} already matches this config, no PR opened\n"
            if record.auto_merge:
                pr_number = int(pr_url.rstrip("/").split("/")[-1])
                await svc.merge_pull_request(pr_number)
                return (
                    f"\n  GitHub: merged PR #{pr_number} with {file_count} files\n"
                    f"  Branch: {feature_branch} → {base_branch}\n"
                    f"  PR:     {pr_url} (merged)\n"
                )
            return (
                f"\n  GitHub: opened PR with {file_count} files\n"
                f"  Branch: {feature_branch} → {base_branch}\n"
                f"  PR:     {pr_url}\n"
            )
        except GitHubError as exc:
            return f"\n  GitHub: PR failed — {exc}\n"
