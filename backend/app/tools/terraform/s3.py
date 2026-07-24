import os
import shutil
import tempfile
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
from app.services.module_versions_service import module_source_dir, stack_components
from app.services.data_profile_service import infer_profile, upsert_profile


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
            "data owner. "
            "Optionally also provisions Snowpipe auto-ingest in the same call — set "
            "create_snowpipe=true with a bronze_table_name and this adds a {name}-pipe "
            "component wired to this landing zone's own bucket/database/schema/stage, "
            "creating the Bronze table and loading files into it automatically. "
            "Before calling this, ask the user to describe the data that will land here and to paste in "
            "at least one representative sample file's content (sample_files, minimum 1) — file format, "
            "size expectations, and per-column details are all inferred from the sample(s) automatically "
            "if not given explicitly, and get stored against this landing zone so they never have to be "
            "asked again later (e.g. when generating dbt models from this data). Ask about individual "
            "columns too if the user has useful context to add (what each field means, valid value ranges) "
            "— pass it via columns, but it's optional; anything not supplied is inferred from the samples. "
            "By default this applies to every stack configured on the account (e.g. dev AND "
            "prod) — always pass stack_name when the request is scoped to one environment "
            "(e.g. 'add this to prod', 'only in dev'), otherwise you will silently change "
            "every other stack too, including ones that already have this landing zone "
            "deployed. "
            "When the user gives different instructions for different stacks in the same "
            "request (e.g. 'prod should reuse bucket X, dev should create its own'), use "
            "stack_overrides instead of separate calls — pass the fields common to all stacks "
            "as top-level arguments and only the differing fields inside stack_overrides."
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
                "stack_name": {
                    "type": "string",
                    "description": "Restrict this to a single stack (e.g. 'prod'). Required whenever "
                    "the request is scoped to one environment. Omit only when the user explicitly wants "
                    "this landing zone created on every stack on the account.",
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
                    "description": "Snowflake file format type. If omitted, inferred from sample_files "
                    "(falls back to JSON if it can't be determined).",
                    "enum": ["JSON", "CSV", "PARQUET", "AVRO", "ORC", "XML"],
                },
                "sample_files": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["content"],
                    },
                    "description": "At least one representative sample of the data that will land here — "
                    "paste its raw content (as text; binary formats like PARQUET/AVRO/ORC can't be inferred "
                    "this way, just describe them instead). Used to infer file_format_type, size stats, "
                    "description, and columns for anything not supplied explicitly. Ask the user for this "
                    "before calling the tool — it's required, not optional.",
                },
                "data_description": {
                    "type": "string",
                    "description": "Plain-language description of what this data represents (e.g. "
                    "'Shopify order-created webhook events'). If omitted, inferred from sample_files.",
                },
                "expected_size_bytes": {
                    "type": "integer",
                    "description": "Typical file size in bytes for this data source. If omitted, "
                    "derived from the average size of sample_files.",
                },
                "min_size_bytes": {
                    "type": "integer",
                    "description": "Smallest file size expected, in bytes. If omitted, derived from "
                    "the smallest sample_files provided.",
                },
                "max_size_bytes": {
                    "type": "integer",
                    "description": "Largest file size expected, in bytes. If omitted, derived from "
                    "the largest sample_files provided.",
                },
                "columns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"},
                            "example": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                    "description": "Known columns/fields in the data, if the user has useful context to "
                    "add beyond what the samples already show (what a field means, valid ranges, units). "
                    "Optional — anything not supplied here is inferred from sample_files.",
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
                "create_snowpipe": {
                    "type": "boolean",
                    "description": "Also provision Snowpipe auto-ingest for this landing zone: creates a "
                    "Bronze table (RAW_DATA VARIANT, SOURCE_FILE, LOAD_TIMESTAMP) in the bronze schema and "
                    "a pipe that automatically loads files dropped into the S3 bucket into it. Requires "
                    "bronze_table_name. Applies to every targeted stack the same way — use the standalone "
                    "create_snowflake_pipe tool instead if you need per-stack pipe config or are retrofitting "
                    "onto a landing zone that already exists.",
                    "default": False,
                },
                "bronze_table_name": {
                    "type": "string",
                    "description": "Unqualified name for the Bronze table Snowpipe loads into (e.g. "
                    "RAW_EVENTS). Required when create_snowpipe is true.",
                    "default": "",
                },
                "snowpipe_filter_prefix": {
                    "type": "string",
                    "description": "S3 key prefix to filter Snowpipe ingest event notifications (optional)",
                    "default": "",
                },
                "snowpipe_filter_suffix": {
                    "type": "string",
                    "description": "S3 key suffix to filter Snowpipe ingest event notifications, e.g. .json "
                    "(optional)",
                    "default": "",
                },
                "tags": {
                    "type": "object",
                    "description": "Additional key-value tags",
                    "default": {},
                },
                "stack_overrides": {
                    "type": "object",
                    "description": "Per-stack field overrides, keyed by stack name (e.g. "
                    '{"dev": {"existing_s3_bucket_arn": ""}, "prod": {"existing_s3_bucket_arn": '
                    '"arn:aws:s3:::..."}}). Only include the fields that differ for that stack — '
                    "anything omitted falls back to the top-level value for that field. Supported "
                    "keys: data_classification, retention_policy, data_owner, department, "
                    "cost_center, existing_s3_bucket_arn, kms_key_arn, s3_stage_prefix, "
                    "file_format_type, create_access_keys, schema_names.",
                    "default": {},
                },
            },
            "required": [
                "name",
                "data_classification",
                "retention_policy",
                "data_owner",
                "sample_files",
            ],
        }

    async def execute(
        self,
        name: str,
        data_classification: str,
        retention_policy: str,
        data_owner: str,
        stack_name: str | None = None,
        region: str = "eu-west-1",
        department: str = "none",
        cost_center: str = "none",
        kms_key_arn: str = "",
        existing_s3_bucket_arn: str = "",
        s3_stage_prefix: str = "data/",
        file_format_type: str | None = None,
        create_access_keys: bool = False,
        schema_names: list[str] = None,
        create_snowpipe: bool = False,
        bronze_table_name: str = "",
        snowpipe_filter_prefix: str = "",
        snowpipe_filter_suffix: str = "",
        sample_files: list[dict] | None = None,
        data_description: str | None = None,
        expected_size_bytes: int | None = None,
        min_size_bytes: int | None = None,
        max_size_bytes: int | None = None,
        columns: list[dict] | None = None,
        tags: dict = {},
        stack_overrides: dict | None = None,
        _action: str = "add",
        _target_stack_names: list[str] | None = None,
        _chat_branch: str | None = None,
    ) -> str:
        if schema_names is None:
            schema_names = ["bronze", "silver", "gold", "platinum"]
        if create_snowpipe and not bronze_table_name:
            return "create_snowpipe requires bronze_table_name (the Bronze table Snowpipe will create and load into)."
        # Only required on initial creation — update_landing_zone re-invokes this with
        # _action="update" for unrelated field changes and never has samples to hand,
        # and re-inferring/overwriting an existing profile on every unrelated update
        # would be both wrong and impossible without them.
        if _action == "add" and not sample_files:
            return (
                "sample_files is required — ask the user for at least one representative sample of the "
                "data that will land here (its raw content, pasted as text) before calling this."
            )
        if stack_name and not _target_stack_names:
            _target_stack_names = [stack_name]
        stack_overrides = stack_overrides or {}

        profile = None
        if sample_files:
            profile = await infer_profile(
                landing_zone_name=name,
                sample_files=sample_files,
                data_description=data_description,
                file_format=file_format_type,
                expected_size_bytes=expected_size_bytes,
                min_size_bytes=min_size_bytes,
                max_size_bytes=max_size_bytes,
                columns=columns,
            )
            file_format_type = profile["file_format"] or "JSON"
            await upsert_profile(self._db, self._account_id, name, profile)
        else:
            file_format_type = file_format_type or "JSON"

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

        # modules/ and the root/global/account HCL are still materialized
        # locally below (needed for `terragrunt plan` if verify_before_pr is
        # on) — but for _action == "update" only the touched landing zone's
        # own terragrunt.hcl files ever get pushed to GitHub (see the
        # `push_root` narrowing after generation, below). Bumping a stack's
        # module version and re-vendoring is a separate, explicit action
        # ("hard refresh modules"), not a side effect of an unrelated config
        # edit — this guarantees an update can never change the vendored
        # Terraform modules, only its own terragrunt config.
        if not (repo_record and repo_record.skip_module_import):
            # Modules land on whichever branch(es) this call targets and are
            # committed there — dev and prod naturally end up with independent
            # copies (different branches), only converging once promoted via
            # the release flow. Use the first targeted stack's pinned version
            # as representative for this PR.
            self._copy_modules(upload_root, stacks[0].module_version)
        if not (repo_record and repo_record.skip_bootstrap):
            self._write_root_hcl(upload_root, name, region, tags)

        resolved: dict[str, dict] = {}

        for env in stack_names:
            ov = stack_overrides.get(env, {})
            cfg = {
                "data_classification": ov.get("data_classification", data_classification),
                "retention_policy": ov.get("retention_policy", retention_policy),
                "data_owner": ov.get("data_owner", data_owner),
                "department": ov.get("department", department),
                "cost_center": ov.get("cost_center", cost_center),
                "existing_s3_bucket_arn": ov.get("existing_s3_bucket_arn", existing_s3_bucket_arn),
                "kms_key_arn": ov.get("kms_key_arn", kms_key_arn),
                "s3_stage_prefix": ov.get("s3_stage_prefix", s3_stage_prefix),
                "file_format_type": ov.get("file_format_type", file_format_type),
                "create_access_keys": ov.get("create_access_keys", create_access_keys),
                "schema_names": ov.get("schema_names", schema_names),
            }
            resolved[env] = cfg
            transition_to_ia_days, transition_to_glacier_days, expiration_days = (
                self._lifecycle_days(cfg["retention_policy"])
            )
            schemas_hcl = ", ".join(f'"{s}"' for s in cfg["schema_names"])

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
                templates.db_arch(name, cfg["data_classification"], schemas_hcl)
            )

            lz_dir = env_dir / f"{name}-lz"
            os.makedirs(lz_dir, exist_ok=True)
            (lz_dir / "terragrunt.hcl").write_text(
                templates.lz(
                    name=name,
                    env=env,
                    data_classification=cfg["data_classification"],
                    retention_policy=cfg["retention_policy"],
                    data_owner=cfg["data_owner"],
                    department=cfg["department"],
                    cost_center=cfg["cost_center"],
                    project_code=project.name,
                    create_access_keys=cfg["create_access_keys"],
                    transition_to_ia_days=transition_to_ia_days,
                    transition_to_glacier_days=transition_to_glacier_days,
                    expiration_days=expiration_days,
                    existing_s3_bucket_arn=cfg["existing_s3_bucket_arn"],
                    kms_key_arn=cfg["kms_key_arn"],
                )
            )

            si_dir = env_dir / f"{name}-si"
            os.makedirs(si_dir, exist_ok=True)
            (si_dir / "terragrunt.hcl").write_text(
                templates.si(
                    name=name,
                    s3_stage_prefix=cfg["s3_stage_prefix"],
                    file_format_type=cfg["file_format_type"],
                )
            )

            if create_snowpipe:
                pipe_dir = env_dir / f"{name}-pipe"
                os.makedirs(pipe_dir, exist_ok=True)
                (pipe_dir / "terragrunt.hcl").write_text(
                    templates.pipe_from_landing_zone(
                        name=name,
                        target_table=bronze_table_name,
                        filter_prefix=snowpipe_filter_prefix,
                        filter_suffix=snowpipe_filter_suffix,
                    )
                )

        any_create_access_keys = any(cfg["create_access_keys"] for cfg in resolved.values())

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

        # The PR always targets the branch of the stack the user is chatting
        # from (e.g. dev -> develop), regardless of which stack(s) the config
        # itself is for — content destined for prod still goes up for review
        # on the dev branch first; promotion to prod's branch happens later
        # via the separate release flow, not by pushing straight to it here.
        target_branch = _chat_branch

        # An update only ever pushes this landing zone's own terragrunt.hcl
        # files — never modules/ or the shared root/global/account HCL that
        # were regenerated into upload_root above purely so verification had
        # a complete tree to plan against.
        if _action == "add":
            push_root = upload_root
        else:
            push_root = Path(tempfile.mkdtemp(prefix="lz-update-push-"))
            for env in stack_names:
                for component in (f"{name}-db", f"{name}-db-arch", f"{name}-lz", f"{name}-si", f"{name}-pipe"):
                    src = upload_root / env / "landing-zone" / component
                    if src.exists():
                        dst = push_root / env / "landing-zone" / component
                        os.makedirs(dst.parent, exist_ok=True)
                        shutil.copytree(src, dst)

        try:
            github_section = await self._open_github_pr(
                landing_zone_name=name,
                upload_root=push_root,
                stack_configs=resolved,
                stack_names=stack_names,
                action=_action,
                target_branch=target_branch,
                create_snowpipe=create_snowpipe,
                bronze_table_name=bronze_table_name,
            )
        finally:
            if push_root != upload_root:
                shutil.rmtree(push_root, ignore_errors=True)

        access_keys_section = (
            await self._access_keys_section(name, project.name, stacks) if any_create_access_keys else ""
        )

        stack_structure = "\n".join(
            f"    {stack_name}/landing-zone/\n"
            f"      {name}-db/\n"
            f"      {name}-db-arch/\n"
            f"      {name}-lz/\n"
            f"      {name}-si/"
            + (f"\n      {name}-pipe/" if create_snowpipe else "")
            for stack_name in stack_names
        )
        first_stack = stack_names[0]

        config_summary = "\n".join(
            f"  {env}:\n"
            f"    Data classification: {resolved[env]['data_classification']}\n"
            f"    Retention policy:    {resolved[env]['retention_policy']}\n"
            f"    Data owner:          {resolved[env]['data_owner']}\n"
            f"    Schemas:             {', '.join(resolved[env]['schema_names'])}"
            + (
                f"\n    Existing bucket:     {resolved[env]['existing_s3_bucket_arn']}"
                if resolved[env]["existing_s3_bucket_arn"] else ""
            )
            for env in stack_names
        )

        snowpipe_summary = (
            f"Snowpipe:\n"
            f"  Bronze table: {bronze_table_name} (RAW_DATA VARIANT, SOURCE_FILE, LOAD_TIMESTAMP — created by Terraform)\n"
            f"  Filter:       prefix='{snowpipe_filter_prefix}' suffix='{snowpipe_filter_suffix}'\n\n"
            if create_snowpipe else ""
        )

        profile_summary = ""
        if profile:
            columns_lines = "\n".join(
                f"    - {c.get('name')} ({c.get('type', 'unknown')}): {c.get('description', '')}"
                for c in (profile.get("columns") or [])
            )
            profile_summary = (
                f"Data profile (inferred from {len(sample_files)} sample(s), stored for reuse later):\n"
                f"  Description:  {profile.get('description') or '(none)'}\n"
                f"  File format:  {file_format_type}\n"
                f"  Size (bytes): min={profile.get('min_size_bytes')} expected={profile.get('expected_size_bytes')} "
                f"max={profile.get('max_size_bytes')}\n"
                + (f"  Columns:\n{columns_lines}\n" if columns_lines else "")
                + "\n"
            )

        return (
            f"Landing zone ready at {upload_root}\n\n"
            f"{config_summary}\n\n"
            f"{snowpipe_summary}"
            f"{profile_summary}"
            f"Structure:\n"
            f"  upload/{name}/\n"
            f"    modules/ (version {stacks[0].module_version})\n"
            f"      aws/landing-zone/\n"
            f"      aws/snowflake-pipe/\n"
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
        stack_configs: dict[str, dict],
        stack_names: list[str],
        action: str = "add",
        target_branch: str | None = None,
        create_snowpipe: bool = False,
        bronze_table_name: str = "",
    ) -> str:
        record = await self._get_github_repo()
        if not record:
            return "\n  GitHub: no repo connected — use POST /api/v1/github/repos to connect one first\n\n"

        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        conv_type = "feat" if action == "add" else "chore"
        feature_branch = f"{conv_type}/{landing_zone_name}-landing-zone-{slug}"

        commit_message = (
            f"{conv_type}(landing-zone): {action} {landing_zone_name} landing zone\n\n"
            + "\n".join(
                f"- {env}: {stack_configs[env]['data_classification']}, "
                f"{stack_configs[env]['retention_policy']}, "
                f"owner={stack_configs[env]['data_owner']}"
                + (
                    f", bucket={stack_configs[env]['existing_s3_bucket_arn']}"
                    if stack_configs[env]["existing_s3_bucket_arn"] else ""
                )
                for env in stack_names
            )
        )

        pr_title = f"{conv_type}(landing-zone): {action} {landing_zone_name} landing zone"

        summary_verb = "Adds" if action == "add" else "Updates"
        config_table_rows = "\n".join(
            f"| `{env}` | `{stack_configs[env]['data_classification']}` | "
            f"`{stack_configs[env]['retention_policy']}` | {stack_configs[env]['data_owner']} | "
            f"{stack_configs[env]['existing_s3_bucket_arn'] or '_new bucket_'} | "
            f"{', '.join(f'`{s}`' for s in stack_configs[env]['schema_names'])} |"
            for env in stack_names
        )
        pr_body = (
            f"## Summary\n\n"
            f"{summary_verb} the landing zone for `{landing_zone_name}`.\n\n"
            f"- **`{landing_zone_name}-db`** — Snowflake database\n"
            f"- **`{landing_zone_name}-db-arch`** — Medallion schemas\n"
            f"- **`{landing_zone_name}-lz`** — S3 bucket\n"
            f"- **`{landing_zone_name}-si`** — Snowflake storage integration + external stage\n"
            + (
                f"- **`{landing_zone_name}-pipe`** — Snowpipe auto-ingest into Bronze table "
                f"`{bronze_table_name}` (`RAW_DATA VARIANT`, `SOURCE_FILE`, `LOAD_TIMESTAMP` — Terraform "
                f"owns only this shape; Silver/Gold modeling from here is dbt's responsibility)\n"
                if create_snowpipe else ""
            )
            + f"\n## Configuration\n\n"
            f"| Stack | Data classification | Retention policy | Data owner | Bucket | Schemas |\n"
            f"|---|---|---|---|---|---|\n"
            f"{config_table_rows}\n\n"
            f"## Test plan\n\n"
            f"- [ ] `terragrunt run-all validate` passes in `{stack_names[0]}/landing-zone`\n"
            f"- [ ] `terragrunt run-all plan` shows expected resources\n"
            + (
                f"- [ ] Drop a test file into the bucket and confirm it appears in `{bronze_table_name}`\n"
                if create_snowpipe else ""
            )
            + f"- [ ] Apply to earlier stacks before later ones (`{'` → `'.join(stack_names)}`)\n\n"
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
        stack_dir = module_source_dir(module_version)
        for rel_path in stack_components(module_version):
            src = stack_dir / rel_path
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
