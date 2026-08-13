import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.llm_client import LLMClient
from app.services.github_service import GitHubService, GitHubError
from app.tools.base import BaseTool
from app.models.project import GitHubRepo
from app.models.stack import Stack

_EXTRACT_PROMPT = """\
You are reading Terragrunt HCL files generated for a landing zone named "{name}".
Extract the current configuration and return it as a JSON object with exactly these fields:
  data_classification  - string
  retention_policy     - string, one of: 30-day, 90-day, 1-year, 7-year, indefinite
  data_owner           - string
  region               - string (AWS region, e.g. eu-west-1)
  existing_s3_bucket_arn - string or null (null if no existing bucket was provided)
  existing_database_landing_zone - string or null. Look at the {name}-si file's `dependency "db"`
    block: its config_path is "../X-db". If X equals "{name}", this is null (the landing zone owns
    its own database). Otherwise this is X (the landing zone reuses that other landing zone's
    database and medallion-arch schemas instead of having its own).
  s3_stage_prefix      - string
  file_format_type     - string, one of: JSON, CSV, PARQUET, AVRO, ORC, XML
  schema_names         - list of strings
  create_access_keys   - boolean (true if an IAM user with access keys was created for direct S3 access)
  create_snowpipe      - boolean (true if at least one "{name}-pipe*/terragrunt.hcl" file is included below)
  tables                - array, one entry per "{name}-pipe*/terragrunt.hcl" file included below (empty
    array if none are included), each an object with:
      name          - the `target_table` input from that file
      filter_prefix - the `filter_prefix` input from that file, or "" if absent
      filter_suffix - the `filter_suffix` input from that file, or "" if absent

HCL files:

{files}

Return ONLY valid JSON with no explanation or markdown fences.
"""


class UpdateLandingZoneTool(BaseTool):

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id
        self._llm = LLMClient()

    @property
    def name(self) -> str:
        return "update_landing_zone"

    @property
    def description(self) -> str:
        return (
            "Update an existing landing zone. Clones the connected GitHub repo, reads the "
            "current Terragrunt config for the named landing zone, applies only the fields "
            "you specify, regenerates the configs, and opens a PR with the changes. "
            "Only provide the fields you want to change — everything else is preserved as-is, including "
            "every other table's Snowpipe setup if this landing zone has more than one (this tool only "
            "ever edits ONE table's pipe per call, named by bronze_table_name — the rest are read back "
            "from the repo and carried through unchanged). "
            "Pass create_snowpipe=true with bronze_table_name to add Snowpipe auto-ingest for a table "
            "that doesn't have it yet (a new table if the name doesn't already exist, or the landing "
            "zone's first table if it has none), or change bronze_table_name/snowpipe_filter_prefix/"
            "snowpipe_filter_suffix to reconfigure an existing one — bronze_table_name must exactly "
            "match (case-insensitive) an existing table's name for this to edit it rather than add a "
            "new one. Setting create_snowpipe=false does NOT remove an already-deployed pipe or Bronze "
            "table — use remove_terragrunt_block with '{name}-pipe' (or '{name}-pipe-{table}' for any "
            "table after the first) for that instead. "
            "Whether this landing zone owns its own Snowflake database or reuses another landing "
            "zone's (existing_database_landing_zone, set at creation) can NOT be changed here — it's "
            "preserved automatically from whatever is currently deployed, and switching it after the "
            "fact would mean migrating already-loaded Bronze tables to a different database/schema, "
            "not just rewriting a dependency block. If the user wants that, tell them it isn't "
            "supported as an update. "
            "Always ask the user which stack(s) this change should apply to before calling — don't "
            "assume. If they say 'all', 'every environment', or have no preference, proceed without "
            "stack_name (applies the change to every stack, e.g. dev AND prod — this is the default "
            "when they don't care). If they name a specific one (e.g. 'only in dev', 'just for "
            "staging'), pass stack_name for it. Getting this wrong silently changes every other "
            "stack too. This only ever touches this landing zone's own terragrunt.hcl "
            "config — it never changes the vendored Terraform modules (use a module version bump "
            "plus a hard-refresh for that). "
            "Requires confirmation: call once with confirm omitted (or false) to get a plain-language "
            "preview of exactly what will change — show that to the user verbatim and wait for them "
            "to explicitly confirm in their next message. Only call again with confirm=true, passing "
            "the exact same arguments as the preview call, after the user has clearly agreed. Never "
            "set confirm=true on the first call."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Landing zone name (e.g. cress, buttercup)",
                },
                "stack_name": {
                    "type": "string",
                    "description": "Restrict this change to a single stack (e.g. 'dev'). Prefer "
                    "stack_names (plural) when you have it from a UI selection; this remains for a "
                    "plain-language single-stack request. Omit both when the user explicitly wants "
                    "the change applied to every stack on the account.",
                },
                "stack_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict this change to a specific subset of stacks (e.g. ['dev', "
                    "'staging']) — one or more, but not necessarily all. Takes precedence over "
                    "stack_name if both are given. Omit (and omit stack_name) when the user wants "
                    "every stack on the account, which is the default when they have no preference.",
                },
                "data_classification": {
                    "type": "string",
                    "enum": ["public", "internal", "confidential", "restricted"],
                },
                "retention_policy": {
                    "type": "string",
                    "enum": ["30-day", "90-day", "1-year", "7-year", "indefinite"],
                },
                "data_owner": {"type": "string"},
                "region": {"type": "string"},
                "existing_s3_bucket_arn": {"type": "string"},
                "s3_stage_prefix": {"type": "string"},
                "file_format_type": {
                    "type": "string",
                    "enum": ["JSON", "CSV", "PARQUET", "AVRO", "ORC", "XML"],
                },
                "schema_names": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "create_access_keys": {
                    "type": "boolean",
                    "description": "Create an IAM user with access keys for direct S3 access to this landing zone's bucket.",
                },
                "create_snowpipe": {
                    "type": "boolean",
                    "description": "Add Snowpipe auto-ingest (with a Bronze table) to this landing zone. "
                    "Requires bronze_table_name if not already set. Setting this to false does NOT delete "
                    "an existing pipe — use remove_terragrunt_block for that.",
                },
                "bronze_table_name": {
                    "type": "string",
                    "description": "Unqualified name for the Bronze table Snowpipe loads into (e.g. "
                    "RAW_EVENTS). Required the first time create_snowpipe is set to true.",
                },
                "snowpipe_filter_prefix": {
                    "type": "string",
                    "description": "S3 key prefix to filter Snowpipe ingest event notifications.",
                },
                "snowpipe_filter_suffix": {
                    "type": "string",
                    "description": "S3 key suffix to filter Snowpipe ingest event notifications, e.g. .json",
                },
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Leave false (or omit) to preview the change without opening a PR. Only "
                    "set true after the user has explicitly confirmed the preview.",
                },
            },
            "required": ["name"],
        }

    async def execute(
        self,
        name: str,
        stack_name: str | None = None,
        stack_names: list[str] | None = None,
        data_classification: str | None = None,
        retention_policy: str | None = None,
        data_owner: str | None = None,
        region: str | None = None,
        existing_s3_bucket_arn: str | None = None,
        s3_stage_prefix: str | None = None,
        file_format_type: str | None = None,
        schema_names: list[str] | None = None,
        create_access_keys: bool | None = None,
        create_snowpipe: bool | None = None,
        bronze_table_name: str | None = None,
        snowpipe_filter_prefix: str | None = None,
        snowpipe_filter_suffix: str | None = None,
        confirm: bool = False,
    ) -> str:
        repo = await self._get_github_repo()
        if not repo:
            return "No GitHub repo connected. Use POST /api/v1/github/repos first."

        # Reading "current" config only needs ONE deployed stack as a reference
        # (an unscoped/multi-stack update applies the same patch uniformly to
        # all of them anyway) — stack_names[0] stands in for the whole subset here.
        single_stack_name = stack_names[0] if stack_names else stack_name
        if single_stack_name:
            reference_stack = await self._get_stack(single_stack_name)
            if not reference_stack:
                return f"No stack named '{single_stack_name}' found for this account."
        else:
            reference_stack = await self._get_reference_stack()
            if not reference_stack:
                return "No stacks configured for this account. Add one under Admin → Stacks first."

        # Every stack's landing-zone content lives on the same trunk branch
        # (GitHub Flow) — only the directory (reference_stack.name) differs
        # per stack, not the branch.
        trunk_branch = repo.branch

        clone_dir = tempfile.mkdtemp(prefix="lz-update-")
        try:
            self._clone(repo, clone_dir, trunk_branch)
            current = await self._extract_config(name, clone_dir, repo.infrastructure_base_path, reference_stack.name)
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(clone_dir, ignore_errors=True)
            return f"Failed to clone {repo.repo_full_name} (branch '{trunk_branch}'): {exc.stderr.decode()}"
        except KeyError:
            shutil.rmtree(clone_dir, ignore_errors=True)
            open_pr_url = await self._find_likely_unmerged_pr(repo, name, trunk_branch)
            if open_pr_url:
                return (
                    f"'{name}' isn't on the '{trunk_branch}' branch yet — but there's an open, unmerged PR "
                    f"that looks like it created it: {open_pr_url}\n\nMerge that PR first, then ask me again."
                )
            return (
                f"Could not find '{name}' under {reference_stack.name}/landing-zone/ on the "
                f"'{trunk_branch}' branch, and no matching open PR was found either. Things to check:\n"
                f"  - Is '{name}-lz' the right landing zone name? (Also tried '{name}-si', '{name}-db-arch'.)\n"
                f"  - Was it created for a different stack? Try again with stack_name set to that stack "
                f"(currently checked: '{reference_stack.name}').\n"
                f"  - Does infrastructure_base_path in GitHub settings match where it actually lives in the repo?"
            )
        except json.JSONDecodeError as exc:
            shutil.rmtree(clone_dir, ignore_errors=True)
            return f"Could not parse the current config for landing zone '{name}' from {repo.repo_full_name}: {exc}"
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

        # Merge: only apply fields explicitly passed (non-None)
        patch = {
            k: v for k, v in {
                "data_classification": data_classification,
                "retention_policy": retention_policy,
                "data_owner": data_owner,
                "region": region,
                "existing_s3_bucket_arn": existing_s3_bucket_arn,
                "s3_stage_prefix": s3_stage_prefix,
                "file_format_type": file_format_type,
                "schema_names": schema_names,
                "create_access_keys": create_access_keys,
                "create_snowpipe": create_snowpipe,
            }.items()
            if v is not None
        }
        merged = {**current, **patch}
        merged_s3_stage_prefix = merged.get("s3_stage_prefix")
        if merged_s3_stage_prefix is None:
            merged_s3_stage_prefix = ""

        # This tool only ever exposes editing ONE table's pipe at a time
        # (bronze_table_name/snowpipe_filter_prefix/snowpipe_filter_suffix) — but
        # the landing zone may have several. Start from every table _extract_config
        # found (every {name}-pipe*/terragrunt.hcl) so an unrelated field change
        # (e.g. retention_policy) never silently drops the others, then merge this
        # call's single-table edit into that list by name (case-insensitive, since
        # Terraform uppercases target_table).
        existing_tables = current.get("tables") or []
        merged_tables = [dict(t) for t in existing_tables]
        if bronze_table_name is not None:
            match = next(
                (t for t in merged_tables if t.get("name", "").upper() == bronze_table_name.upper()), None
            )
            if match is None:
                match = {"name": bronze_table_name, "filter_prefix": "", "filter_suffix": ""}
                merged_tables.append(match)
            if snowpipe_filter_prefix is not None:
                match["filter_prefix"] = snowpipe_filter_prefix
            if snowpipe_filter_suffix is not None:
                match["filter_suffix"] = snowpipe_filter_suffix

        if merged.get("create_snowpipe") and not merged_tables:
            return "create_snowpipe requires bronze_table_name (the Bronze table Snowpipe will create and load into)."

        if not confirm:
            changes = "\n".join(
                f"  {field}: {current.get(field)!r} → {value!r}"
                for field, value in patch.items()
                if current.get(field) != value
            )
            if bronze_table_name is not None:
                changes += (
                    f"\n  tables: {[t.get('name') for t in existing_tables]!r} → "
                    f"{[t.get('name') for t in merged_tables]!r}"
                )
            if not changes:
                return f"Landing zone '{name}' already matches the requested config — nothing to change."
            target_desc = ", ".join(stack_names) if stack_names else (stack_name or "every stack")
            return (
                f"This will update landing zone '{name}' on {target_desc}:\n\n"
                f"{changes}\n\n"
                "This only rewrites this landing zone's own terragrunt.hcl files — it will not touch "
                "the vendored Terraform modules or any other landing zone.\n\n"
                "Reply to confirm and I'll open the PR."
            )

        # Convert each table's absolute filter_prefix back to the s3_prefix (relative
        # to s3_stage_prefix) LandingZoneTool.execute() expects — it reconstructs the
        # absolute prefix itself as s3_stage_prefix + s3_prefix. No sample_files here:
        # an update never re-infers or overwrites an already-captured data profile.
        tables_arg = []
        for t in merged_tables:
            filter_prefix = t.get("filter_prefix") or ""
            s3_prefix = (
                filter_prefix[len(merged_s3_stage_prefix):]
                if filter_prefix.startswith(merged_s3_stage_prefix)
                else filter_prefix
            )
            tables_arg.append({
                "name": t["name"],
                "s3_prefix": s3_prefix,
                "filter_suffix": t.get("filter_suffix") or "",
            })

        # Import here to avoid circular imports
        from app.tools.terraform.s3 import LandingZoneTool
        tool = LandingZoneTool(self._db, self._account_id)
        return await tool.execute(
            name=name,
            data_classification=merged.get("data_classification", "internal"),
            retention_policy=merged.get("retention_policy", "1-year"),
            data_owner=merged.get("data_owner", "unknown"),
            region=merged.get("region", "eu-west-1"),
            existing_s3_bucket_arn=merged.get("existing_s3_bucket_arn") or "",
            # Not settable via this tool's input_schema — deliberately not exposed
            # as a patchable field, since changing which database a landing zone
            # attaches to after creation would mean migrating already-loaded
            # Bronze tables between schemas, not just rewriting a dependency
            # block. Always carried through unchanged from `current` (extracted
            # from the deployed {name}-si) so an unrelated field change (e.g.
            # retention_policy) can never silently repoint -si/pipes at a
            # {name}-db that was never created.
            existing_database_landing_zone=merged.get("existing_database_landing_zone") or "",
            s3_stage_prefix=merged_s3_stage_prefix,
            file_format_type=merged.get("file_format_type", "JSON"),
            schema_names=merged.get("schema_names", ["bronze", "silver", "gold", "platinum"]),
            create_access_keys=merged.get("create_access_keys", False),
            create_snowpipe=merged.get("create_snowpipe", False),
            tables=tables_arg,
            _action="update",
            _target_stack_names=stack_names if stack_names else ([stack_name] if stack_name else None),
        )

    # ------------------------------------------------------------------

    def _clone(self, repo: GitHubRepo, clone_dir: str, branch: str) -> None:
        clone_url = f"https://{repo.token}@github.com/{repo.repo_full_name}.git"
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, clone_url, clone_dir],
            check=True,
            capture_output=True,
        )

    async def _extract_config(self, name: str, clone_dir: str, base_path: str, reference_stack: str) -> dict:
        base = Path(clone_dir) / base_path
        files: dict[str, str] = {}

        # Read the files Claude needs to reconstruct config, from `reference_stack`
        # — either the specific stack being updated (stack_name was given) or the
        # account's lowest-sort-order stack as a representative default (a plain,
        # unscoped update applies uniformly to every stack anyway). The clone was
        # already checked out to that stack's own branch, so this is just a path.
        for component in (f"{name}-lz", f"{name}-si", f"{name}-db-arch"):
            hcl = base / reference_stack / "landing-zone" / component / "terragrunt.hcl"
            if hcl.exists():
                files[f"{reference_stack}/landing-zone/{component}/terragrunt.hcl"] = hcl.read_text()

        # Every table's pipe component, not just the first: {name}-pipe (the first
        # table) plus any {name}-pipe-<table> (every table after that) — see
        # LandingZoneTool._pipe_components. Missing any of these here would mean an
        # unrelated field update (e.g. changing retention_policy) silently drops
        # every table but the first from the regenerated config.
        landing_zone_dir = base / reference_stack / "landing-zone"
        if landing_zone_dir.exists():
            for pipe_dir in sorted(landing_zone_dir.glob(f"{name}-pipe*")):
                hcl = pipe_dir / "terragrunt.hcl"
                if hcl.exists():
                    files[f"{reference_stack}/landing-zone/{pipe_dir.name}/terragrunt.hcl"] = hcl.read_text()

        for fname in ("region.hcl",):
            f = base / reference_stack / fname
            if f.exists():
                files[f"{reference_stack}/{fname}"] = f.read_text()

        if not files:
            raise KeyError(
                f"No HCL files found for landing zone '{name}' under "
                f"{base}/{reference_stack}/landing-zone/ — check the branch has the landing zone merged."
            )

        files_text = "\n\n".join(f"=== {k} ===\n{v}" for k, v in files.items())
        prompt = _EXTRACT_PROMPT.format(name=name, files=files_text)

        text = await self._llm.complete(prompt, max_tokens=512)
        # Strip markdown fences if the model adds them anyway
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text)

    async def _get_github_repo(self) -> "GitHubRepo | None":
        result = await self._db.execute(select(GitHubRepo).where(GitHubRepo.account_id == self._account_id))
        return result.scalar_one_or_none()

    async def _get_reference_stack(self) -> "Stack | None":
        result = await self._db.execute(
            select(Stack)
            .where(Stack.account_id == self._account_id)
            .order_by(Stack.sort_order)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_stack(self, stack_name: str) -> "Stack | None":
        result = await self._db.execute(
            select(Stack).where(Stack.account_id == self._account_id, Stack.name == stack_name)
        )
        return result.scalar_one_or_none()

    async def _find_likely_unmerged_pr(self, repo: GitHubRepo, landing_zone_name: str, branch: str) -> str | None:
        """The most common reason config extraction fails: the landing zone was
        just created but its PR hasn't been merged yet, so it genuinely isn't on
        that stack's branch. Check for an open PR before telling the user it's missing."""
        svc = GitHubService(
            token=repo.token,
            repo_full_name=repo.repo_full_name,
            branch=branch,
            api_url=repo.api_url,
            base_path=repo.infrastructure_base_path,
        )
        try:
            return await svc.find_open_pr_by_branch_substring(f"{landing_zone_name}-landing-zone-")
        except GitHubError:
            return None
