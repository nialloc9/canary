"""Builds a visual topology of what's actually deployed to a stack, by reading
the generated Terragrunt config straight from GitHub — not from our own DB
records of what tools were called, which can drift if someone edits the repo
directly. Cached in memory per stack with a short TTL; callers can force a
refresh to bypass it.
"""
import re
import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.project import GitHubRepo
from app.models.stack import Stack
from app.services.github_service import GitHubService, GitHubError

CACHE_TTL_SECONDS = 300

# terragrunt.hcl `source = "${get_parent_terragrunt_dir()}/<module path>"` -> node type.
# This is the reliable signal for what a component *is*, independent of naming.
MODULE_PATH_TO_TYPE = {
    "modules/aws/landing-zone": "s3_bucket",
    "modules/snowflake/database": "snowflake_database",
    "modules/snowflake/medallion-arch": "medallion_schemas",
    "modules/snowflake/s3-storage-integration": "storage_integration",
    "modules/aws/snowflake-pipe": "snowpipe",
}

# Folder suffixes our own templates use, longest/most-specific first so
# "-db-arch" doesn't get mis-stripped as "-db".
_COMPONENT_SUFFIXES = ["-db-arch", "-lz", "-si", "-pipe", "-db"]

_SOURCE_RE = re.compile(r'source\s*=\s*"\$\{get_parent_terragrunt_dir\(\)\}/([\w/-]+)"')
_DEPENDENCY_RE = re.compile(r'config_path\s*=\s*"\.\./([\w-]+)"')
_SCALAR_RE = re.compile(r'^\s*([a-z][a-z0-9_]*)\s*=\s*"([^"]*)"', re.MULTILINE)
_ARRAY_RE = re.compile(r'^\s*([a-z][a-z0-9_]*)\s*=\s*\[(.*?)\]', re.MULTILINE | re.DOTALL)
_BOOL_RE = re.compile(r'^\s*([a-z][a-z0-9_]*)\s*=\s*(true|false)\s*$', re.MULTILINE)


@dataclass
class TopologyNode:
    id: str
    landing_zone: str
    type: str
    label: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class TopologyEdge:
    source: str
    target: str


@dataclass
class SkippedEntry:
    dir: str
    reason: str


@dataclass
class Topology:
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    fetched_at: float
    connected: bool  # False if no GitHub repo is connected at all
    error: str | None = None  # set if a repo is connected but the fetch itself failed
    skipped: list[SkippedEntry] = field(default_factory=list)  # dirs found but not recognized as a component


_cache: dict[str, tuple[float, Topology]] = {}


def _split_component(dir_name: str) -> tuple[str, str] | None:
    """Split e.g. "cress-db-arch" into ("cress", "-db-arch"). Returns None if
    the folder doesn't match any known component suffix."""
    for suffix in _COMPONENT_SUFFIXES:
        if dir_name.endswith(suffix):
            return dir_name[: -len(suffix)], suffix
    return None


def _parse_fields(content: str) -> dict[str, str]:
    """Extract simple scalar/array fields from the *last* `inputs = { ... }`
    block in the file (always the final top-level block in our templates —
    scoping to it avoids picking up `dependency`/`mock_outputs` noise)."""
    marker = content.rfind("inputs = {")
    body = content[marker:] if marker != -1 else content

    fields: dict[str, str] = {}
    for key, value in _SCALAR_RE.findall(body):
        if key not in fields:
            fields[key] = value
    for key, value in _ARRAY_RE.findall(body):
        items = [v.strip().strip('"') for v in value.split(",") if v.strip()]
        if items:
            fields[key] = ", ".join(items)
    for key, value in _BOOL_RE.findall(body):
        if key not in fields:
            fields[key] = value
    return fields


_TYPE_LABELS = {
    "s3_bucket": "S3 Bucket",
    "snowflake_database": "Snowflake Database",
    "medallion_schemas": "Medallion Schemas",
    "storage_integration": "Storage Integration",
    "snowpipe": "Snowpipe",
}


def _parse_component(dir_name: str, content: str) -> tuple[TopologyNode | None, str | None]:
    """Returns (node, None) on success, or (None, reason) if this directory
    couldn't be recognized as a component — so callers can tell the user
    *why* something they know exists isn't showing up, instead of it just
    silently vanishing."""
    split = _split_component(dir_name)
    if not split:
        return None, (
            f"'{dir_name}' doesn't end with a recognized component suffix "
            f"({', '.join(_COMPONENT_SUFFIXES)})"
        )
    landing_zone, _ = split

    source_match = _SOURCE_RE.search(content)
    if not source_match:
        return None, f"'{dir_name}/terragrunt.hcl' has no recognizable `source = \"...\"` line"
    module_path = source_match.group(1)
    node_type = MODULE_PATH_TO_TYPE.get(module_path)
    if not node_type:
        return None, f"'{dir_name}' points at an unrecognized module source '{module_path}'"

    return TopologyNode(
        id=dir_name,
        landing_zone=landing_zone,
        type=node_type,
        label=_TYPE_LABELS[node_type],
        fields=_parse_fields(content),
    ), None


async def _get_repo(db: AsyncSession, account_id: str) -> GitHubRepo | None:
    result = await db.execute(select(GitHubRepo).where(GitHubRepo.account_id == account_id))
    return result.scalar_one_or_none()


async def get_stack_topology(
    db: AsyncSession, account_id: str, stack: Stack, force_refresh: bool = False
) -> Topology:
    cache_key = stack.id
    if not force_refresh and cache_key in _cache:
        ts, cached = _cache[cache_key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return cached

    repo = await _get_repo(db, account_id)
    if not repo:
        topology = Topology(nodes=[], edges=[], fetched_at=time.time(), connected=False)
        _cache[cache_key] = (time.time(), topology)
        return topology

    svc = GitHubService(token=repo.token, repo_full_name=repo.repo_full_name, branch=repo.branch, api_url=repo.api_url)
    base = f"{repo.infrastructure_base_path}/{stack.name}/landing-zone" if repo.infrastructure_base_path else f"{stack.name}/landing-zone"

    try:
        entries = await svc.list_directory(base, ref=repo.branch)
        dirs = [e["name"] for e in entries if e.get("type") == "dir"]

        nodes: list[TopologyNode] = []
        edges: list[TopologyEdge] = []
        skipped: list[SkippedEntry] = []
        for component_dir in dirs:
            content = await svc.get_file_content(f"{base}/{component_dir}/terragrunt.hcl", ref=repo.branch)
            if not content:
                skipped.append(SkippedEntry(dir=component_dir, reason="no terragrunt.hcl found in this directory"))
                continue
            node, reason = _parse_component(component_dir, content)
            if not node:
                skipped.append(SkippedEntry(dir=component_dir, reason=reason or "unknown"))
                continue
            nodes.append(node)
            # dependency's config_path points at what this node *consumes from* —
            # data flows dependency -> this node, so that's the edge direction.
            for dep_id in _DEPENDENCY_RE.findall(content):
                edges.append(TopologyEdge(source=dep_id, target=node.id))
    except GitHubError as exc:
        topology = Topology(nodes=[], edges=[], fetched_at=time.time(), connected=True, error=str(exc))
        _cache[cache_key] = (time.time(), topology)
        return topology

    # Drop edges whose endpoints weren't actually found (e.g. a dependency on
    # a component that failed to parse).
    node_ids = {n.id for n in nodes}
    edges = [e for e in edges if e.source in node_ids and e.target in node_ids]

    topology = Topology(nodes=nodes, edges=edges, fetched_at=time.time(), connected=True, skipped=skipped)
    _cache[cache_key] = (time.time(), topology)
    return topology
