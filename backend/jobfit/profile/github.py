"""Fetch README files from GitHub via the REST API (no `gh` CLI or git clone needed)."""

from __future__ import annotations

import httpx

API = "https://api.github.com"


def _client(token: str = "") -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API, headers=headers, timeout=20.0, follow_redirects=True)


def list_repos(user: str, token: str = "", limit: int = 30) -> list[str]:
    """The user's own (non-fork) public repos, most recently pushed first."""
    with _client(token) as c:
        r = c.get(f"/users/{user}/repos", params={"per_page": 100, "sort": "pushed", "type": "owner"})
        r.raise_for_status()
        return [repo["full_name"] for repo in r.json() if not repo.get("fork")][:limit]


def fetch_readme(full_name: str, token: str = "") -> str | None:
    with _client(token) as c:
        r = c.get(f"/repos/{full_name}/readme", headers={"Accept": "application/vnd.github.raw+json"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.text


def fetch_readmes(target: str, token: str = "", limit: int = 30) -> list[tuple[str, str]]:
    """`target` is a username ("octocat") or comma-separated repos ("octocat/a, octocat/b")."""
    names = [t.strip() for t in target.split(",") if t.strip()]
    repos: list[str] = []
    for name in names:
        repos.extend([name] if "/" in name else list_repos(name, token, limit))
    out = []
    for full_name in repos[:limit]:
        readme = fetch_readme(full_name, token)
        if readme:
            out.append((full_name, readme))
    return out
