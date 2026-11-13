import subprocess
import tempfile


class GitOpsError(Exception):
    pass


def clone_repo(token: str, repo_full_name: str, branch: str) -> str:
    """Shallow-clone repo_full_name at branch into a fresh temp dir. Caller
    is responsible for cleaning up the returned directory."""
    clone_dir = tempfile.mkdtemp(prefix="canary-git-")
    clone_url = f"https://{token}@github.com/{repo_full_name}.git"
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, clone_url, clone_dir],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise GitOpsError(
            f"Failed to clone {repo_full_name} (branch '{branch}'): {exc.stderr.decode(errors='replace')}"
        ) from exc
    return clone_dir


def has_changes(clone_dir: str) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=clone_dir, check=True, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def commit_and_push(clone_dir: str, feature_branch: str, commit_message: str) -> None:
    try:
        subprocess.run(["git", "checkout", "-b", feature_branch], cwd=clone_dir, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=clone_dir, check=True, capture_output=True)
        subprocess.run(
            [
                "git", "-c", "user.email=canary@pensievetechnologies.com", "-c", "user.name=Canary",
                "commit", "-m", commit_message,
            ],
            cwd=clone_dir, check=True, capture_output=True,
        )
        subprocess.run(["git", "push", "origin", feature_branch], cwd=clone_dir, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise GitOpsError(f"Git push failed: {exc.stderr.decode(errors='replace')}") from exc
