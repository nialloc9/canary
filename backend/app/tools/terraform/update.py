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
  s3_stage_prefix      - string
  file_format_type     - string, one of: JSON, CSV, PARQUET, AVRO, ORC, XML
  schema_names         - list of strings
  create_access_keys   - boolean (true if an IAM user with access keys was created for direct S3 access)

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
            "Only provide the fields you want to change — everything else is preserved as-is. "
            "By default this applies the change to every stack (e.g. dev AND prod) — always pass "
            "stack_name when the user's request is specific to one environment (e.g. 'only in dev', "
            "'prod should stay the same', 'just for staging'), otherwise you will silently change "
            "every other stack too. This only ever touches this landing zone's own terragrunt.hcl "
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
                    "description": "Restrict this change to a single stack (e.g. 'dev'). Required whenever "
                    "the request is scoped to one environment. Omit only when the user explicitly wants "
                    "the change applied to every stack on the account.",
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
        data_classification: str | None = None,
        retention_policy: str | None = None,
        data_owner: str | None = None,
        region: str | None = None,
        existing_s3_bucket_arn: str | None = None,
        s3_stage_prefix: str | None = None,
        file_format_type: str | None = None,
        schema_names: list[str] | None = None,
        create_access_keys: bool | None = None,
        confirm: bool = False,
        _chat_branch: str | None = None,
    ) -> str:
        repo = await self._get_github_repo()
        if not repo:
            return "No GitHub repo connected. Use POST /api/v1/github/repos first."

        if stack_name:
            reference_stack = await self._get_stack(stack_name)
            if not reference_stack:
                return f"No stack named '{stack_name}' found for this account."
        else:
            reference_stack = await self._get_reference_stack()
            if not reference_stack:
                return "No stacks configured for this account. Add one under Admin → Stacks first."

        # Each stack's landing-zone content lives on that stack's own branch
        # (e.g. dev -> develop, prod -> main) — not necessarily the repo's
        # account-level default branch.
        stack_branch = reference_stack.branch

        clone_dir = tempfile.mkdtemp(prefix="lz-update-")
        try:
            self._clone(repo, clone_dir, stack_branch)
            current = await self._extract_config(name, clone_dir, repo.infrastructure_base_path, reference_stack.name)
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(clone_dir, ignore_errors=True)
            return f"Failed to clone {repo.repo_full_name} (branch '{stack_branch}'): {exc.stderr.decode()}"
        except KeyError:
            shutil.rmtree(clone_dir, ignore_errors=True)
            open_pr_url = await self._find_likely_unmerged_pr(repo, name, stack_branch)
            if open_pr_url:
                return (
                    f"'{name}' isn't on the '{stack_branch}' branch yet — but there's an open, unmerged PR "
                    f"that looks like it created it: {open_pr_url}\n\nMerge that PR first, then ask me again."
                )
            return (
                f"Could not find '{name}' under {reference_stack.name}/landing-zone/ on the "
                f"'{stack_branch}' branch (the '{reference_stack.name}' stack's branch), and no matching "
                f"open PR was found either. Things to check:\n"
                f"  - Is '{name}-lz' the right landing zone name? (Also tried '{name}-si', '{name}-db-arch'.)\n"
                f"  - Was it created for a different stack? Try again with stack_name set to that stack "
                f"(currently checked: '{reference_stack.name}', branch '{stack_branch}').\n"
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
            }.items()
            if v is not None
        }
        merged = {**current, **patch}

        if not patch:
            return f"No fields were specified to change on landing zone '{name}' — nothing to do."

        if not confirm:
            changes = "\n".join(
                f"  {field}: {current.get(field)!r} → {value!r}"
                for field, value in patch.items()
                if current.get(field) != value
            )
            if not changes:
                return f"Landing zone '{name}' already matches the requested config — nothing to change."
            return (
                f"This will update landing zone '{name}' on {stack_name or 'every stack'}:\n\n"
                f"{changes}\n\n"
                "This only rewrites this landing zone's own terragrunt.hcl files — it will not touch "
                "the vendored Terraform modules or any other landing zone.\n\n"
                "Reply to confirm and I'll open the PR."
            )

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
            s3_stage_prefix=merged.get("s3_stage_prefix", "data/"),
            file_format_type=merged.get("file_format_type", "JSON"),
            schema_names=merged.get("schema_names", ["bronze", "silver", "gold", "platinum"]),
            create_access_keys=merged.get("create_access_keys", False),
            _action="update",
            _target_stack_names=[stack_name] if stack_name else None,
            _chat_branch=_chat_branch,
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
