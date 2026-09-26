"""GitHub repository discovery and commit-keyed dataset caching."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}


class RepositoryError(RuntimeError):
    """Safe, user-facing GitHub integration error."""


class GitHubRepository:
    def __init__(
        self,
        repository_url: str,
        branch: str = "main",
        token: str | None = None,
        data_path: str | None = None,
        cache_dir: str | Path = ".cache/github",
    ) -> None:
        parsed = urlparse(repository_url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if parsed.netloc.lower() not in {"github.com", "www.github.com"} or len(parts) < 2:
            raise RepositoryError("GITHUB_REPO_URL must be a GitHub URL such as https://github.com/org/repo.")
        self.owner, self.name = parts[:2]
        self.name = self.name.removesuffix(".git")
        self.branch = branch
        self.data_path = (data_path or "").strip("/")
        self.cache_dir = Path(cache_dir)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    @property
    def api_root(self) -> str:
        return f"https://api.github.com/repos/{quote(self.owner)}/{quote(self.name)}"

    def _get_json(self, url: str) -> dict:
        try:
            response = self.session.get(url, timeout=30)
        except requests.RequestException as exc:
            raise RepositoryError("Could not reach GitHub. Check the network connection and repository settings.") from exc
        if response.status_code in {401, 403}:
            raise RepositoryError("GitHub rejected access. Check the token, repository permissions, and API rate limit.")
        if response.status_code == 404:
            raise RepositoryError("GitHub repository or branch was not found, or the token cannot access it.")
        if response.status_code >= 400:
            raise RepositoryError(f"GitHub returned HTTP {response.status_code} while reading repository metadata.")
        try:
            return response.json()
        except ValueError as exc:
            raise RepositoryError("GitHub returned an invalid metadata response.") from exc

    def discover(self) -> tuple[str, list[dict[str, str]]]:
        branch_info = self._get_json(f"{self.api_root}/commits/{quote(self.branch, safe='')}")
        commit_sha = branch_info.get("sha")
        if not commit_sha:
            raise RepositoryError("GitHub did not return a commit for the configured branch.")
        tree = self._get_json(f"{self.api_root}/git/trees/{commit_sha}?recursive=1")
        if tree.get("truncated"):
            raise RepositoryError("The GitHub repository tree is too large for complete discovery.")
        files = [
            {"path": item["path"], "sha": item["sha"]}
            for item in tree.get("tree", [])
            if item.get("type") == "blob" and Path(item.get("path", "")).suffix.lower() in SUPPORTED_EXTENSIONS
            and (not self.data_path or item["path"] == self.data_path or item["path"].startswith(f"{self.data_path}/"))
        ]
        return commit_sha, files

    def read_file(self, commit_sha: str, item: dict[str, str]) -> bytes:
        cache_key = hashlib.sha256(f"{self.owner}/{self.name}/{item['path']}/{item['sha']}".encode()).hexdigest()
        cache_path = self.cache_dir / commit_sha / f"{cache_key}{Path(item['path']).suffix.lower()}"
        if cache_path.is_file():
            return cache_path.read_bytes()

        blob = self._get_json(f"{self.api_root}/git/blobs/{item['sha']}")
        if blob.get("encoding") != "base64" or not blob.get("content"):
            raise RepositoryError(f"GitHub could not provide dataset `{item['path']}` in a supported encoding.")
        try:
            content = base64.b64decode(blob["content"])
        except (ValueError, TypeError) as exc:
            raise RepositoryError(f"GitHub returned invalid content for dataset `{item['path']}`.") from exc
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        metadata_path = self.cache_dir / "latest.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps({"commit": commit_sha}), encoding="utf-8")
        return content


def repository_from_environment() -> GitHubRepository | None:
    repository_url = os.getenv("GITHUB_REPO_URL", "").strip()
    if not repository_url:
        return None
    return GitHubRepository(
        repository_url=repository_url,
        branch=os.getenv("GITHUB_BRANCH", "main").strip() or "main",
        token=os.getenv("GITHUB_TOKEN") or None,
        data_path=os.getenv("GITHUB_DATA_PATH"),
        cache_dir=os.getenv("DATA_CACHE_DIR", ".cache/github"),
    )


def repository_from_blob_url(url: str, token: str | None = None, cache_dir: str | Path = ".cache/github") -> GitHubRepository:
    parsed = urlparse(url)
    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if parsed.netloc.lower() not in {"github.com", "www.github.com"} or len(parts) < 5 or parts[2] != "blob":
        raise RepositoryError("The purchase-price URL must be a GitHub blob URL.")
    owner, name, _, commit, *file_parts = parts
    return GitHubRepository(
        f"https://github.com/{owner}/{name}",
        branch=commit,
        token=token,
        data_path="/".join(file_parts),
        cache_dir=cache_dir,
    )


def purchase_repository_from_environment() -> GitHubRepository | None:
    url = os.getenv("GITHUB_PURCHASE_PRICE_URL", "").strip()
    if not url:
        return None
    return repository_from_blob_url(
        url,
        token=os.getenv("GITHUB_TOKEN") or None,
        cache_dir=os.getenv("DATA_CACHE_DIR", ".cache/github"),
    )