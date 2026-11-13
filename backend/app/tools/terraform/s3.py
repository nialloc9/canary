import os
import re
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
from app.models.data_classification import DataClassification
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
            "medallion-arch schemas, and Snowflake storage integration, for one or more tables "
            "landing in the same bucket. Copies Terraform modules into an upload/ directory and "
            "generates terragrunt configs for every stack configured on the account, with "
            "{name}-db, {name}-db-arch, and {name}-lz folders wired together via "
            "dependencies. Requires data owner and at least one entry in `tables` for the landing zone "
            "as a whole. data_classification and retention_policy are also needed but usually don't need "
            "asking about — they fall back to this account's configured defaults (see your system "
            "context) when omitted; only ask if there's no default configured, or if a table's data "
            "looks more sensitive than the default classification's description covers. "
            "Optionally also provisions Snowpipe auto-ingest in the same call — set "
            "create_snowpipe=true and this adds one {name}-pipe component per table (the first "
            "table keeps the plain {name}-pipe folder name, additional tables get "
            "{name}-pipe-{table_name}), each wired to this landing zone's own bucket/database/"
            "schema/stage, creating that table's Bronze table and loading its files into it "
            "automatically, filtered to that table's own S3 prefix so tables never ingest each "
            "other's files. "
            "If the user hasn't already given you enough to work with in one go, ask about tables ONE AT "
            "A TIME in conversation, not all at once: for each table, collect its name, a plain-language "
            "description (or paste at least one representative sample file and it's inferred), owner, "
            "refresh rate (e.g. real-time/hourly/daily), data classification (defaults to the landing "
            "zone's own data_classification if the user has no reason to make this table different), and "
            "an S3 prefix — default is '{table_name}/' (nested under the landing zone's overall "
            "s3_stage_prefix), applied without asking unless the user brings it up or clearly wants "
            "something else. Ask about individual column descriptions too if the user has useful context to "
            "add (what each field means, valid value ranges) — optional, anything not supplied is "
            "inferred from the sample file(s). After each table, ask whether there's another table to "
            "add before either asking about the next one or calling this tool with the full set collected "
            "so far. "
            "If instead the user dumps loose info for several tables at once (pasting multiple sample "
            "files, describing several tables in one message), don't interrogate them one field at a "
            "time — call draft_landing_zone_tables first to turn that into a reviewable draft, and only "
            "call this tool once with the tables list the user confirms/edits from that draft. "
            "Note: all tables in one landing zone share a single Snowflake external stage and file "
            "format (file_format_type) — if two tables genuinely need different file formats, they need "
            "separate landing zones. data_classification, owner, and refresh_rate set per table are "
            "descriptive metadata only (stored for later reuse, e.g. dbt model generation) — they do not "
            "change which Snowflake schema Terraform actually provisions; that's still driven by the "
            "landing zone's own top-level data_classification. "
            "Before calling this, always ask whether the data should land in a brand-new Snowflake "
            "database or be added to one an existing landing zone already created (use "
            "check_deployed_infrastructure to show them what's already deployed on the target stack(s) "
            "as options) — never assume. A new database also gets its own medallion-arch schemas "
            "({name}-db and {name}-db-arch are both created). Reusing an existing landing zone's "
            "database does NOT create either — pass that landing zone's name as "
            "existing_database_landing_zone instead, and this one's table(s) land in its existing "
            "schemas via {existing_database_landing_zone}-db/-db-arch. This matters because schema "
            "names are derived from classification, not landing zone name (e.g. 'bronze' + "
            "'confidential' always becomes BRONZE_CONFIDENTIAL) — two landing zones with the same "
            "classification that each tried to create their own medallion-arch in the same database "
            "would collide on identical schema names and fail at apply time; reusing is how a second "
            "landing zone shares a database safely. Only makes sense when both landing zones are in "
            "the same stack (their Terraform components must be siblings in the same directory tree). "
            "Always ask the user which stack(s) this should apply to before calling — don't assume. "
            "If they say 'all', 'every environment', or have no preference, proceed without "
            "stack_name (applies to every stack configured on the account, e.g. dev AND prod — this "
            "is the default when they don't care). If they name specific stack(s) (e.g. 'just dev', "
            "'add this to prod'), pass stack_name for a single one, or use stack_overrides (see "
            "below) if they want it on more than one but with different settings per stack. Getting "
            "this wrong silently changes every stack on the account, including ones that already "
            "have this landing zone deployed. "
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
                    "description": "Restrict this to a single stack (e.g. 'prod'). Prefer stack_names "
                    "(plural) when you have it from a UI selection; this remains for a plain-language "
                    "single-stack request. Omit both when the user explicitly wants this landing zone "
                    "created on every stack on the account.",
                },
                "stack_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict this to a specific subset of stacks (e.g. ['dev', "
                    "'staging']) — one or more, but not necessarily all. Takes precedence over "
                    "stack_name if both are given. Omit (and omit stack_name) when the user wants "
                    "every stack on the account, which is the default when they have no preference.",
                },
                "region": {
                    "type": "string",
                    "description": "AWS region (e.g. eu-west-1)",
                    "default": "eu-west-1",
                },
                "data_classification": {
                    "type": "string",
                    "description": "Data classification level — must match one of this account's "
                    "configured classifications (listed, with descriptions, in your system context). If "
                    "omitted, the account's default classification is used; if there's no default "
                    "configured, this is required and you must ask.",
                },
                "retention_policy": {
                    "type": "string",
                    "description": "How long data must be retained. If omitted, the account's default "
                    "retention_policy (see system context) is used; if there's no default configured, "
                    "this is required and you must ask.",
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
                "existing_database_landing_zone": {
                    "type": "string",
                    "description": "Name of an already-deployed landing zone (on the same stack) whose "
                    "Snowflake database and medallion-arch schemas this one should attach to, instead of "
                    "creating its own {name}-db/{name}-db-arch. Leave empty to create a new database. "
                    "Always ask the user which they want — use check_deployed_infrastructure to show them "
                    "what's already deployed on the target stack(s) as candidates.",
                    "default": "",
                },
                "s3_stage_prefix": {
                    "type": "string",
                    "description": "Key prefix within the bucket where data actually lands — the Snowflake "
                    "external stage created by {name}-si points at exactly this prefix, and every "
                    "table's own s3_prefix is nested under it. Defaults to '' (bucket root), which works "
                    "for any table layout since the stage just needs to be a common ancestor of every "
                    "table's files — only set this if tables actually share a real nested parent folder "
                    "(e.g. all tables land under 'data/').",
                    "default": "",
                },
                "file_format_type": {
                    "type": "string",
                    "description": "Snowflake file format type, shared by every table in this landing "
                    "zone (they all read through the same external stage). If omitted, inferred from the "
                    "first table's sample_files (falls back to JSON if it can't be determined).",
                    "enum": ["JSON", "CSV", "PARQUET", "AVRO", "ORC", "XML"],
                },
                "tables": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Table name (e.g. RAW_EVENTS). Used as the Bronze table "
                                "name when create_snowpipe is true, and as the default S3 prefix "
                                "('{name}/') this table's files land under.",
                            },
                            "description": {
                                "type": "string",
                                "description": "Plain-language description of what this table represents "
                                "(e.g. 'Shopify order-created webhook events'). If omitted, inferred from "
                                "this table's sample_files.",
                            },
                            "owner": {
                                "type": "string",
                                "description": "Team or person responsible for this specific table's "
                                "data. Metadata only — stored for later reuse, doesn't affect what "
                                "Terraform provisions.",
                            },
                            "refresh_rate": {
                                "type": "string",
                                "description": "How often this table is expected to receive new data, "
                                "e.g. 'real-time', 'hourly', 'daily'. Metadata only.",
                            },
                            "data_classification": {
                                "type": "string",
                                "enum": ["public", "internal", "confidential", "restricted"],
                                "description": "Data classification for this specific table. Defaults to "
                                "the landing zone's own data_classification if omitted. Metadata only — "
                                "the schema Terraform actually provisions is still driven by the landing "
                                "zone's top-level data_classification.",
                            },
                            "s3_prefix": {
                                "type": "string",
                                "description": "S3 key prefix (nested under the landing zone's own "
                                "s3_stage_prefix) this table's files land under, e.g. 'orders/'. Defaults "
                                "to '{name}/' if the user doesn't want anything different. Ask the user "
                                "before calling this tool whether the default is fine or they want a "
                                "different prefix — don't silently assume.",
                            },
                            "file_format_type": {
                                "type": "string",
                                "enum": ["JSON", "CSV", "PARQUET", "AVRO", "ORC", "XML"],
                                "description": "This table's file format, if it needs to be given "
                                "explicitly rather than inferred from its sample_files. Only the first "
                                "table's resolved format is actually used (see the top-level "
                                "file_format_type note) — provide this on the first table if it matters.",
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
                                "description": "At least one representative sample of this table's data — "
                                "paste its raw content (as text; binary formats like PARQUET/AVRO/ORC "
                                "can't be inferred this way, just describe them instead). Used to infer "
                                "file format, size stats, description, and columns for anything not "
                                "supplied explicitly. Ask the user for this before calling the tool — "
                                "required per table, not optional.",
                            },
                            "expected_size_bytes": {
                                "type": "integer",
                                "description": "Typical file size in bytes for this table. If omitted, "
                                "derived from the average size of its sample_files.",
                            },
                            "min_size_bytes": {
                                "type": "integer",
                                "description": "Smallest file size expected for this table, in bytes. If "
                                "omitted, derived from the smallest sample_files provided.",
                            },
                            "max_size_bytes": {
                                "type": "integer",
                                "description": "Largest file size expected for this table, in bytes. If "
                                "omitted, derived from the largest sample_files provided.",
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
                                "description": "Known columns/fields in this table, if the user has "
                                "useful context to add beyond what the samples already show (what a "
                                "field means, valid ranges, units). Optional — anything not supplied "
                                "here is inferred from this table's sample_files.",
                            },
                            "filter_suffix": {
                                "type": "string",
                                "description": "S3 key suffix to filter this table's Snowpipe ingest "
                                "event notifications, e.g. '.json' (optional).",
                            },
                        },
                        "required": ["name", "sample_files"],
                    },
                    "description": "One entry per table/dataset landing in this bucket. Ask about tables "
                    "one at a time in conversation (see the tool description) — collect each one's "
                    "fields, ask if there's another table, and only call this tool once the user is done "
                    "adding tables.",
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
                    "description": "Also provision Snowpipe auto-ingest for every table in `tables`: "
                    "creates each one's Bronze table (RAW_DATA VARIANT, SOURCE_FILE, LOAD_TIMESTAMP) in "
                    "the bronze schema and a pipe that automatically loads files landing under that "
                    "table's own S3 prefix into it. Applies to every targeted stack the same way — use "
                    "the standalone create_snowflake_pipe tool instead if you need per-stack pipe config "
                    "or are retrofitting a new table onto a landing zone that already exists.",
                    "default": False,
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
                    "cost_center, existing_s3_bucket_arn, existing_database_landing_zone, kms_key_arn, "
                    "s3_stage_prefix, file_format_type, create_access_keys, schema_names.",
                    "default": {},
                },
            },
            "required": [
                "name",
                "data_owner",
                "tables",
            ],
        }

    async def execute(
        self,
        name: str,
        data_owner: str,
        data_classification: str | None = None,
        retention_policy: str | None = None,
        stack_name: str | None = None,
        stack_names: list[str] | None = None,
        region: str = "eu-west-1",
        department: str = "none",
        cost_center: str = "none",
        kms_key_arn: str = "",
        existing_s3_bucket_arn: str = "",
        existing_database_landing_zone: str = "",
        s3_stage_prefix: str = "",
        file_format_type: str | None = None,
        create_access_keys: bool = False,
        schema_names: list[str] = None,
        create_snowpipe: bool = False,
        tables: list[dict] | None = None,
        tags: dict = {},
        stack_overrides: dict | None = None,
        _action: str = "add",
        _target_stack_names: list[str] | None = None,
    ) -> str:
        if schema_names is None:
            schema_names = ["bronze", "silver", "gold", "platinum"]
        tables = tables or []
        # Only required on initial creation — update_landing_zone re-invokes this with
        # _action="update" for unrelated field changes and never has samples to hand,
        # and re-inferring/overwriting an existing profile on every unrelated update
        # would be both wrong and impossible without them.
        if _action == "add":
            if not tables:
                return (
                    "tables is required — ask the user about each table one at a time (name, "
                    "description, owner, refresh rate, data classification, S3 prefix, sample "
                    "file(s), column descriptions), asking after each one whether there's another "
                    "table before calling this."
                )
            for t in tables:
                if not t.get("name"):
                    return "Every table needs a name."
                if not t.get("sample_files"):
                    return (
                        f"Table '{t.get('name')}' needs at least one sample file (sample_files) — "
                        "ask the user for one before calling this."
                    )
        if not _target_stack_names:
            if stack_names:
                _target_stack_names = stack_names
            elif stack_name:
                _target_stack_names = [stack_name]
        stack_overrides = stack_overrides or {}

        if data_classification is None:
            data_classification = await self._default_data_classification()
            if data_classification is None:
                return (
                    "data_classification is required — this account has no default classification "
                    "configured (Admin → Data classifications), so ask the user which one applies."
                )
        if retention_policy is None:
            retention_policy = await self._default_retention_policy()
            if retention_policy is None:
                return (
                    "retention_policy is required — this account has no default retention policy "
                    "configured (Admin → Projects), so ask the user how long this data must be retained."
                )

        # One profile (persisted) + resolved S3/file-format config per table. All tables
        # share this landing zone's single external stage and file format — only the
        # first table's resolved file_format_type actually gets used for the stage.
        resolved_tables: list[dict] = []
        for t in tables:
            table_name = t["name"]
            table_s3_prefix = t.get("s3_prefix") or f"{table_name}/"
            sample_files = t.get("sample_files")
            table_profile = None
            table_file_format = t.get("file_format_type")
            if sample_files:
                table_profile = await infer_profile(
                    landing_zone_name=name,
                    table_name=table_name,
                    sample_files=sample_files,
                    data_description=t.get("description"),
                    file_format=table_file_format,
                    expected_size_bytes=t.get("expected_size_bytes"),
                    min_size_bytes=t.get("min_size_bytes"),
                    max_size_bytes=t.get("max_size_bytes"),
                    columns=t.get("columns"),
                    owner=t.get("owner"),
                    refresh_rate=t.get("refresh_rate"),
                    data_classification=t.get("data_classification") or data_classification,
                    s3_prefix=table_s3_prefix,
                )
                table_file_format = table_profile["file_format"] or "JSON"
                await upsert_profile(self._db, self._account_id, name, table_profile)
            else:
                table_file_format = table_file_format or "JSON"
            resolved_tables.append({
                "name": table_name,
                "s3_prefix": table_s3_prefix,
                "file_format_type": table_file_format,
                "filter_suffix": t.get("filter_suffix", ""),
                "profile": table_profile,
                "sample_files": sample_files,
            })

        if file_format_type is None and resolved_tables:
            file_format_type = resolved_tables[0]["file_format_type"]
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
            # modules/ is a single shared directory in the repo (referenced by
            # every stack's terragrunt config via get_parent_terragrunt_dir()),
            # vendored from the account's one pinned module_version.
            self._copy_modules(upload_root, repo_record.module_version if repo_record else "1.0.0")
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
                "existing_database_landing_zone": ov.get(
                    "existing_database_landing_zone", existing_database_landing_zone
                ),
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

            db_landing_zone = cfg["existing_database_landing_zone"] or name
            if not cfg["existing_database_landing_zone"]:
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
                    db_landing_zone=db_landing_zone,
                )
            )

            if create_snowpipe:
                for pipe_component, rt in self._pipe_components(name, resolved_tables):
                    pipe_dir = env_dir / pipe_component
                    os.makedirs(pipe_dir, exist_ok=True)
                    (pipe_dir / "terragrunt.hcl").write_text(
                        templates.pipe_from_landing_zone(
                            name=name,
                            target_table=rt["name"],
                            filter_prefix=f"{cfg['s3_stage_prefix']}{rt['s3_prefix']}",
                            filter_suffix=rt["filter_suffix"],
                            db_landing_zone=db_landing_zone,
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

        # An update only ever pushes this landing zone's own terragrunt.hcl
        # files — never modules/ or the shared root/global/account HCL that
        # were regenerated into upload_root above purely so verification had
        # a complete tree to plan against.
        if _action == "add":
            push_root = upload_root
        else:
            push_root = Path(tempfile.mkdtemp(prefix="lz-update-push-"))
            pipe_components = [c for c, _ in self._pipe_components(name, resolved_tables)]
            for env in stack_names:
                for component in (f"{name}-db", f"{name}-db-arch", f"{name}-lz", f"{name}-si", *pipe_components):
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
                create_snowpipe=create_snowpipe,
                table_names=[rt["name"] for rt in resolved_tables],
            )
        finally:
            if push_root != upload_root:
                shutil.rmtree(push_root, ignore_errors=True)

        access_keys_section = (
            await self._access_keys_section(name, project.name, stacks) if any_create_access_keys else ""
        )

        pipe_structure_lines = (
            "".join(f"\n      {c}/" for c, _ in self._pipe_components(name, resolved_tables))
            if create_snowpipe else ""
        )
        stack_structure = "\n".join(
            f"    {stack_name}/landing-zone/\n"
            + (
                f"      {name}-db/\n      {name}-db-arch/\n"
                if not resolved[stack_name]["existing_database_landing_zone"] else ""
            )
            + f"      {name}-lz/\n"
            f"      {name}-si/"
            + pipe_structure_lines
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
            + (
                f"\n    Existing database:   {resolved[env]['existing_database_landing_zone']}-db"
                if resolved[env]["existing_database_landing_zone"] else ""
            )
            for env in stack_names
        )

        snowpipe_summary = ""
        if create_snowpipe:
            pipe_lines = "\n".join(
                f"  {rt['name']}: RAW_DATA VARIANT, SOURCE_FILE, LOAD_TIMESTAMP (created by Terraform)\n"
                f"    Filter: prefix='{s3_stage_prefix}{rt['s3_prefix']}' suffix='{rt['filter_suffix']}'"
                for rt in resolved_tables
            )
            snowpipe_summary = f"Snowpipe:\n{pipe_lines}\n\n"

        profile_summary = ""
        profiled = [rt for rt in resolved_tables if rt["profile"]]
        if profiled:
            table_blocks = []
            for rt in profiled:
                profile = rt["profile"]
                columns_lines = "\n".join(
                    f"      - {c.get('name')} ({c.get('type', 'unknown')}): {c.get('description', '')}"
                    for c in (profile.get("columns") or [])
                )
                table_blocks.append(
                    f"  {rt['name']} (from {len(rt['sample_files'])} sample(s)):\n"
                    f"    Description:  {profile.get('description') or '(none)'}\n"
                    f"    File format:  {rt['file_format_type']}\n"
                    f"    Size (bytes): min={profile.get('min_size_bytes')} expected={profile.get('expected_size_bytes')} "
                    f"max={profile.get('max_size_bytes')}\n"
                    + (f"    Columns:\n{columns_lines}\n" if columns_lines else "")
                )
            profile_summary = (
                "Data profiles (stored for reuse later, e.g. dbt model generation):\n"
                + "\n".join(table_blocks) + "\n"
            )

        return (
            f"Landing zone ready at {upload_root}\n\n"
            f"{config_summary}\n\n"
            f"{snowpipe_summary}"
            f"{profile_summary}"
            f"Structure:\n"
            f"  upload/{name}/\n"
            f"    modules/ (version {repo_record.module_version if repo_record else '1.0.0'})\n"
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
        create_snowpipe: bool = False,
        table_names: list[str] | None = None,
    ) -> str:
        table_names = table_names or []
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
                + (
                    f", db={stack_configs[env]['existing_database_landing_zone']}-db"
                    if stack_configs[env]["existing_database_landing_zone"] else ""
                )
                for env in stack_names
            )
        )

        pr_title = f"{conv_type}(landing-zone): {action} {landing_zone_name} landing zone"

        summary_verb = "Adds" if action == "add" else "Updates"
        any_new_db = any(not stack_configs[env]["existing_database_landing_zone"] for env in stack_names)
        any_reused_db = any(stack_configs[env]["existing_database_landing_zone"] for env in stack_names)
        config_table_rows = "\n".join(
            f"| `{env}` | `{stack_configs[env]['data_classification']}` | "
            f"`{stack_configs[env]['retention_policy']}` | {stack_configs[env]['data_owner']} | "
            f"{stack_configs[env]['existing_s3_bucket_arn'] or '_new bucket_'} | "
            f"{stack_configs[env]['existing_database_landing_zone'] + '-db' if stack_configs[env]['existing_database_landing_zone'] else '_new database_'} | "
            f"{', '.join(f'`{s}`' for s in stack_configs[env]['schema_names'])} |"
            for env in stack_names
        )
        pr_body = (
            f"## Summary\n\n"
            f"{summary_verb} the landing zone for `{landing_zone_name}`.\n\n"
            + (
                f"- **`{landing_zone_name}-db`** — Snowflake database\n"
                f"- **`{landing_zone_name}-db-arch`** — Medallion schemas\n"
                if any_new_db else ""
            )
            + (
                "- **Reuses an existing database** for: "
                + ", ".join(
                    f"`{env}` (`{stack_configs[env]['existing_database_landing_zone']}-db`)"
                    for env in stack_names
                    if stack_configs[env]["existing_database_landing_zone"]
                )
                + " — no new database or medallion-arch schemas created for these stacks\n"
                if any_reused_db else ""
            )
            + f"- **`{landing_zone_name}-lz`** — S3 bucket\n"
            f"- **`{landing_zone_name}-si`** — Snowflake storage integration + external stage\n"
            + (
                f"- **Snowpipe auto-ingest** ({len(table_names)} table(s): "
                f"{', '.join(f'`{t}`' for t in table_names)}) — one "
                f"`{landing_zone_name}-pipe{'' if len(table_names) <= 1 else '[-<table>]'}` component "
                f"per table, each with its own Bronze table (`RAW_DATA VARIANT`, `SOURCE_FILE`, "
                f"`LOAD_TIMESTAMP` — Terraform owns only this shape; Silver/Gold modeling from here is "
                f"dbt's responsibility)\n"
                if create_snowpipe else ""
            )
            + f"\n## Configuration\n\n"
            f"| Stack | Data classification | Retention policy | Data owner | Bucket | Database | Schemas |\n"
            f"|---|---|---|---|---|---|---|\n"
            f"{config_table_rows}\n\n"
            f"## Test plan\n\n"
            f"- [ ] `terragrunt run-all validate` passes in `{stack_names[0]}/landing-zone`\n"
            f"- [ ] `terragrunt run-all plan` shows expected resources\n"
            + (
                "".join(
                    f"- [ ] Drop a test file under each table's own S3 prefix and confirm it appears in "
                    f"`{t}`\n"
                    for t in table_names
                ) if create_snowpipe else ""
            )
            + f"---\n"
            f"🤖 Generated by Canary"
        )

        base_branch = record.branch
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
    def _pipe_components(name: str, resolved_tables: list[dict]) -> list[tuple[str, dict]]:
        """(terragrunt component name, resolved table) for each table's pipe. The
        first table keeps the plain {name}-pipe folder — the same path every
        single-table landing zone has always used, so an existing deployment's
        Terraform state stays put — and only the second-and-later tables get a
        {name}-pipe-{table} folder of their own."""
        components = []
        for i, rt in enumerate(resolved_tables):
            component = f"{name}-pipe" if i == 0 else f"{name}-pipe-{LandingZoneTool._slugify(rt['name'])}"
            components.append((component, rt))
        return components

    @staticmethod
    def _slugify(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

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

    async def _default_data_classification(self) -> str | None:
        result = await self._db.execute(
            select(DataClassification).where(
                DataClassification.account_id == self._account_id, DataClassification.is_default.is_(True)
            )
        )
        record = result.scalar_one_or_none()
        return record.name if record else None

    async def _default_retention_policy(self) -> str | None:
        project = await self._get_project()
        return project.default_retention_policy if project else None

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
