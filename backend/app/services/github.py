"""
GitHub integration: create repos, manage branches, commit status.
"""
import httpx
from typing import Optional
from app.core.config import get_settings

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

    async def close(self):
        await self.client.aclose()


github_service = GitHubService()
