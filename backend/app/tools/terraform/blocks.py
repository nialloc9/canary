import difflib
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.tools.base import BaseTool
from app.models.project import GitHubRepo
from app.models.stack import Stack
from app.services.github_service import GitHubService, GitHubError


def _repo_path(base_path: str, *parts: str) -> str:
    segments = [p.strip("/") for p in (base_path, *parts) if p and p.strip("/")]
    return "/".join(segments)


class ListTerragruntBlocksTool(BaseTool):
    """Lists whatever terragrunt blocks actually exist under a stack's
    landing-zone/ directory — landing zone components, Snowpipes, or any
    other generated infrastructure unit — by exact directory name."""

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "list_terragrunt_blocks"

    @property
    def description(self) -> str:
        return (
            "List the exact directory names of every terragrunt block (landing zone components, "
            "Snowpipes, or any other generated infrastructure unit) under a stack's landing-zone/ "
            "directory. Use this before read_terragrunt_block, edit_terragrunt_block, or "
            "remove_terragrunt_block whenever you don't already know the precise block_name(s) — "
            "don't guess a directory name."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "stack_name": {
                    "type": "string",
                    "description": "Stack to list (e.g. 'dev'). Omit to list every stack on the account.",
                },
            },
        }

    async def execute(self, stack_name: str | None = None) -> str:
        repo = await self._get_github_repo()
        if not repo:
            return "No GitHub repo connected. Use POST /api/v1/github/repos first."

        stacks = await self._resolve_stacks(stack_name)
        if isinstance(stacks, str):
            return stacks

        lines = []
        for stack in stacks:
            svc = GitHubService(
                token=repo.token, repo_full_name=repo.repo_full_name,
                branch=stack.branch, api_url=repo.api_url,
            )
            path = _repo_path(repo.infrastructure_base_path, stack.name, "landing-zone")
            try:
                entries = await svc.list_directory(path, ref=stack.branch)
            except GitHubError as exc:
                lines.append(f"{stack.name}: failed to list — {exc}")
                continue
            dirs = sorted(e["name"] for e in entries if e.get("type") == "dir")
            lines.append(f"{stack.name}: {', '.join(dirs) if dirs else '(nothing deployed)'}")
        return "\n".join(lines)

    async def _resolve_stacks(self, stack_name: str | None):
        if stack_name:
            stack = await self._get_stack(stack_name)
            if not stack:
                return f"No stack named '{stack_name}' found for this account."
            return [stack]
        stacks = await self._get_all_stacks()
        if not stacks:
            return "No stacks configured for this account. Add one under Admin → Stacks first."
        return stacks

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


class ReadTerragruntBlockTool(BaseTool):
    """Reads a single block's raw terragrunt.hcl content, so the model has
    real content to base an edit_terragrunt_block call on."""

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "read_terragrunt_block"

    @property
    def description(self) -> str:
        return (
            "Read a specific terragrunt block's current terragrunt.hcl content, so you can propose an "
            "edit with edit_terragrunt_block based on what's actually there. Use list_terragrunt_blocks "
            "first if you don't already know the exact block_name."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "block_name": {
                    "type": "string",
                    "description": "Exact directory name under <stack>/landing-zone/ (e.g. 'buttercup-lz', 'buttercup-pipe')",
                },
                "stack_name": {
                    "type": "string",
                    "description": "Which stack to read from (e.g. 'dev'). Required if the block might "
                    "differ across stacks or you're not sure which one the user means.",
                },
            },
            "required": ["block_name"],
        }

    async def execute(self, block_name: str, stack_name: str | None = None) -> str:
        repo = await self._get_github_repo()
        if not repo:
            return "No GitHub repo connected. Use POST /api/v1/github/repos first."

        stack = await self._resolve_one_stack(stack_name)
        if isinstance(stack, str):
            return stack

        svc = GitHubService(
            token=repo.token, repo_full_name=repo.repo_full_name,
            branch=stack.branch, api_url=repo.api_url,
        )
        path = _repo_path(repo.infrastructure_base_path, stack.name, "landing-zone", block_name, "terragrunt.hcl")
        content = await svc.get_file_content(path, ref=stack.branch)
        if content is None:
            return (
                f"No block named '{block_name}' found on stack '{stack.name}'. Use list_terragrunt_blocks "
                "to see what's actually deployed there."
            )
        return content

    async def _resolve_one_stack(self, stack_name: str | None):
        if stack_name:
            stack = await self._get_stack(stack_name)
            if not stack:
                return f"No stack named '{stack_name}' found for this account."
            return stack
        stacks = await self._get_all_stacks()
        if not stacks:
            return "No stacks configured for this account. Add one under Admin → Stacks first."
        return stacks[0]

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


class EditTerragruntBlockTool(BaseTool):
    """Overwrites a single block's terragrunt.hcl with model-provided
    content. Only ever touches that one file — never modules/ or any other
    block — since it writes a single blob via the GitHub tree API rather
    than syncing a whole directory."""

    def __init__(self, db: AsyncSession, account_id: str):
        self._db = db
        self._account_id = account_id

    @property
    def name(self) -> str:
        return "edit_terragrunt_block"

    @property
    def description(self) -> str:
        return (
            "Overwrite a terragrunt block's terragrunt.hcl with new content you provide — for anything "
            "that isn't a plain S3 landing zone field change (use update_landing_zone for that instead), "
            "e.g. editing a Snowpipe's filters, or any other generated infrastructure unit. Always call "
            "read_terragrunt_block first and base your edit on the real current content — pass the FULL "
            "new file content, not a diff or partial snippet; this replaces the whole file. Never touches "
            "the vendored Terraform modules or any other block. By default this applies to every stack — "
            "always pass stack_name when the request is scoped to one environment. "
            "Requires confirmation: call once with confirm omitted (or false) to preview a diff of exactly "
            "what will change — show that to the user verbatim and wait for them to explicitly confirm in "
            "their next message. Only call again with confirm=true, passing the exact same arguments as "
            "the preview call, after the user has clearly agreed. Never set confirm=true on the first call."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "block_name": {
                    "type": "string",
                    "description": "Exact directory name under <stack>/landing-zone/ (e.g. 'buttercup-lz', 'buttercup-pipe')",
                },
                "content": {
                    "type": "string",
                    "description": "Full new terragrunt.hcl content for this block (not a diff).",
                },
                "stack_name": {
                    "type": "string",
                    "description": "Restrict this edit to a single stack (e.g. 'dev'). Required whenever "
                    "the request is scoped to one environment. Omit only when the user explicitly wants "
                    "it applied to every stack on the account.",
                },
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Leave false (or omit) to preview the diff without opening a PR. Only "
                    "set true after the user has explicitly confirmed the preview.",
                },
            },
            "required": ["block_name", "content"],
        }

    async def execute(
        self, block_name: str, content: str, stack_name: str | None = None, confirm: bool = False
    ) -> str:
        repo = await self._get_github_repo()
        if not repo:
            return "No GitHub repo connected. Use POST /api/v1/github/repos first."

        stacks = await self._resolve_stacks(stack_name)
        if isinstance(stacks, str):
            return stacks

        current_by_stack: dict[str, str | None] = {}
        for stack in stacks:
            svc = GitHubService(
                token=repo.token, repo_full_name=repo.repo_full_name,
                branch=stack.branch, api_url=repo.api_url,
            )
            path = _repo_path(repo.infrastructure_base_path, stack.name, "landing-zone", block_name, "terragrunt.hcl")
            current_by_stack[stack.name] = await svc.get_file_content(path, ref=stack.branch)

        changed = {s: c for s, c in current_by_stack.items() if c != content}
        if not changed:
            return f"'{block_name}' already matches this content on {stack_name or 'every targeted stack'} — nothing to change."

        if not confirm:
            sections = []
            for stack_nm, old in changed.items():
                if old is None:
                    sections.append(f"{stack_nm}: (new file)\n" + "\n".join(f"  + {l}" for l in content.splitlines()))
                else:
                    diff = list(difflib.unified_diff(
                        old.splitlines(), content.splitlines(),
                        fromfile=f"{stack_nm}/current", tofile=f"{stack_nm}/proposed", lineterm="",
                    ))
                    sections.append(f"{stack_nm}:\n" + "\n".join(diff))
            return (
                f"This will overwrite '{block_name}/terragrunt.hcl':\n\n"
                + "\n\n".join(sections)
                + "\n\nThis only rewrites this block's own terragrunt.hcl — it will not touch the vendored "
                "Terraform modules or any other block.\n\nReply to confirm and I'll open the PR(s)."
            )

        results: list[str] = []
        for stack in stacks:
            if stack.name not in changed:
                continue
            svc = GitHubService(
                token=repo.token, repo_full_name=repo.repo_full_name,
                branch=stack.branch, api_url=repo.api_url,
                base_path=repo.infrastructure_base_path,
            )
            slug = datetime.now().strftime("%Y%m%d-%H%M%S")
            feature_branch = f"chore/edit-{block_name}-{stack.name}-{slug}"
            with tempfile.TemporaryDirectory() as staging:
                block_dir = Path(staging) / stack.name / "landing-zone" / block_name
                block_dir.mkdir(parents=True, exist_ok=True)
                (block_dir / "terragrunt.hcl").write_text(content)
                try:
                    pr_url, _ = await svc.open_pull_request(
                        local_dir=Path(staging),
                        feature_branch=feature_branch,
                        commit_message=f"chore({block_name}): update terragrunt config ({stack.name})",
                        pr_title=f"chore({block_name}): update terragrunt config ({stack.name})",
                        pr_body=(
                            f"## Summary\n\nUpdates `{block_name}`'s terragrunt.hcl on the `{stack.name}` "
                            f"stack.\n\n---\n🤖 Generated by Canary"
                        ),
                    )
                except GitHubError as exc:
                    results.append(f"{stack.name}: PR failed — {exc}")
                    continue
            results.append(f"{stack.name}: already up to date, nothing to push" if pr_url is None else f"{stack.name}: {pr_url}")

        return "Edit PR(s):\n" + "\n".join(f"  {r}" for r in results)

    async def _resolve_stacks(self, stack_name: str | None):
        if stack_name:
            stack = await self._get_stack(stack_name)
            if not stack:
                return f"No stack named '{stack_name}' found for this account."
            return [stack]
        stacks = await self._get_all_stacks()
        if not stacks:
            return "No stacks configured for this account. Add one under Admin → Stacks first."
        return stacks

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
