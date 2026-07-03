import base64
from pathlib import Path

import httpx
from nacl import encoding, public

PUBLIC_GITHUB_API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubService:
    """
    Wraps the GitHub Git Data API.

    Works with both github.com (api_url="https://api.github.com") and
    GitHub Enterprise Server (api_url="https://{hostname}/api/v3").

    self._branch is the *target* branch for PRs (e.g. develop).
    Feature branches are created from it and merged back via a PR.
    """

    def __init__(
        self,
        token: str,
        repo_full_name: str,
        branch: str,
        api_url: str = PUBLIC_GITHUB_API,
        base_path: str = "",
    ):
        self._repo = repo_full_name
        self._branch = branch
        self._api_url = api_url.rstrip("/")
        self._infrastructure_base_path = base_path.strip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _repo_url(self, path: str) -> str:
        return f"{self._api_url}/repos/{self._repo}{path}"

    def _repo_path(self, relative: Path) -> str:
        rel_str = relative.as_posix()
        return f"{self._infrastructure_base_path}/{rel_str}" if self._infrastructure_base_path else rel_str

    @staticmethod
    def _raise_for(response: httpx.Response, context: str) -> None:
        if response.is_error:
            detail = response.json().get("message", response.text)
            raise GitHubError(f"{context}: {detail}", status_code=response.status_code)

    async def create_repo(
        self,
        name: str,
        private: bool = True,
        description: str = "",
        org: str | None = None,
        auto_init: bool = True,
    ) -> dict:
        """Create a new GitHub repository. Returns repo metadata."""
        url = (
            f"{self._api_url}/orgs/{org}/repos"
            if org
            else f"{self._api_url}/user/repos"
        )
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            resp = await client.post(url, json={
                "name": name,
                "private": private,
                "description": description,
                "auto_init": auto_init,
            })
            self._raise_for(resp, "Failed to create repository")
            data = resp.json()
            return {
                "full_name": data["full_name"],
                "html_url": data["html_url"],
                "clone_url": data["clone_url"],
                "default_branch": data["default_branch"],
                "private": data["private"],
            }

    async def validate(self) -> dict:
        """Check that the token has access to the repo. Returns repo metadata."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            resp = await client.get(self._repo_url(""))
            self._raise_for(resp, "Failed to access repository")
            data = resp.json()
            return {
                "full_name": data["full_name"],
                "default_branch": data["default_branch"],
                "private": data["private"],
                "html_url": data["html_url"],
            }

    async def branch_exists(self, branch: str) -> bool:
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            resp = await client.get(self._repo_url(f"/git/ref/heads/{branch}"))
            return resp.status_code == 200

    async def create_branch_from(self, new_branch: str, source_branch: str) -> None:
        """Create `new_branch` at the current tip of `source_branch`. Raises
        GitHubError if `source_branch` doesn't exist or creation otherwise fails."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            ref_resp = await client.get(self._repo_url(f"/git/ref/heads/{source_branch}"))
            self._raise_for(ref_resp, f"Failed to find source branch '{source_branch}'")
            sha = ref_resp.json()["object"]["sha"]

            create_resp = await client.post(
                self._repo_url("/git/refs"),
                json={"ref": f"refs/heads/{new_branch}", "sha": sha},
            )
            if create_resp.status_code == 422:
                return  # branch already exists (created concurrently) — fine
            self._raise_for(create_resp, f"Failed to create branch '{new_branch}'")

    async def list_directory(self, path: str, ref: str | None = None) -> list[dict]:
        """List entries in a repo directory at `ref` (defaults to self._branch).
        Returns [] if the path doesn't exist rather than raising."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            resp = await client.get(self._repo_url(f"/contents/{path}"), params={"ref": ref or self._branch})
            if resp.status_code == 404:
                return []
            self._raise_for(resp, f"Failed to list directory '{path}'")
            data = resp.json()
            return data if isinstance(data, list) else []

    async def get_file_content(self, path: str, ref: str | None = None) -> str | None:
        """Fetch a file's decoded text content at `ref` (defaults to self._branch).
        Returns None if it doesn't exist rather than raising."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            resp = await client.get(self._repo_url(f"/contents/{path}"), params={"ref": ref or self._branch})
            if resp.status_code == 404:
                return None
            self._raise_for(resp, f"Failed to fetch file '{path}'")
            data = resp.json()
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return data.get("content", "")

    async def set_secrets(self, secrets: dict[str, str]) -> None:
        """Encrypt and upload a dict of secrets to the repo via the Actions Secrets API."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            key_resp = await client.get(self._repo_url("/actions/secrets/public-key"))
            self._raise_for(key_resp, "Failed to fetch repo public key")
            key_data = key_resp.json()
            key_id = key_data["key_id"]
            public_key = public.PublicKey(base64.b64decode(key_data["key"]))
            sealed_box = public.SealedBox(public_key)

            for name, value in secrets.items():
                encrypted = base64.b64encode(
                    sealed_box.encrypt(value.encode())
                ).decode()
                resp = await client.put(
                    self._repo_url(f"/actions/secrets/{name}"),
                    json={"encrypted_value": encrypted, "key_id": key_id},
                )
                self._raise_for(resp, f"Failed to set secret '{name}'")

    async def open_branch_pr(self, head: str, base: str, title: str, body: str) -> str:
        """Open a PR between two already-pushed branches (no file changes needed —
        used by the release flow, where the git merge already happened locally).
        Returns the PR HTML URL."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            resp = await client.post(
                self._repo_url("/pulls"),
                json={"title": title, "body": body, "head": head, "base": base},
            )
            if resp.status_code == 422:
                existing = await client.get(
                    self._repo_url("/pulls"),
                    params={"head": f"{self._repo.split('/')[0]}:{head}", "base": base, "state": "open"},
                )
                self._raise_for(existing, "Failed to fetch existing pull request")
                pulls = existing.json()
                if pulls:
                    return pulls[0]["html_url"]
                raise GitHubError(f"PR from '{head}' to '{base}' already exists but could not be retrieved")
            self._raise_for(resp, f"Failed to create pull request '{head}' → '{base}'")
            return resp.json()["html_url"]

    async def find_open_pr_by_branch_substring(self, substring: str) -> str | None:
        """Search open PRs targeting self._branch for one whose head branch name
        contains `substring`. Returns the PR's HTML URL, or None if none match.
        Used to give a precise "merge this PR first" hint instead of a generic
        "couldn't find it" error when content genuinely just hasn't landed yet."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            resp = await client.get(
                self._repo_url("/pulls"),
                params={"base": self._branch, "state": "open", "per_page": 100},
            )
            self._raise_for(resp, "Failed to list open pull requests")
            for pr in resp.json():
                if substring in pr.get("head", {}).get("ref", ""):
                    return pr["html_url"]
            return None

    async def merge_pull_request(self, pr_number: int, commit_message: str = "") -> None:
        """Merge an open pull request via squash merge."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            resp = await client.put(
                self._repo_url(f"/pulls/{pr_number}/merge"),
                json={"merge_method": "squash", "commit_message": commit_message},
            )
            self._raise_for(resp, f"Failed to merge PR #{pr_number}")

    async def open_pull_request(
        self,
        local_dir: Path,
        feature_branch: str,
        commit_message: str,
        pr_title: str,
        pr_body: str,
        root_files: dict[str, bytes] | None = None,
    ) -> tuple[str | None, int]:
        """
        Create a feature branch from self._branch, commit all files from local_dir
        (prefixed with infrastructure_base_path) plus any root_files (committed at
        the repo root with no prefix) in a single atomic commit, then open a PR.
        Returns (pr_html_url, file_count). If none of the files actually differ
        from what's already on self._branch, no branch/commit/PR is created and
        pr_html_url is None.
        """
        files: dict[str, bytes] = {
            self._repo_path(path.relative_to(local_dir)): path.read_bytes()
            for path in local_dir.rglob("*")
            if path.is_file()
        }
        if root_files:
            files.update(root_files)
        if not files:
            raise GitHubError("No files to commit")

        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            base_commit_sha, base_tree_sha = await self._get_branch_state(client)
            tree_sha = await self._create_tree(client, files, base_tree_sha)
            if tree_sha == base_tree_sha:
                return None, len(files)

            await self._create_branch(client, feature_branch, base_commit_sha)
            _, commit_sha = await self._create_commit(
                client, commit_message, tree_sha, base_commit_sha
            )
            await self._update_branch_ref(client, feature_branch, commit_sha)
            pr_url = await self._create_pull_request(client, feature_branch, pr_title, pr_body)

        return pr_url, len(files)

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_branch_state(self, client: httpx.AsyncClient) -> tuple[str, str]:
        """Return (latest_commit_sha, base_tree_sha) for self._branch."""
        ref_resp = await client.get(self._repo_url(f"/git/ref/heads/{self._branch}"))
        self._raise_for(ref_resp, f"Failed to get branch '{self._branch}'")
        base_commit_sha = ref_resp.json()["object"]["sha"]

        commit_resp = await client.get(self._repo_url(f"/git/commits/{base_commit_sha}"))
        self._raise_for(commit_resp, "Failed to get base commit")
        base_tree_sha = commit_resp.json()["tree"]["sha"]

        return base_commit_sha, base_tree_sha

    async def _create_branch(
        self, client: httpx.AsyncClient, branch_name: str, sha: str
    ) -> None:
        """Create a new branch at sha. Silently succeeds if the branch already exists."""
        resp = await client.post(
            self._repo_url("/git/refs"),
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        )
        if resp.status_code == 422:
            return  # branch already exists — reuse it
        self._raise_for(resp, f"Failed to create branch '{branch_name}'")

    async def _create_tree(
        self,
        client: httpx.AsyncClient,
        files: dict[str, bytes],
        base_tree_sha: str,
    ) -> str:
        tree_entries = []
        for repo_path, content in files.items():
            blob_resp = await client.post(
                self._repo_url("/git/blobs"),
                json={"content": base64.b64encode(content).decode(), "encoding": "base64"},
            )
            self._raise_for(blob_resp, f"Failed to create blob for '{repo_path}'")
            tree_entries.append({
                "path": repo_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_resp.json()["sha"],
            })

        tree_resp = await client.post(
            self._repo_url("/git/trees"),
            json={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        self._raise_for(tree_resp, "Failed to create tree")
        return tree_resp.json()["sha"]

    async def _create_commit(
        self,
        client: httpx.AsyncClient,
        message: str,
        tree_sha: str,
        parent_sha: str,
    ) -> tuple[str, str]:
        resp = await client.post(
            self._repo_url("/git/commits"),
            json={"message": message, "tree": tree_sha, "parents": [parent_sha]},
        )
        self._raise_for(resp, "Failed to create commit")
        data = resp.json()
        return data["html_url"], data["sha"]

    async def _update_branch_ref(
        self, client: httpx.AsyncClient, branch: str, commit_sha: str
    ) -> None:
        resp = await client.patch(
            self._repo_url(f"/git/refs/heads/{branch}"),
            json={"sha": commit_sha},
        )
        self._raise_for(resp, f"Failed to update ref for branch '{branch}'")

    async def _create_pull_request(
        self,
        client: httpx.AsyncClient,
        head: str,
        title: str,
        body: str,
    ) -> str:
        """Open a PR from head into self._branch. Returns the PR HTML URL."""
        resp = await client.post(
            self._repo_url("/pulls"),
            json={"title": title, "body": body, "head": head, "base": self._branch},
        )
        # 422 means a PR already exists for this head — fetch and return it
        if resp.status_code == 422:
            existing = await client.get(
                self._repo_url(f"/pulls"),
                params={"head": f"{self._repo.split('/')[0]}:{head}", "state": "open"},
            )
            self._raise_for(existing, "Failed to fetch existing pull request")
            pulls = existing.json()
            if pulls:
                return pulls[0]["html_url"]
            raise GitHubError("PR already exists but could not be retrieved")

        self._raise_for(resp, "Failed to create pull request")
        return resp.json()["html_url"]
