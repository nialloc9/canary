import json
from pathlib import Path

from pydantic import BaseModel

MODULES_ROOT = Path(__file__).resolve().parents[2] / "terraform" / "modules"

# A "module stack" is a named, self-contained set of Terraform modules for one
# platform combination (cloud + warehouse), versioned independently of every
# other stack under terraform/modules/<stack>/<version>/ — see
# stack_components(). aws-snowflake is the only one today; a future stack
# (e.g. a different cloud/warehouse pairing) is just another top-level
# directory with its own versions.json, nothing to register here.
DEFAULT_MODULE_STACK = "aws-snowflake"


class ModuleVersion(BaseModel):
    version: str
    released_at: str
    notes: str


class ModuleVersionError(Exception):
    pass


def list_module_versions(stack: str = DEFAULT_MODULE_STACK) -> list[ModuleVersion]:
    manifest_path = MODULES_ROOT / stack / "versions.json"
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text())
    return [ModuleVersion(**entry) for entry in data]


def latest_module_version(stack: str = DEFAULT_MODULE_STACK) -> str:
    versions = list_module_versions(stack)
    if not versions:
        raise ModuleVersionError(f"No terraform module versions published in {stack}/versions.json")
    return versions[-1].version


def module_version_exists(version: str, stack: str = DEFAULT_MODULE_STACK) -> bool:
    return any(v.version == version for v in list_module_versions(stack))


def module_source_dir(version: str, stack: str = DEFAULT_MODULE_STACK) -> Path:
    return MODULES_ROOT / stack / version


def stack_components(version: str, stack: str = DEFAULT_MODULE_STACK) -> list[str]:
    """Every module directory in this stack/version, discovered by presence
    of a .tf file, returned as paths relative to the version root (e.g.
    "aws/landing-zone"). Vendoring copies every one of these for every
    landing zone regardless of which are actually used — dropping a new
    module in under the version directory is enough for it to be picked up;
    there's no separate list to remember to update, so it can't go stale."""
    version_dir = module_source_dir(version, stack)
    if not version_dir.exists():
        return []
    module_dirs = {tf.parent for tf in version_dir.rglob("*.tf")}
    return sorted(str(d.relative_to(version_dir)) for d in module_dirs)
