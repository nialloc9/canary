"""Release flow: promotes a stack's branch into prod (main) and/or dev (develop).

- Releasing to prod: creates a new branch off prod's tip, merges the source
  stack's branch into it — favoring prod's side on any conflicting lines, per
  policy, with a commit message documenting what happened — then opens two
  PRs from that one branch: one to prod, one to dev (keeps dev in sync with
  what's shipping to prod).
- Releasing to dev only (a non-dev/non-prod stack choosing "develop" as its
  target): a direct PR from the source branch to dev's branch, no merge needed
  since prod isn't involved.

The "dev" stack can only release to prod (there's nothing upstream of it but
prod). The "prod" stack can't release at all — it's already production.
"""
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.project import GitHubRepo
from app.models.stack import Stack
from app.services.github_service import GitHubService, GitHubError

GIT_AUTHOR_NAME = "Canary"
GIT_AUTHOR_EMAIL = "canary@pensievetechnologies.com"


class ReleaseError(Exception):
    pass


@dataclass
class ConflictInfo:
    path: str
    ours: str | None  # None means this side deleted the file
    theirs: str | None


class ReleaseConflictError(ReleaseError):
    """Raised when the merge hits conflicts an -X ours strategy couldn't
    auto-resolve (structural conflicts: add/add, rename/delete, modify/delete).
    Carries both sides' content per conflicted path so the caller can show
    the user a choice, then retry with `resolutions`."""

    def __init__(self, conflicts: list[ConflictInfo], source_branch: str, target_branch: str):
        self.conflicts = conflicts
        self.source_branch = source_branch
        self.target_branch = target_branch
        super().__init__(f"{len(conflicts)} file(s) need manual conflict resolution")


@dataclass
class ReleaseResult:
    pr_urls: list[str]
    branch: str | None = None


async def _get_repo(db: AsyncSession, account_id: str) -> GitHubRepo:
    result = await db.execute(select(GitHubRepo).where(GitHubRepo.account_id == account_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise ReleaseError("No GitHub repo connected. Use POST /api/v1/github/repos first.")
    return repo


async def _get_stack(db: AsyncSession, account_id: str, name: str) -> Stack:
    result = await db.execute(select(Stack).where(Stack.account_id == account_id, Stack.name == name))
    stack = result.scalar_one_or_none()
    if not stack:
        raise ReleaseError(f"No '{name}' stack found for this account.")
    return stack


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _clone(repo: GitHubRepo, clone_dir: Path) -> None:
    clone_url = f"https://{repo.token}@github.com/{repo.repo_full_name}.git"
    result = subprocess.run(["git", "clone", clone_url, str(clone_dir)], capture_output=True, text=True)
    if result.returncode != 0:
        raise ReleaseError(f"Failed to clone {repo.repo_full_name}: {result.stderr}")
    _run(["git", "config", "user.email", GIT_AUTHOR_EMAIL], clone_dir)
    _run(["git", "config", "user.name", GIT_AUTHOR_NAME], clone_dir)


def _show_stage(clone_dir: Path, stage: int, path: str) -> str | None:
    """Content of `path` at the given merge stage (2 = ours, 3 = theirs).
    None means that side has no entry for this path (e.g. it deleted it)."""
    r = _run(["git", "show", f":{stage}:{path}"], clone_dir)
    return r.stdout if r.returncode == 0 else None


def _collect_conflicts(clone_dir: Path) -> list[ConflictInfo]:
    r = _run(["git", "diff", "--name-only", "--diff-filter=U"], clone_dir)
    paths = [p for p in r.stdout.splitlines() if p.strip()]
    return [
        ConflictInfo(path=p, ours=_show_stage(clone_dir, 2, p), theirs=_show_stage(clone_dir, 3, p))
        for p in paths
    ]


def _apply_resolution(clone_dir: Path, conflict: ConflictInfo, choice: str) -> None:
    if choice not in ("ours", "theirs"):
        raise ReleaseError(f"Invalid resolution '{choice}' for '{conflict.path}' — must be 'ours' or 'theirs'")

    content = conflict.ours if choice == "ours" else conflict.theirs
    if content is None:
        # That side deleted the file — resolving to it means the file goes away.
        _run(["git", "rm", "-f", conflict.path], clone_dir)
        return

    r = _run(["git", "checkout", f"--{choice}", "--", conflict.path], clone_dir)
    if r.returncode != 0:
        raise ReleaseError(f"Failed to resolve '{conflict.path}' to {choice}: {r.stdout}\n{r.stderr}")
    _run(["git", "add", "--", conflict.path], clone_dir)


def _in_base_path(path: str, base_path: str) -> bool:
    return not base_path or path == base_path or path.startswith(base_path + "/")


def _restrict_to_path(clone_dir: Path, base_path: str, keep_ref: str) -> None:
    """Discard any merge changes outside base_path, restoring them to keep_ref's
    content — every other tool scopes its GitHub reads/writes to
    infrastructure_base_path, and the release merge should too, so a release
    PR never drags in unrelated repo-root content the target branch doesn't
    have. No-op when base_path is empty (whole repo is in scope)."""
    if not base_path:
        return
    diff = _run(
        ["git", "diff", "--name-only", keep_ref, "--", ".", f":(exclude){base_path}/**", f":(exclude){base_path}"],
        clone_dir,
    )
    for path in (p for p in diff.stdout.splitlines() if p.strip()):
        existed = _run(["git", "cat-file", "-e", f"{keep_ref}:{path}"], clone_dir).returncode == 0
        if existed:
            _run(["git", "checkout", keep_ref, "--", path], clone_dir)
        else:
            _run(["git", "rm", "-f", "--ignore-unmatch", "--", path], clone_dir)


async def release_stack(
    db: AsyncSession,
    account_id: str,
    source_stack_name: str,
    target: str,
    resolutions: dict[str, str] | None = None,
) -> ReleaseResult:
    if target not in ("prod", "develop"):
        raise ReleaseError("target must be 'prod' or 'develop'")
    if source_stack_name == "prod":
        raise ReleaseError("The 'prod' stack cannot be released — it's already production.")
    if source_stack_name == "dev" and target != "prod":
        raise ReleaseError("The 'dev' stack can only release to prod.")

    repo = await _get_repo(db, account_id)
    source_stack = await _get_stack(db, account_id, source_stack_name)
    prod_stack = await _get_stack(db, account_id, "prod")
    dev_stack = await _get_stack(db, account_id, "dev")

    if target == "develop":
        return await _release_to_dev(repo, source_stack, dev_stack)
    return await _release_to_prod(repo, source_stack, prod_stack, dev_stack, resolutions=resolutions)


async def _release_to_dev(repo: GitHubRepo, source_stack: Stack, dev_stack: Stack) -> ReleaseResult:
    svc = GitHubService(token=repo.token, repo_full_name=repo.repo_full_name, branch=dev_stack.branch, api_url=repo.api_url)
    try:
        pr_url = await svc.open_branch_pr(
            head=source_stack.branch,
            base=dev_stack.branch,
            title=f"release: {source_stack.name} → {dev_stack.name}",
            body=(
                f"## Release\n\n"
                f"Promotes `{source_stack.branch}` (**{source_stack.name}**) into "
                f"`{dev_stack.branch}` (**{dev_stack.name}**).\n\n"
                f"---\n🤖 Generated by Canary"
            ),
        )
    except GitHubError as exc:
        raise ReleaseError(str(exc))
    return ReleaseResult(pr_urls=[pr_url])


async def _release_to_prod(
    repo: GitHubRepo, source_stack: Stack, prod_stack: Stack, dev_stack: Stack,
    resolutions: dict[str, str] | None = None,
) -> ReleaseResult:
    base_path = repo.infrastructure_base_path.strip("/")
    clone_dir = Path(tempfile.mkdtemp(prefix="release-"))
    try:
        _clone(repo, clone_dir)

        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        prod_release_branch = f"release/{source_stack.name}-to-{prod_stack.name}-{slug}"

        r = _run(["git", "checkout", "-b", prod_release_branch, f"origin/{prod_stack.branch}"], clone_dir)
        if r.returncode != 0:
            raise ReleaseError(f"Failed to branch from '{prod_stack.branch}': {r.stderr}")

        commit_message = (
            f"release: promote {source_stack.name} ({source_stack.branch}) into "
            f"{prod_stack.name} ({prod_stack.branch})\n\n"
            f"Merges the accumulated changes from `{source_stack.branch}` into a release branch\n"
            f"based on `{prod_stack.branch}`. Where conflicts existed, `{prod_stack.branch}`'s\n"
            f"version was kept (production is authoritative on conflicting lines); all\n"
            f"non-conflicting changes from `{source_stack.branch}` are included as-is.\n\n"
            f"Scoped to `{base_path}/` — nothing outside the Terraform tree is touched.\n\n"
            f"This branch is opened as two PRs:\n"
            f"- -> {prod_stack.branch}: ships the release to production\n"
            f"- -> {dev_stack.branch}: keeps {dev_stack.name} in sync with what's going to prod"
        )

        r = _run(
            ["git", "merge", "--no-ff", "--no-commit", "-X", "ours", f"origin/{source_stack.branch}"],
            clone_dir,
        )
        has_conflicts = bool(_run(["git", "diff", "--name-only", "--diff-filter=U"], clone_dir).stdout.strip())
        if r.returncode != 0 or has_conflicts:
            conflicts = _collect_conflicts(clone_dir)
            if not conflicts:
                # Not a content conflict at all (e.g. bad ref, dirty tree) — surface
                # everything git said, since neither stream alone may have it.
                raise ReleaseError(
                    f"Merge failed unexpectedly.\n{r.stdout}\n{r.stderr}".strip()
                )

            # Conflicts outside the Terraform tree don't matter — that content
            # gets discarded by _restrict_to_path below regardless of how it
            # resolves, so auto-resolve those and only bother the user about
            # ones that actually affect what's being released.
            in_scope = [c for c in conflicts if _in_base_path(c.path, base_path)]
            out_of_scope = [c for c in conflicts if not _in_base_path(c.path, base_path)]
            for conflict in out_of_scope:
                _apply_resolution(clone_dir, conflict, "ours")

            if in_scope:
                if not resolutions:
                    raise ReleaseConflictError(in_scope, source_stack.branch, prod_stack.branch)

                missing = [c.path for c in in_scope if c.path not in resolutions]
                if missing:
                    raise ReleaseError(
                        f"Missing a resolution for: {', '.join(missing)}. Resolve every conflicted "
                        "path before retrying."
                    )
                for conflict in in_scope:
                    _apply_resolution(clone_dir, conflict, resolutions[conflict.path])

        _restrict_to_path(clone_dir, base_path, f"origin/{prod_stack.branch}")

        r = _run(["git", "commit", "-m", commit_message], clone_dir)
        if r.returncode != 0:
            raise ReleaseError(f"Failed to commit release branch: {r.stdout}\n{r.stderr}".strip())

        r = _run(["git", "push", "origin", prod_release_branch], clone_dir)
        if r.returncode != 0:
            raise ReleaseError(f"Failed to push release branch: {r.stderr}")

        # A separate branch off dev's own tip, carrying over only the same
        # resolved Terraform tree — so the dev PR only ever shows infra
        # changes too, never unrelated repo-root content dev doesn't have.
        dev_release_branch = f"release/{source_stack.name}-to-{dev_stack.name}-{slug}"
        r = _run(["git", "checkout", "-b", dev_release_branch, f"origin/{dev_stack.branch}"], clone_dir)
        if r.returncode != 0:
            raise ReleaseError(f"Failed to branch from '{dev_stack.branch}': {r.stderr}")

        sync_path = base_path or "."
        r = _run(["git", "checkout", prod_release_branch, "--", sync_path], clone_dir)
        if r.returncode != 0:
            raise ReleaseError(f"Failed to sync '{sync_path}' onto {dev_stack.branch}: {r.stderr}")

        dev_commit_message = (
            f"release: sync {dev_stack.name} with {prod_stack.name} ({source_stack.name} release)\n\n"
            f"Applies the same resolved `{base_path}/` tree from the {prod_stack.name} release so "
            f"{dev_stack.name} doesn't drift from what's shipping to {prod_stack.name}."
        )
        r = _run(["git", "commit", "-m", dev_commit_message], clone_dir)
        dev_has_changes = r.returncode == 0
        if not dev_has_changes and "nothing to commit" not in (r.stdout + r.stderr).lower():
            raise ReleaseError(f"Failed to commit dev-sync branch: {r.stdout}\n{r.stderr}".strip())

        if dev_has_changes:
            r = _run(["git", "push", "origin", dev_release_branch], clone_dir)
            if r.returncode != 0:
                raise ReleaseError(f"Failed to push dev-sync branch: {r.stderr}")

        svc = GitHubService(token=repo.token, repo_full_name=repo.repo_full_name, branch=prod_stack.branch, api_url=repo.api_url)

        try:
            prod_pr = await svc.open_branch_pr(
                head=prod_release_branch,
                base=prod_stack.branch,
                title=f"release: {source_stack.name} → {prod_stack.name}",
                body=(
                    f"## Release: {source_stack.name} → {prod_stack.name}\n\n"
                    f"Promotes `{source_stack.branch}` into `{prod_stack.branch}`.\n\n"
                    f"Conflict policy: `{prod_stack.branch}` wins on any conflicting lines. Scoped to "
                    f"`{base_path}/` only.\n\n"
                    f"---\n🤖 Generated by Canary"
                ),
            )
            pr_urls = [prod_pr]
            if dev_has_changes:
                dev_pr = await svc.open_branch_pr(
                    head=dev_release_branch,
                    base=dev_stack.branch,
                    title=f"release: sync {dev_stack.name} with {prod_stack.name} ({source_stack.name} release)",
                    body=(
                        f"## Sync: keep {dev_stack.name} aligned with {prod_stack.name}\n\n"
                        f"Companion PR to the [{prod_stack.name} release]({prod_pr}) — applies the same "
                        f"resolved `{base_path}/` tree to `{dev_stack.branch}` so it doesn't drift from "
                        f"what just shipped to `{prod_stack.branch}`.\n\n---\n🤖 Generated by Canary"
                    ),
                )
                pr_urls.append(dev_pr)
        except GitHubError as exc:
            raise ReleaseError(str(exc))

        return ReleaseResult(pr_urls=pr_urls, branch=prod_release_branch)
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)
