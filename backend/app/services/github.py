"""
GitHub integration: create repos, manage branches, commit status.
"""
import httpx
import logging
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class GitHubService:
    BASE = "https://api.github.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"token {settings.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Retrix-Orchestrator",
            },
        )

    async def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = True,
        org: Optional[str] = None,
    ) -> dict:
        """Create a new GitHub repository."""
        url = f"{self.BASE}/orgs/{org}/repos" if org else f"{self.BASE}/user/repos"
        resp = await self.client.post(url, json={
            "name": name,
            "description": description,
            "private": private,
            "auto_init": True,
            "gitignore_template": "Node",  # basic .gitignore
        })
        resp.raise_for_status()
        data = resp.json()
        return {
            "full_name": data["full_name"],
            "clone_url": data["clone_url"],
            "ssh_url": data["ssh_url"],
            "html_url": data["html_url"],
        }

    async def repo_exists(self, owner: str, repo: str) -> bool:
        resp = await self.client.get(f"{self.BASE}/repos/{owner}/{repo}")
        return resp.status_code == 200

    async def create_branch(self, owner: str, repo: str, branch: str, from_branch: str = "main") -> dict:
        """Create a new branch from existing branch."""
        # Get SHA of source branch
        resp = await self.client.get(f"{self.BASE}/repos/{owner}/{repo}/git/ref/heads/{from_branch}")
        resp.raise_for_status()
        sha = resp.json()["object"]["sha"]

        # Create new branch
        resp = await self.client.post(
            f"{self.BASE}/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        resp.raise_for_status()
        return resp.json()

    async def list_branches(self, owner: str, repo: str) -> list:
        resp = await self.client.get(f"{self.BASE}/repos/{owner}/{repo}/branches")
        resp.raise_for_status()
        return [b["name"] for b in resp.json()]

    async def get_repo_info(self, owner: str, repo: str) -> dict:
        resp = await self.client.get(f"{self.BASE}/repos/{owner}/{repo}")
        resp.raise_for_status()
        data = resp.json()
        return {
            "full_name": data["full_name"],
            "clone_url": data["clone_url"],
            "ssh_url": data["ssh_url"],
            "html_url": data["html_url"],
            "default_branch": data["default_branch"],
        }

    async def setup_develop_branch(self, workspace_path: str) -> bool:
        """Create and checkout develop branch (idempotent — skips if already on develop).
        Returns True on success."""
        import subprocess
        import asyncio

        def _run(cmd: list, cwd: str):
            return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

        loop = asyncio.get_running_loop()

        await loop.run_in_executor(None, _run,
            ["git", "config", "user.email", "pm@retrix.ai"], workspace_path)
        await loop.run_in_executor(None, _run,
            ["git", "config", "user.name", "Retrix PM"], workspace_path)

        # Check current branch
        cur = await loop.run_in_executor(None, _run,
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], workspace_path)
        if cur.stdout.strip() == "develop":
            return True

        # Try to checkout existing remote develop, otherwise create fresh
        checkout = await loop.run_in_executor(None, _run,
            ["git", "checkout", "-b", "develop", "--track", "origin/develop"], workspace_path)
        if checkout.returncode != 0:
            checkout = await loop.run_in_executor(None, _run,
                ["git", "checkout", "-b", "develop"], workspace_path)
        if checkout.returncode != 0:
            logger.warning(f"[git] failed to create develop branch: {checkout.stderr}")
            return False

        push = await loop.run_in_executor(None, _run,
            ["git", "push", "-u", "origin", "develop"], workspace_path)
        if push.returncode != 0:
            logger.warning(f"[git] failed to push develop branch: {push.stderr}")

        return True

    async def git_commit_and_push(self, workspace_path: str, message: str) -> bool:
        """Stage all changes in workspace, commit, and push to develop branch.
        Returns True if a commit was made, False if nothing to commit."""
        import subprocess
        import asyncio

        def _run(cmd: list, cwd: str):
            return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

        loop = asyncio.get_running_loop()

        await loop.run_in_executor(None, _run,
            ["git", "config", "user.email", "pm@retrix.ai"], workspace_path)
        await loop.run_in_executor(None, _run,
            ["git", "config", "user.name", "Retrix PM"], workspace_path)

        # Ensure we're on develop
        cur = await loop.run_in_executor(None, _run,
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], workspace_path)
        if cur.stdout.strip() != "develop":
            await loop.run_in_executor(None, _run,
                ["git", "checkout", "develop"], workspace_path)

        await loop.run_in_executor(None, _run, ["git", "add", "-A"], workspace_path)

        status = await loop.run_in_executor(None, _run,
            ["git", "status", "--porcelain"], workspace_path)
        if not status.stdout.strip():
            return False  # nothing to commit

        result = await loop.run_in_executor(None, _run,
            ["git", "commit", "-m", message], workspace_path)
        if result.returncode != 0:
            logger.warning(f"[git] commit failed: {result.stderr}")
            return False

        push = await loop.run_in_executor(None, _run,
            ["git", "push", "origin", "develop"], workspace_path)
        if push.returncode != 0:
            logger.warning(f"[git] push failed: {push.stderr}")

        return True

    async def merge_develop_to_main(self, workspace_path: str, project_name: str) -> bool:
        """Merge develop into main and push. Returns True on success."""
        import subprocess
        import asyncio

        def _run(cmd: list, cwd: str):
            return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

        loop = asyncio.get_running_loop()

        await loop.run_in_executor(None, _run,
            ["git", "config", "user.email", "pm@retrix.ai"], workspace_path)
        await loop.run_in_executor(None, _run,
            ["git", "config", "user.name", "Retrix PM"], workspace_path)

        # Switch to main (try both 'main' and 'master')
        checkout = await loop.run_in_executor(None, _run,
            ["git", "checkout", "main"], workspace_path)
        if checkout.returncode != 0:
            checkout = await loop.run_in_executor(None, _run,
                ["git", "checkout", "master"], workspace_path)
        if checkout.returncode != 0:
            logger.warning(f"[git] could not checkout main/master: {checkout.stderr}")
            return False

        # Pull latest main
        await loop.run_in_executor(None, _run,
            ["git", "pull", "origin", "HEAD"], workspace_path)

        # Merge develop with a merge commit (no fast-forward keeps history clean)
        merge = await loop.run_in_executor(None, _run,
            ["git", "merge", "--no-ff", "develop",
             "-m", f"chore: merge develop into main — {project_name} complete"],
            workspace_path)
        if merge.returncode != 0:
            logger.warning(f"[git] merge failed: {merge.stderr}")
            return False

        push = await loop.run_in_executor(None, _run,
            ["git", "push", "origin", "HEAD"], workspace_path)
        if push.returncode != 0:
            logger.warning(f"[git] push main failed: {push.stderr}")
            return False

        return True

    async def close(self):
        await self.client.aclose()


github_service = GitHubService()
