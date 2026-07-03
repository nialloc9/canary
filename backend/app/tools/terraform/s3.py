import os
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
import app.tools.terraform.templates as templates
from app.tools.terraform.verify import verify_stack_plan
from app.models.project import GitHubRepo, Project
from app.models.stack import Stack, StackStateBackend
from app.services.github_service import GitHubService, GitHubError
from app.services.aws_secrets_service import get_landing_zone_access_keys
from app.services.module_versions_service import MODULE_COMPONENTS, module_source_dir


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
            "terragrunt configs for every stack configured on the account, with "
            "{name}-db, {name}-db-arch, and {name}-lz folders wired together via "
            "dependencies. Requires data classification, retention policy, and "
            "data owner."
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
        kms_key_arn: str = "",
        existing_s3_bucket_arn: str = "",
        s3_stage_prefix: str = "data/",
        file_format_type: str = "JSON",
        create_access_keys: bool = False,
        schema_names: list[str] = None,
        tags: dict = {},
        _action: str = "add",
        _target_stack_names: list[str] | None = None,
    ) -> str:
        if schema_names is None:
            schema_names = ["bronze", "silver", "gold", "platinum"]

        transition_to_ia_days, transition_to_glacier_days, expiration_days = (
            self._lifecycle_days(retention_policy)
        )

        upload_root = Path(__file__).resolve().parents[3] / "upload" / name
        shutil.rmtree(upload_root, ignore_errors=True)
        os.makedirs(upload_root)

        project = await self._get_project()
        if project is None:
            return "No project found for this account. Connect a GitHub repo first via POST /api/v1/github/repos."
        if not project.version_control_created:
            return "GitHub repo not yet connected. Use POST /api/v1/github/repos."
        repo_record = await self._get_github_repo()

        if not project.infrastructure_bootstrapped and not (repo_record and repo_record.skip_bootstrap):
            return (
                "Infrastructure not yet bootstrapped. Call POST /api/v1/projects/bootstrap first."
            )

        if repo_record and repo_record.create_cicd and not project.cicd_created:
            return (
                "CI/CD not yet created. Call POST /api/v1/projects/cicd first."
            )

        stacks_result = await self._db.execute(
            select(Stack).where(Stack.account_id == self._account_id).order_by(Stack.sort_order)
        )
        stacks = list(stacks_result.scalars().all())
        if not stacks:
            return "No stacks configured for this account. Add one under Admin → Stacks first."

        if _target_stack_names:
            stacks = [s for s in stacks if s.name in _target_stack_names]
            missing = set(_target_stack_names) - {s.name for s in stacks}
            if missing:
                return f"No stack(s) named {', '.join(sorted(missing))} found for this account."

        state_backend_by_stack: dict[str, StackStateBackend] = {}
        if repo_record:
            sb_result = await self._db.execute(
                select(StackStateBackend).where(StackStateBackend.github_repo_id == repo_record.id)
            )
            state_backend_by_stack = {r.stack_id: r for r in sb_result.scalars().all()}

        state_configs = {
            s.name: {
                "bucket": (state_backend_by_stack[s.id].state_bucket if s.id in state_backend_by_stack else None)
                or f"{project.name}-{s.name}-terraform-state",
                "region": (state_backend_by_stack[s.id].state_region if s.id in state_backend_by_stack else None)
                or region,
                "lock_table": (state_backend_by_stack[s.id].state_lock_table if s.id in state_backend_by_stack else None)
                or f"{project.name}-{s.name}-terraform-lock",
            }
            for s in stacks
        }
        stack_names = [s.name for s in stacks]

        if not (repo_record and repo_record.skip_module_import):
            # Modules land on whichever branch(es) this call targets and are
            # committed there — dev and prod naturally end up with independent
            # copies (different branches), only converging once promoted via
            # the release flow. Use the first targeted stack's pinned version
            # as representative for this PR.
            self._copy_modules(upload_root, stacks[0].module_version)
        if not (repo_record and repo_record.skip_bootstrap):
            self._write_root_hcl(upload_root, name, region, tags)

        schemas_hcl = ", ".join(f'"{s}"' for s in schema_names)

        for env in stack_names:
            sc = state_configs[env]
            env_top_dir = upload_root / env
            env_dir = env_top_dir / "landing-zone"
            os.makedirs(env_dir, exist_ok=True)

            (env_top_dir / "env.hcl").write_text(templates.env_hcl(
                project.name, env,
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
                    project_code=project.name,
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

        verify_failures: list[str] = []
        for s in stacks:
            if not s.verify_before_pr:
                continue
            result = await verify_stack_plan(upload_root / s.name, s, max_attempts=s.verify_max_attempts)
            if not result.ok:
                verify_failures.append(
                    f"Stack '{s.name}' failed `terragrunt plan` after {result.attempts} attempt(s):\n"
                    f"{result.log[-2000:]}"
                )

        if verify_failures:
            return (
                "Landing zone generated but failed pre-PR verification — no PR was opened.\n\n"
                + "\n\n".join(verify_failures)
                + "\n\nFix the issue and try again, or disable 'Verify before PR' for the affected "
                "stack(s) in Admin → Stacks."
            )

        # A landing-zone PR normally targets the repo's account-level default
        # branch — but each stack's content actually lives on that stack's own
        # branch (e.g. dev -> develop, prod -> main). When this call is scoped
        # to exactly one stack, target that stack's branch instead, so the PR
        # actually lands where the stack's existing content already lives.
        target_branch = stacks[0].branch if _target_stack_names and len(stacks) == 1 else None

        github_section = await self._open_github_pr(
            landing_zone_name=name,
            upload_root=upload_root,
            data_classification=data_classification,
            retention_policy=retention_policy,
            schema_names=schema_names,
            stack_names=stack_names,
            action=_action,
            target_branch=target_branch,
        )

        access_keys_section = (
            await self._access_keys_section(name, project.name, stacks) if create_access_keys else ""
        )

        stack_structure = "\n".join(
            f"    {stack_name}/landing-zone/\n"
            f"      {name}-db/\n"
            f"      {name}-db-arch/\n"
            f"      {name}-lz/\n"
            f"      {name}-si/"
            for stack_name in stack_names
        )
        first_stack = stack_names[0]

        return (
            f"Landing zone ready at {upload_root}\n\n"
            f"  Data classification: {data_classification}\n"
            f"  Retention policy:    {retention_policy}\n"
            f"  Data owner:          {data_owner}\n"
            f"  Schemas:             {', '.join(schema_names)}\n\n"
            f"Structure:\n"
            f"  upload/{name}/\n"
            f"    modules/ (version {stacks[0].module_version})\n"
            f"      aws/landing-zone/\n"
            f"      aws/secret/\n"
            f"      snowflake/database/\n"
            f"      snowflake/medallion-arch/\n"
            f"      snowflake/s3-storage-integration/\n"
            f"    terragrunt.hcl        (root config)\n"
            f"    global.hcl\n"
            f"{stack_structure}\n"
            f"{github_section}\n"
            f"{access_keys_section}"
            f"To deploy ({first_stack}):\n"
            f"  terragrunt run-all plan  --terragrunt-working-dir {first_stack}/landing-zone\n"
            f"  terragrunt run-all apply --terragrunt-working-dir {first_stack}/landing-zone"
        )

    async def _open_github_pr(
        self,
        landing_zone_name: str,
        upload_root: Path,
        data_classification: str,
        retention_policy: str,
        schema_names: list[str],
        stack_names: list[str],
        action: str = "add",
        target_branch: str | None = None,
    ) -> str:
        record = await self._get_github_repo()
        if not record:
            return "\n  GitHub: no repo connected — use POST /api/v1/github/repos to connect one first\n\n"

        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        conv_type = "feat" if action == "add" else "chore"
        feature_branch = f"{conv_type}/{landing_zone_name}-landing-zone-{slug}"

        commit_message = (
            f"{conv_type}(landing-zone): {action} {landing_zone_name} landing zone\n\n"
            f"- Data classification: {data_classification}\n"
            f"- Retention policy: {retention_policy}\n"
            f"- Schemas: {', '.join(schema_names)}\n"
            f"- Stacks: {', '.join(stack_names)}"
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
            f"| Stacks | {', '.join(f'`{s}`' for s in stack_names)} |\n\n"
            f"## Test plan\n\n"
            f"- [ ] `terragrunt run-all validate` passes in `{stack_names[0]}/landing-zone`\n"
            f"- [ ] `terragrunt run-all plan` shows expected resources\n"
            f"- [ ] Apply to earlier stacks before later ones (`{'` → `'.join(stack_names)}`)\n\n"
            f"---\n"
            f"🤖 Generated by Canary"
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
                local_dir=upload_root,
                feature_branch=feature_branch,
                commit_message=commit_message,
                pr_title=pr_title,
                pr_body=pr_body,
            )
            if pr_url is None:
                return f"\n  GitHub: no changes — {record.repo_full_name} already matches this config, no PR opened\n\n"
            if record.auto_merge:
                pr_number = int(pr_url.rstrip("/").split("/")[-1])
                await svc.merge_pull_request(pr_number)
                return (
                    f"\n  GitHub: merged PR #{pr_number} with {file_count} files → {record.repo_full_name}\n"
                    f"  Branch: {feature_branch} → {base_branch}\n"
                    f"  PR:     {pr_url} (merged)\n\n"
                )
            return (
                f"\n  GitHub: opened PR with {file_count} files → {record.repo_full_name}\n"
                f"  Branch: {feature_branch} → {base_branch}\n"
                f"  PR:     {pr_url}\n\n"
            )
        except GitHubError as exc:
            return f"\n  GitHub: PR failed — {exc}\n\n"

    async def _access_keys_section(self, landing_zone_name: str, project_name: str, stacks: list[Stack]) -> str:
        """Best-effort: the keys only exist in Secrets Manager once this PR is
        merged and applied, which doesn't happen synchronously here — so this
        either reports the real values (re-running on an already-deployed
        landing zone) or tells the user to ask again once it's live."""
        lines = ["Access keys (from AWS Secrets Manager):"]
        any_found = False
        for stack in stacks:
            keys = await get_landing_zone_access_keys(stack, project_name, landing_zone_name)
            if keys is None:
                lines.append(f"  {stack.name}: not available yet — ask me again once this PR is merged and applied.")
            else:
                any_found = True
                lines.append(
                    f"  {stack.name}:\n"
                    f"    Access key ID:     {keys['access_key_id']}\n"
                    f"    Secret access key: {keys['secret_access_key']}"
                )
        if not any_found:
            lines = [
                "Access keys: not available yet — this PR needs to be merged and applied first. "
                "Ask me for the access keys again once that's done."
            ]
        return "\n".join(lines) + "\n\n"

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

    async def _get_project(self) -> "Project | None":
        result = await self._db.execute(select(Project).where(Project.account_id == self._account_id))
        return result.scalar_one_or_none()

    async def _get_github_repo(self) -> "GitHubRepo | None":
        result = await self._db.execute(select(GitHubRepo).where(GitHubRepo.account_id == self._account_id))
        return result.scalar_one_or_none()

    def _copy_modules(self, upload_root: Path, module_version: str) -> None:
        version_dir = module_source_dir(module_version)
        for rel_path in MODULE_COMPONENTS:
            src = version_dir / rel_path
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
