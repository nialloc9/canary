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
    ) -> tuple[str, int]:
        """
        Create a feature branch from self._branch, commit all files from local_dir
        (prefixed with infrastructure_base_path) plus any root_files (committed at
        the repo root with no prefix) in a single atomic commit, then open a PR.
        Returns (pr_html_url, file_count).
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
            await self._create_branch(client, feature_branch, base_commit_sha)
            tree_sha = await self._create_tree(client, files, base_tree_sha)
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
