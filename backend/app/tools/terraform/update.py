import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.tools.base import BaseTool
from app.models.project import GitHubRepo

settings = get_settings()

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

HCL files:

{files}

Return ONLY valid JSON with no explanation or markdown fences.
"""


class UpdateLandingZoneTool(BaseTool):

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    @property
    def name(self) -> str:
        return "update_landing_zone"

    @property
    def description(self) -> str:
        return (
            "Update an existing landing zone. Clones the connected GitHub repo, reads the "
            "current Terragrunt config for the named landing zone, applies only the fields "
            "you specify, regenerates the configs, and opens a PR with the changes. "
            "Only provide the fields you want to change — everything else is preserved as-is."
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
                "project_code": {
                    "type": "string",
                    "description": "Project the landing zone belongs to",
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
            },
            "required": ["name", "project_code"],
        }

    async def execute(
        self,
        name: str,
        project_code: str,
        data_classification: str | None = None,
        retention_policy: str | None = None,
        data_owner: str | None = None,
        region: str | None = None,
        existing_s3_bucket_arn: str | None = None,
        s3_stage_prefix: str | None = None,
        file_format_type: str | None = None,
        schema_names: list[str] | None = None,
    ) -> str:
        repo = await self._get_github_repo(project_code)
        if not repo:
            return f"No GitHub repo connected for project '{project_code}'."

        clone_dir = tempfile.mkdtemp(prefix="lz-update-")
        try:
            self._clone(repo, clone_dir)
            current = await self._extract_config(name, clone_dir, repo.infrastructure_base_path)
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(clone_dir, ignore_errors=True)
            return f"Failed to clone {repo.repo_full_name}: {exc.stderr.decode()}"
        except (json.JSONDecodeError, KeyError) as exc:
            shutil.rmtree(clone_dir, ignore_errors=True)
            return f"Could not extract config for landing zone '{name}' from {repo.repo_full_name}: {exc}"
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
            }.items()
            if v is not None
        }
        merged = {**current, **patch}

        # Import here to avoid circular imports
        from app.tools.terraform.s3 import LandingZoneTool
        tool = LandingZoneTool(self._db, self._account_id)
        return await tool.execute(
            name=name,
            project_code=project_code,
            data_classification=merged.get("data_classification", "internal"),
            retention_policy=merged.get("retention_policy", "1-year"),
            data_owner=merged.get("data_owner", "unknown"),
            region=merged.get("region", "eu-west-1"),
            existing_s3_bucket_arn=merged.get("existing_s3_bucket_arn") or "",
            s3_stage_prefix=merged.get("s3_stage_prefix", "data/"),
            file_format_type=merged.get("file_format_type", "JSON"),
            schema_names=merged.get("schema_names", ["bronze", "silver", "gold", "platinum"]),
            _action="update",
        )

    # ------------------------------------------------------------------

    def _clone(self, repo: GitHubRepo, clone_dir: str) -> None:
        clone_url = f"https://{repo.token}@github.com/{repo.repo_full_name}.git"
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", repo.branch, clone_url, clone_dir],
            check=True,
            capture_output=True,
        )

    async def _extract_config(self, name: str, clone_dir: str, base_path: str) -> dict:
        base = Path(clone_dir) / base_path
        files: dict[str, str] = {}

        # Read the files Claude needs to reconstruct config
        for component in (f"{name}-lz", f"{name}-si", f"{name}-db-arch"):
            hcl = base / "dev" / "landing-zone" / component / "terragrunt.hcl"
            if hcl.exists():
                files[f"dev/landing-zone/{component}/terragrunt.hcl"] = hcl.read_text()

        for fname in ("region.hcl",):
            f = base / "dev" / fname
            if f.exists():
                files[f"dev/{fname}"] = f.read_text()

        if not files:
            raise KeyError(
                f"No HCL files found for landing zone '{name}' under "
                f"{base}/dev/landing-zone/ — check the branch has the landing zone merged."
            )

        files_text = "\n\n".join(f"=== {k} ===\n{v}" for k, v in files.items())
        prompt = _EXTRACT_PROMPT.format(name=name, files=files_text)

        response = await self._client.messages.create(
            model=settings.anthropic_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip markdown fences if the model adds them anyway
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text)

    async def _get_github_repo(self, project_name: str) -> "GitHubRepo | None":
        result = await self._db.execute(
            select(GitHubRepo).where(
                GitHubRepo.account_id == self._account_id,
                GitHubRepo.project_name == project_name,
            )
        )
        return result.scalar_one_or_none()
