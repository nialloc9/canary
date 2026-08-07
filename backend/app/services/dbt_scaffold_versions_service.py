import json
from pathlib import Path

from pydantic import BaseModel

SCAFFOLD_ROOT = Path(__file__).resolve().parents[2] / "dbt" / "scaffold"

# Mirrors module_versions_service.py's module-stack pattern: a "scaffold
# stack" is a versioned dbt project skeleton for one warehouse, under
# dbt/scaffold/<stack>/<version>/. snowflake is the only one today — a
# future warehouse (e.g. databricks) is just another top-level directory
# with its own versions.json, nothing to register here.
DEFAULT_SCAFFOLD_STACK = "snowflake"


class ScaffoldVersion(BaseModel):
    version: str
    released_at: str
    notes: str


class ScaffoldVersionError(Exception):
    pass


def list_scaffold_versions(stack: str = DEFAULT_SCAFFOLD_STACK) -> list[ScaffoldVersion]:
    manifest_path = SCAFFOLD_ROOT / stack / "versions.json"
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text())
    return [ScaffoldVersion(**entry) for entry in data]


def latest_scaffold_version(stack: str = DEFAULT_SCAFFOLD_STACK) -> str:
    versions = list_scaffold_versions(stack)
    if not versions:
        raise ScaffoldVersionError(f"No dbt scaffold versions published in {stack}/versions.json")
    return versions[-1].version


def scaffold_version_exists(version: str, stack: str = DEFAULT_SCAFFOLD_STACK) -> bool:
    return any(v.version == version for v in list_scaffold_versions(stack))


def scaffold_source_dir(version: str, stack: str = DEFAULT_SCAFFOLD_STACK) -> Path:
    return SCAFFOLD_ROOT / stack / version
