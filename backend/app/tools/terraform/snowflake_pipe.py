import re
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
from app.services.module_versions_service import module_source_dir


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
            "Retrofit Snowpipe auto-ingest onto a landing zone that was already created without it. "
            "Creates the target Bronze table (RAW_DATA VARIANT, SOURCE_FILE, LOAD_TIMESTAMP) and a "
            "Snowflake pipe that automatically ingests files dropped into the landing zone S3 bucket "
            "into it. Terraform owns only this raw ingestion shape — Silver/Gold modeling from the "
            "Bronze table onward is dbt's responsibility, not Terraform's. "
            "The target database/schema are always derived via Terragrunt dependency blocks — resolved "
            "automatically from whichever database this landing zone actually attaches to (its own "
            "{name}-db/{name}-db-arch normally, or another landing zone's if this one was created with "
            "existing_database_landing_zone set) — never pass or guess literal Snowflake identifiers, "
            "since the actual names are transformed by those modules (uppercased, and the schema is "
            "suffixed with its data classification, e.g. bronze -> BRONZE_CONFIDENTIAL) and guessing "
            "them wrong fails at apply time with a Snowflake 'object does not exist' error. "
            "If you're creating a brand-new landing zone and it also needs Snowpipe, prefer passing "
            "create_snowpipe=true directly to create_landing_zone instead of calling this afterward. "
            "Always ask the user which stack(s) this should apply to before calling — don't assume. "
            "If they say 'all', 'every environment', or have no preference, proceed without "
            "stack_name (applies to every stack configured on the account — this is the default "
            "when they don't care). If they name a specific one (e.g. 'only in dev'), pass "
            "stack_name for it. Getting this wrong silently changes every other stack too. "
            "Requires confirmation: call once with confirm omitted (or false) to get a plain-language "
            "preview of exactly what will be created and which stack(s) it targets — show that to the "
            "user verbatim and wait for them to explicitly confirm in their next message. Only call "
            "again with confirm=true, passing the exact same arguments as the preview call, after the "
            "user has clearly agreed. Never set confirm=true on the first call."
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
                    "description": "Restrict this to a single stack (e.g. 'dev'). Prefer stack_names "
                    "(plural) when you have it from a UI selection; this remains for a plain-language "
                    "single-stack request. Omit both when the user explicitly wants it added to every "
                    "stack on the account.",
                },
                "stack_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict this to a specific subset of stacks (e.g. ['dev', "
                    "'staging']) — one or more, but not necessarily all. Takes precedence over "
                    "stack_name if both are given. Omit (and omit stack_name) when the user wants "
                    "every stack on the account, which is the default when they have no preference.",
                },
                "target_table": {
                    "type": "string",
                    "description": "Unqualified name for the Bronze table this creates (e.g. RAW_EVENTS). "
                    "Terraform creates this table with a fixed RAW_DATA VARIANT / SOURCE_FILE / "
                    "LOAD_TIMESTAMP shape and loads it via the pipe's COPY INTO — it must not already exist.",
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
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Leave false (or omit) to preview what will be created without "
                    "opening a PR. Only set true after the user has explicitly confirmed the preview.",
                },
            },
            "required": ["name", "target_table"],
        }

    async def execute(
        self,
        name: str,
        target_table: str,
        stack_name: str | None = None,
        stack_names: list[str] | None = None,
        filter_prefix: str = "",
        filter_suffix: str = "",
        confirm: bool = False,
    ) -> str:
        all_stacks_result = await self._db.execute(
            select(Stack).where(Stack.account_id == self._account_id).order_by(Stack.sort_order)
        )
        all_stacks = list(all_stacks_result.scalars().all())
        if not all_stacks:
            return "No stacks configured for this account. Add one under Admin → Stacks first."

        if stack_names:
            stacks = [s for s in all_stacks if s.name in stack_names]
            missing = set(stack_names) - {s.name for s in stacks}
            if missing:
                return f"No stack(s) named {', '.join(sorted(missing))} found for this account."
        elif stack_name:
            stacks = [s for s in all_stacks if s.name == stack_name]
            if not stacks:
                return f"No stack named '{stack_name}' found for this account."
        else:
            stacks = all_stacks
        stack_names = [s.name for s in stacks]

        if not confirm:
            return (
                f"This will add Snowpipe auto-ingest to landing zone '{name}' on "
                f"{', '.join(stack_names)}:\n\n"
                f"  Bronze table: {target_table} (RAW_DATA VARIANT, SOURCE_FILE, LOAD_TIMESTAMP)\n"
                f"  Filter:       prefix='{filter_prefix}' suffix='{filter_suffix}'\n\n"
                "Reply to confirm and I'll open the PR."
            )

        repo_record = await self._get_github_repo()

        with tempfile.TemporaryDirectory() as staging:
            staging_path = Path(staging)

            # Sourced from the same versioned modules tree as the rest of the
            # landing zone — one shared module_version per account (mirrors
            # LandingZoneTool._copy_modules).
            module_version = repo_record.module_version if repo_record else "1.0.0"
            src = module_source_dir(module_version) / "aws" / "snowflake-pipe"
            if src.exists():
                shutil.copytree(src, staging_path / "modules" / "aws" / "snowflake-pipe")

            for env in stack_names:
                # This landing zone may have been created with
                # existing_database_landing_zone set, in which case it has no
                # {name}-db/-db-arch of its own — read its {name}-si to find out
                # which landing zone's database it actually attaches to, so this
                # pipe's Bronze table lands in the right place instead of
                # pointing at a {name}-db that was never created.
                db_landing_zone = await self._resolve_db_landing_zone(name, repo_record, env)
                pipe_dir = staging_path / env / "landing-zone" / f"{name}-pipe"
                pipe_dir.mkdir(parents=True, exist_ok=True)
                (pipe_dir / "terragrunt.hcl").write_text(
                    templates.pipe_from_landing_zone(
                        name=name,
                        target_table=target_table,
                        filter_prefix=filter_prefix,
                        filter_suffix=filter_suffix,
                        db_landing_zone=db_landing_zone,
                    )
                )

            verify_error = await self._verify_stacks(name, staging_path, stacks)
            if verify_error:
                return verify_error

            github_section = await self._open_pr(
                name=name,
                staging_path=staging_path,
                target_table=target_table,
                stack_names=stack_names,
            )

        return (
            f"Snowpipe added to '{name}' landing zone\n\n"
            f"  Database/schema: derived via dependency blocks (this landing zone's own database, or "
            f"a reused one if it was created with existing_database_landing_zone)\n"
            f"  Bronze table:    {target_table} (RAW_DATA VARIANT, SOURCE_FILE, LOAD_TIMESTAMP — created by Terraform)\n"
            f"  Filter:          prefix='{filter_prefix}' suffix='{filter_suffix}'\n"
            f"{github_section}\n"
            f"To deploy:\n"
            f"  terragrunt run-all apply --terragrunt-working-dir {stack_names[0]}/landing-zone/{name}-pipe"
        )

    async def _get_github_repo(self) -> "GitHubRepo | None":
        result = await self._db.execute(select(GitHubRepo).where(GitHubRepo.account_id == self._account_id))
        return result.scalar_one_or_none()

    async def _resolve_db_landing_zone(
        self, name: str, repo_record: "GitHubRepo | None", env: str
    ) -> str:
        """Best-effort: read {name}-si's own dependency block to find which
        landing zone's {*-db}/{*-db-arch} it's actually wired to. Falls back to
        `name` itself (the common case, and also the safe fallback whenever this
        can't be determined) rather than raising — a failed lookup here shouldn't
        block adding a pipe."""
        if repo_record is None:
            return name
        svc = GitHubService(
            token=repo_record.token,
            repo_full_name=repo_record.repo_full_name,
            branch=repo_record.branch,
            api_url=repo_record.api_url,
            base_path=repo_record.infrastructure_base_path,
        )
        try:
            content = await svc.get_file_content(f"{env}/landing-zone/{name}-si/terragrunt.hcl")
        except GitHubError:
            return name
        if not content:
            return name
        match = re.search(r'dependency\s+"db"\s*\{\s*config_path\s*=\s*"\.\./([\w.-]+)-db"', content)
        return match.group(1) if match else name

    async def _verify_stacks(self, name: str, staging_path: Path, stacks: list[Stack]) -> str | None:
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

        clone_dir = tempfile.mkdtemp(prefix="pipe-verify-")
        try:
            clone_url = f"https://{repo.token}@github.com/{repo.repo_full_name}.git"
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", repo.branch, clone_url, clone_dir],
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
        target_table: str,
        stack_names: list[str],
    ) -> str:
        result = await self._db.execute(select(GitHubRepo).where(GitHubRepo.account_id == self._account_id))
        record = result.scalar_one_or_none()
        if not record:
            return "\n  GitHub: no repo connected for this project — use POST /api/v1/github/repos first\n"

        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        feature_branch = f"feat/{name}-snowpipe-{slug}"
        commit_message = (
            f"feat(snowpipe): add {name} auto-ingest pipe\n\n"
            f"- Target: {name}-db / {name}-db-arch . {target_table}\n"
            f"- Stacks: {', '.join(stack_names)}"
        )
        pr_title = f"feat(snowpipe): add {name} auto-ingest pipe"
        pr_body = (
            f"## Summary\n\n"
            f"Adds Snowpipe auto-ingest for the `{name}` landing zone.\n\n"
            f"- **Bronze table** `{target_table}` created by Terraform in `{name}-db` / `{name}-db-arch`'s "
            f"own database/schema (resolved via dependency blocks, not hardcoded) with a fixed "
            f"`RAW_DATA VARIANT`, `SOURCE_FILE`, `LOAD_TIMESTAMP` shape — Silver/Gold modeling from here "
            f"is dbt's responsibility, not Terraform's\n"
            f"- **Pipe** auto-ingests files from the `{name}` S3 bucket into that table\n"
            f"- S3 event notifications wired to Snowpipe's managed SQS queue\n\n"
            f"## Test plan\n\n"
            f"- [ ] `terragrunt validate` passes in `{stack_names[0]}/landing-zone/{name}-pipe`\n"
            f"- [ ] `terragrunt plan` shows `snowflake_table`, `snowflake_pipe`, and `aws_s3_bucket_notification`\n"
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
            if pr_url is None:
                return f"\n  GitHub: no changes — {record.repo_full_name} already matches this config, no PR opened\n"
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
