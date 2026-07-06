import json
from pathlib import Path

from pydantic import BaseModel

MODULES_ROOT = Path(__file__).resolve().parents[2] / "terraform" / "modules"

# The module components vendored into every generated landing zone. Adding a
# new component here also requires adding it under each version directory in
# terraform/modules/<version>/.
MODULE_COMPONENTS = (
    "aws/landing-zone",
    "snowflake/database",
    "snowflake/medallion-arch",
    "snowflake/s3-storage-integration",
    "aws/snowflake-pipe",
)


class ModuleVersion(BaseModel):
    version: str
    released_at: str
    notes: str


class ModuleVersionError(Exception):
    pass


def list_module_versions() -> list[ModuleVersion]:
    manifest_path = MODULES_ROOT / "versions.json"
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text())
    return [ModuleVersion(**entry) for entry in data]


def latest_module_version() -> str:
    versions = list_module_versions()
    if not versions:
        raise ModuleVersionError("No terraform module versions published in versions.json")
    return versions[-1].version


def module_version_exists(version: str) -> bool:
    return any(v.version == version for v in list_module_versions())


def module_source_dir(version: str) -> Path:
    return MODULES_ROOT / version
