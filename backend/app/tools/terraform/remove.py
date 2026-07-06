import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
from app.tools.terraform.blocks import _repo_path
from app.models.project import GitHubRepo
from app.models.stack import Stack
from app.services.git_ops import clone_repo, has_changes, commit_and_push, GitOpsError
from app.services.github_service import GitHubService, GitHubError


class RemoveTerragruntBlockTool(BaseTool):
    """Removes one or more terragrunt blocks (landing zone components, a
    Snowpipe, or any other generated infrastructure unit) via a PR. Never
    touches the vendored Terraform modules or any other block."""

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "remove_terragrunt_block"

    @property
    def description(self) -> str:
        return (
            "Remove one or more terragrunt blocks (landing zone components, a Snowpipe, or any other "
            "generated infrastructure unit) by deleting their directories via a PR. Pass every block_name "
            "that should come out together so they're removed atomically in one PR — e.g. all four of "
            "'{name}-db', '{name}-db-arch', '{name}-lz', '{name}-si' to remove a landing zone entirely, or "
            "just '{name}-pipe' to remove only its Snowpipe. Use list_terragrunt_blocks first if you don't "
            "already know the exact block_name(s). Never touches the vendored Terraform modules or any "
            "other block. Deleting the terragrunt config does NOT destroy the already-deployed cloud/"
            "Snowflake resources — merging the PR only stops Terraform from managing them going forward; "
            "say this explicitly if the user seems to expect otherwise. By default this applies to every "
            "stack — always pass stack_name when the request is scoped to one environment (e.g. 'only in "
            "dev'), otherwise you will silently remove it from every other stack too. "
            "Requires confirmation: call once with confirm omitted (or false) to preview exactly what "
            "would be deleted — show that to the user verbatim and wait for them to explicitly confirm "
            "in their next message. Only call again with confirm=true, passing the exact same arguments "
            "as the preview call, after the user has clearly agreed. Never set confirm=true on the first "
            "call."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "block_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "Exact directory name(s) under <stack>/landing-zone/ to remove.",
                },
                "stack_name": {
                    "type": "string",
                    "description": "Restrict this removal to a single stack (e.g. 'dev'). Required "
                    "whenever the request is scoped to one environment. Omit only when the user "
                    "explicitly wants it removed from every stack on the account.",
                },
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Leave false (or omit) to preview what would be deleted without "
                    "opening a PR. Only set true after the user has explicitly confirmed the preview.",
                },
            },
            "required": ["block_names"],
        }

    async def execute(
        self, block_names: list[str], stack_name: str | None = None, confirm: bool = False
    ) -> str:
        repo = await self._get_github_repo()
        if not repo:
            return "No GitHub repo connected. Use POST /api/v1/github/repos first."

        if stack_name:
            stack = await self._get_stack(stack_name)
            if not stack:
                return f"No stack named '{stack_name}' found for this account."
            stacks = [stack]
        else:
            stacks = await self._get_all_stacks()
            if not stacks:
                return "No stacks configured for this account. Add one under Admin → Stacks first."

        found = await self._discover(repo, stacks, block_names)
        if not found:
            scope = f"stack '{stack_name}'" if stack_name else "any stack"
            return f"None of {block_names} are deployed on {scope} — nothing to remove."

        if not confirm:
            lines = "\n".join(f"  {s}: {', '.join(dirs)}" for s, dirs in found.items())
            return (
                f"This will delete the following terragrunt directories:\n\n{lines}\n\n"
                "This only removes these blocks' terragrunt config — it will not touch the vendored "
                "Terraform modules or any other block, and it does NOT destroy the already-deployed "
                "cloud/Snowflake resources; merging the resulting PR(s) just stops Terraform from "
                "managing them going forward.\n\n"
                "Reply to confirm and I'll open the PR(s)."
            )

        results: list[str] = []
        for stack in stacks:
            if stack.name not in found:
                continue
            clone_dir = None
            try:
                clone_dir = clone_repo(repo.token, repo.repo_full_name, stack.branch)
                base = self._env_dir(clone_dir, repo.infrastructure_base_path, stack.name)
                for component in found[stack.name]:
                    shutil.rmtree(base / component, ignore_errors=True)

                if not has_changes(clone_dir):
                    results.append(f"{stack.name}: already up to date, nothing to push")
                    continue

                slug = datetime.now().strftime("%Y%m%d-%H%M%S")
                feature_branch = f"chore/remove-blocks-{stack.name}-{slug}"
                commit_and_push(
                    clone_dir, feature_branch,
                    f"chore(terragrunt): remove {', '.join(found[stack.name])} from {stack.name}",
                )

                svc = GitHubService(
                    token=repo.token,
                    repo_full_name=repo.repo_full_name,
                    branch=stack.branch,
                    api_url=repo.api_url,
                )
                pr_url = await svc.open_branch_pr(
                    head=feature_branch,
                    base=stack.branch,
                    title=f"chore(terragrunt): remove {', '.join(found[stack.name])} from {stack.name}",
                    body=(
                        f"## Summary\n\n"
                        f"Removes the following terragrunt blocks from the `{stack.name}` stack: "
                        f"{', '.join(found[stack.name])}.\n\n"
                        f"This does not destroy the underlying cloud/Snowflake resources — run "
                        f"`terragrunt destroy` against them separately if that's also needed.\n\n"
                        f"---\n🤖 Generated by Canary"
                    ),
                )
                results.append(f"{stack.name}: {pr_url}")
            except GitOpsError as exc:
                results.append(f"{stack.name}: failed — {exc}")
            except GitHubError as exc:
                results.append(f"{stack.name}: PR failed — {exc}")
            finally:
                if clone_dir:
                    shutil.rmtree(clone_dir, ignore_errors=True)

        return "Removal PR(s):\n" + "\n".join(f"  {r}" for r in results)

    # ------------------------------------------------------------------

    async def _discover(
        self, repo: GitHubRepo, stacks: list[Stack], block_names: list[str]
    ) -> dict[str, list[str]]:
        """For each stack, check (via the GitHub Contents API — no clone
        needed) which of the requested block_names actually exist."""
        found: dict[str, list[str]] = {}
        for stack in stacks:
            svc = GitHubService(
                token=repo.token, repo_full_name=repo.repo_full_name,
                branch=stack.branch, api_url=repo.api_url,
            )
            present = []
            for block_name in block_names:
                path = _repo_path(
                    repo.infrastructure_base_path, stack.name, "landing-zone", block_name, "terragrunt.hcl"
                )
                content = await svc.get_file_content(path, ref=stack.branch)
                if content is not None:
                    present.append(block_name)
            if present:
                found[stack.name] = present
        return found

    @staticmethod
    def _env_dir(clone_dir: str, base_path: str, stack_name: str) -> Path:
        base = Path(clone_dir)
        if base_path.strip("/"):
            base = base / base_path.strip("/")
        return base / stack_name / "landing-zone"

    async def _get_github_repo(self) -> "GitHubRepo | None":
        result = await self._db.execute(select(GitHubRepo).where(GitHubRepo.account_id == self._account_id))
        return result.scalar_one_or_none()

    async def _get_stack(self, name: str) -> "Stack | None":
        result = await self._db.execute(
            select(Stack).where(Stack.account_id == self._account_id, Stack.name == name)
        )
        return result.scalar_one_or_none()

    async def _get_all_stacks(self) -> list[Stack]:
        result = await self._db.execute(
            select(Stack).where(Stack.account_id == self._account_id).order_by(Stack.sort_order)
        )
        return list(result.scalars().all())
