from __future__ import annotations
import httpx
from typing import Optional
from app.models.github_models import GitHubRepo, SearchResult, ContributorInfo, GitHubIssue
from app.models.search_filters import SearchFilters
from app.models.settings import settings
from app.utils.logger import get_logger

log = get_logger("github_client")

GITHUB_API_BASE = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self._token = token or settings.github_token
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
            log.info("GitHubClient: authenticated with token")
        else:
            log.warning("GitHubClient: no token — rate limited to 10 req/min")
        self._client = httpx.Client(base_url=GITHUB_API_BASE, headers=headers, timeout=15.0)

    # ── Primary: repository search ────────────────────────────────────────────

    def search_repos(
        self,
        filters: SearchFilters,
        order: str = "desc",
        per_page: int = 50,
        page: int = 1,
    ) -> SearchResult:
        query = filters.build_query()
        sort = filters.sort if filters.sort != "best-match" else ""
        params: dict = {
            "q": query,
            "order": order,
            "per_page": per_page,
            "page": page,
        }
        if sort:
            params["sort"] = sort
        log.info(
            "GitHub search  query=%r  sort=%s  per_page=%d  page=%d",
            query, sort or "relevance", per_page, page,
        )
        response = self._client.get("/search/repositories", params=params)
        response.raise_for_status()
        result = SearchResult.model_validate(response.json())
        log.info(
            "GitHub search  total=%d  returned=%d  page=%d",
            result.total_count, len(result.items), page,
        )
        return result

    # ── Secondary enrichment ──────────────────────────────────────────────────

    def get_repo(self, owner: str, repo: str) -> GitHubRepo:
        log.debug("Fetching repo detail  repo=%s/%s", owner, repo)
        response = self._client.get(f"/repos/{owner}/{repo}")
        response.raise_for_status()
        return GitHubRepo.model_validate(response.json())

    def get_readme_b64(self, owner: str, repo: str) -> str:
        log.debug("Fetching README  repo=%s/%s", owner, repo)
        try:
            response = self._client.get(f"/repos/{owner}/{repo}/readme")
            if response.status_code == 404:
                log.debug("README not found  repo=%s/%s", owner, repo)
                return ""
            response.raise_for_status()
            content = response.json().get("content", "")
            log.debug("README fetched  repo=%s/%s  bytes=%d", owner, repo, len(content))
            return content
        except Exception as exc:
            log.warning("README fetch failed  repo=%s/%s  error=%s", owner, repo, exc)
            return ""

    def get_contributors(
        self, owner: str, repo: str, per_page: int = 30
    ) -> list[ContributorInfo]:
        log.debug("Fetching contributors  repo=%s/%s", owner, repo)
        try:
            response = self._client.get(
                f"/repos/{owner}/{repo}/contributors",
                params={"per_page": per_page, "anon": "false"},
            )
            if response.status_code == 204:
                return []
            response.raise_for_status()
            contributors = [ContributorInfo.model_validate(c) for c in response.json()]
            log.debug(
                "Contributors fetched  repo=%s/%s  count=%d", owner, repo, len(contributors)
            )
            return contributors
        except Exception as exc:
            log.warning("Contributors fetch failed  repo=%s/%s  error=%s", owner, repo, exc)
            return []

    def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
    ) -> list[GitHubIssue]:
        log.debug("Fetching issues  repo=%s/%s  state=%s", owner, repo, state)
        try:
            response = self._client.get(
                f"/repos/{owner}/{repo}/issues",
                params={"state": state, "per_page": per_page, "pulls": "false"},
            )
            response.raise_for_status()
            raw_issues = [i for i in response.json() if "pull_request" not in i]
            issues = [
                GitHubIssue(
                    **{k: v for k, v in i.items() if k != "labels"},
                    labels=[lbl["name"] for lbl in i.get("labels", [])],
                )
                for i in raw_issues
            ]
            log.debug(
                "Issues fetched  repo=%s/%s  count=%d", owner, repo, len(issues)
            )
            return issues
        except Exception as exc:
            log.warning("Issues fetch failed  repo=%s/%s  error=%s", owner, repo, exc)
            return []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
