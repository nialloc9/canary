import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.tools.base import BaseTool
import app.tools.dbt.templates as templates
from app.models.project import DbtRepo
from app.models.data_profile import LandingZoneDataProfile
from app.services.github_service import GitHubService, GitHubError


class CreateDbtStagingModelTool(BaseTool):
    """Generates a dbt staging model (SQL + schema.yml) for a landing zone's
    Bronze table, using the data profile captured back when create_landing_zone
    ran — never re-asks the user for a description or samples. Table/column
    descriptions in the generated schema.yml become real Snowflake COMMENT
    metadata (visible in Snowsight, SHOW TABLES, etc.) the next time `dbt run`/
    `dbt build` actually executes, via persist_docs — Canary generates the
    config and opens the PR, it never runs dbt itself, so nothing reaches
    Snowflake until that PR is merged and a dbt run happens afterward."""

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "create_dbt_staging_model"

    @property
    def description(self) -> str:
        return (
            "Generate a dbt staging model for a landing zone's Bronze table — extracts each column from "
            "RAW_DATA (the VARIANT column) with the right type cast, and writes a schema.yml with the "
            "table's and every column's description. Those descriptions get pushed into Snowflake as "
            "native table/column comments (via persist_docs) the next time dbt actually runs — this tool "
            "only opens the PR, it doesn't run dbt itself, so nothing shows up in Snowflake until that PR "
            "merges and a dbt run happens. "
            "Requires a data profile already captured for this landing zone (create_landing_zone collects "
            "this automatically) and a dbt repo already connected (POST /api/v1/dbt/repo) — if either is "
            "missing, this tells you which. "
            "Requires the Bronze table's actual database/schema/table name (from the {name}-pipe setup) "
            "since that isn't stored anywhere queryable yet — ask the user if it's ambiguous."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "landing_zone_name": {
                    "type": "string",
                    "description": "Landing zone name — must already have a data profile from create_landing_zone.",
                },
                "bronze_database": {
                    "type": "string",
                    "description": "Snowflake database containing the Bronze table (e.g. BUTTERCUP).",
                },
                "bronze_schema": {
                    "type": "string",
                    "description": "Snowflake schema containing the Bronze table (e.g. BRONZE_CONFIDENTIAL).",
                },
                "bronze_table_name": {
                    "type": "string",
                    "description": "Unqualified Bronze table name (e.g. RAW_BUTTERCUP).",
                },
                "model_name": {
                    "type": "string",
                    "description": "dbt model name. Defaults to stg_{landing_zone_name}.",
                },
            },
            "required": ["landing_zone_name", "bronze_database", "bronze_schema", "bronze_table_name"],
        }

    async def execute(
        self,
        landing_zone_name: str,
        bronze_database: str,
        bronze_schema: str,
        bronze_table_name: str,
        model_name: str | None = None,
    ) -> str:
        repo_result = await self._db.execute(select(DbtRepo).where(DbtRepo.account_id == self._account_id))
        repo = repo_result.scalar_one_or_none()
        if not repo:
            return "No dbt repo connected for this account. Use POST /api/v1/dbt/repo first."

        # A landing zone created with multiple tables (see create_landing_zone's `tables`
        # list) has one profile row per table_name — match this call's bronze_table_name
        # to the right one. Landing zones created before per-table profiles existed have
        # a single row with a null table_name describing their one (implicit) table —
        # fall back to that if there's no exact match.
        profile_result = await self._db.execute(
            select(LandingZoneDataProfile).where(
                LandingZoneDataProfile.account_id == self._account_id,
                LandingZoneDataProfile.landing_zone_name == landing_zone_name,
                func.upper(LandingZoneDataProfile.table_name) == bronze_table_name.upper(),
            )
        )
        profile = profile_result.scalar_one_or_none()
        if not profile:
            legacy_result = await self._db.execute(
                select(LandingZoneDataProfile).where(
                    LandingZoneDataProfile.account_id == self._account_id,
                    LandingZoneDataProfile.landing_zone_name == landing_zone_name,
                    LandingZoneDataProfile.table_name.is_(None),
                )
            )
            profile = legacy_result.scalar_one_or_none()
        if not profile or not profile.columns:
            return (
                f"No data profile found for landing zone '{landing_zone_name}' table '{bronze_table_name}' "
                "— create_landing_zone collects this automatically from each table's sample files when "
                "the landing zone is first set up. Run that first (or re-run it with sample_files for "
                "this table if it predates per-table profiles)."
            )

        model_name = templates.sanitize_identifier(model_name or f"stg_{landing_zone_name}")
        project_name = templates.sanitize_identifier(repo.repo_full_name.split("/")[-1])

        base_path = "" if repo.dbt_base_path in (".", "") else repo.dbt_base_path.strip("/")
        svc = GitHubService(
            token=repo.token,
            repo_full_name=repo.repo_full_name,
            branch=repo.branch,
            api_url=repo.api_url,
            base_path=base_path,
        )

        files: dict[str, bytes] = {}
        existing_project_file = await svc.get_file_content("dbt_project.yml", ref=repo.branch)
        wrote_project_file = existing_project_file is None
        if wrote_project_file:
            files["dbt_project.yml"] = templates.dbt_project_yml(project_name).encode()

        sql = templates.staging_model_sql(bronze_database, bronze_schema, bronze_table_name, profile.columns)
        schema_yml = templates.staging_model_schema_yml(model_name, profile.description, profile.columns)
        files[f"models/staging/{landing_zone_name}/{model_name}.sql"] = sql.encode()
        files[f"models/staging/{landing_zone_name}/{model_name}.yml"] = schema_yml.encode()

        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        feature_branch = f"feat/dbt-{model_name}-{slug}"

        with tempfile.TemporaryDirectory() as staging:
            try:
                pr_url, file_count = await svc.open_pull_request(
                    local_dir=Path(staging),
                    feature_branch=feature_branch,
                    commit_message=f"feat(dbt): add {model_name} staging model\n\nSource: {bronze_database}.{bronze_schema}.{bronze_table_name}",
                    pr_title=f"feat(dbt): add {model_name} staging model",
                    pr_body=(
                        f"## Summary\n\n"
                        f"Adds the `{model_name}` staging model, extracting columns from "
                        f"`{bronze_database}.{bronze_schema}.{bronze_table_name}`'s `RAW_DATA` column.\n\n"
                        + (
                            "Also adds `dbt_project.yml` with `persist_docs` enabled (this repo didn't have "
                            "one yet) — without it, the descriptions below stay inert text in this repo "
                            "instead of becoming real Snowflake column/table comments.\n\n"
                            if wrote_project_file else ""
                        )
                        + f"**These descriptions only reach Snowflake once `dbt run`/`dbt build` actually "
                        f"executes against this model** — merging this PR alone doesn't do it.\n\n"
                        f"## Columns\n\n"
                        f"| Column | Type | Description |\n|---|---|---|\n"
                        + "\n".join(
                            f"| `{c['name']}` | `{templates.snowflake_cast_type(c.get('type'))}` | "
                            f"{c.get('description') or ''} |"
                            for c in profile.columns
                        )
                        + "\n\n---\n🤖 Generated by Canary"
                    ),
                    root_files=files,
                )
            except GitHubError as exc:
                return f"Failed to open PR: {exc}"

        if pr_url is None:
            return f"'{model_name}' already matches what's in {repo.repo_full_name} — no PR needed."

        return (
            f"dbt staging model '{model_name}' generated ({file_count} file(s)).\n\n"
            f"  PR: {pr_url}\n\n"
            "Not auto-merged — dbt model PRs always need manual review, since a wrong extraction or "
            "type cast fails silently rather than loudly the way a bad Terraform apply does.\n\n"
            "Once merged, run `dbt run`/`dbt build` against this model for the descriptions to actually "
            "show up as Snowflake table/column comments — generating this PR doesn't do that by itself."
        )
