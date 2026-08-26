from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterator
from dotenv import load_dotenv

import httpx

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

API = "https://api.github.com"


class RawPayload:
    """Container for one raw GitHub record."""

    def __init__(self, source_native_id: str, payload: dict):
        self.source_native_id = source_native_id
        self.payload = payload


class GitHubAdapter:
    """Fetch real GitHub data and return raw payloads."""

    source_type = "github"

    def __init__(
        self,
        repo: str,
        token: str | None = None,
        max_commits: int = 300,
    ):
        self.repo = repo
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.max_commits = max_commits

        if not self.repo:
            raise RuntimeError("GitHub repository is required")

    def _client(self) -> httpx.Client:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return httpx.Client(
            base_url=API,
            headers=headers,
            timeout=30.0,
        )


    def _get(
        self,
        client: httpx.Client,
        url: str,
        params: dict | None = None,
    ) -> Any:

        for attempt in range(3):

            response = client.get(
                url,
                params=params,
            )

            # Fallback to unauthenticated if token is invalid/expired (401)
            if response.status_code == 401 and "Authorization" in client.headers:
                del client.headers["Authorization"]
                self.token = None
                continue

            # GitHub rate limit
            if (
                response.status_code == 403
                and response.headers.get("X-RateLimit-Remaining") == "0"
            ):
                reset = int(
                    response.headers.get(
                        "X-RateLimit-Reset",
                        "0",
                    )
                )

                wait = max(
                    0,
                    reset - int(time.time()),
                ) + 1

                time.sleep(min(wait, 60))
                continue

            # Temporary GitHub server error
            if response.status_code >= 500:
                time.sleep(2 ** attempt)
                continue

            response.raise_for_status()

            return response.json()

        raise RuntimeError(
            f"GitHub request failed after retries: {url}"
        )

    def _paginate(
        self,
        client: httpx.Client,
        url: str,
        params: dict | None = None,
        limit: int = 1000,
    ) -> Iterator[dict]:

        page = 1
        seen = 0

        while seen < limit:

            batch = self._get(
                client,
                url,
                {
                    **(params or {}),
                    "per_page": 100,
                    "page": page,
                },
            )

            if not batch:
                return

            for item in batch:

                yield item

                seen += 1

                if seen >= limit:
                    return

            page += 1

    def fetch(self) -> Iterator[RawPayload]:

        with self._client() as client:

            reachable_commits = set()

            # -------------------------
            # COMMITS
            # -------------------------

            for payload in self._fetch_commits(client):

                reachable_commits.add(
                    payload.source_native_id
                )

                yield payload

            # -------------------------
            # PULL REQUESTS + REVIEWS
            # -------------------------

            yield from self._fetch_pulls_and_reviews(
                client,
                reachable_commits,
            )

    def _fetch_commits(
        self,
        client: httpx.Client,
    ) -> Iterator[RawPayload]:

        for summary in self._paginate(
            client,
            f"/repos/{self.repo}/commits",
            limit=self.max_commits,
        ):

            sha = summary["sha"]

            # IMPORTANT:
            # The list endpoint does not contain
            # complete commit information.
            detail = self._get(
                client,
                f"/repos/{self.repo}/commits/{sha}",
            )

            yield RawPayload(
                source_native_id=sha,
                payload=detail,
            )

    def _fetch_pulls_and_reviews(
        self,
        client: httpx.Client,
        reachable: set[str],
    ):

        for pr in self._paginate(
            client,
            f"/repos/{self.repo}/pulls",
            {
                "state": "all",
            },
            limit=100,
        ):

            number = pr["number"]

            merge_sha = pr.get(
                "merge_commit_sha"
            )

            # Ignore merged PRs whose merge commit
            # is no longer reachable.
            if (
                reachable
                and merge_sha
                and merge_sha not in reachable
            ):
                continue

            # PR files
            try:

                pr["_files"] = self._get(
                    client,
                    f"/repos/{self.repo}/pulls/{number}/files",
                )

            except Exception:

                pr["_files"] = []

            # PR commits
            try:

                pr["_commits"] = self._get(
                    client,
                    f"/repos/{self.repo}/pulls/{number}/commits",
                )

            except Exception:

                pr["_commits"] = []

            yield RawPayload(
                source_native_id=f"pr-{number}",
                payload=pr,
            )

            # PR reviews
            try:

                reviews = self._get(
                    client,
                    f"/repos/{self.repo}/pulls/{number}/reviews",
                )

            except Exception:

                reviews = []

            for review in reviews:

                review["_pr_number"] = number
                review["_pr_files"] = pr.get(
                    "_files",
                    [],
                )

                yield RawPayload(
                    source_native_id=(
                        f"pr-{number}"
                        f"-review-{review['id']}"
                    ),
                    payload=review,
                )


def build_adapter(
    repo: str,
    token: str | None = None,
) -> GitHubAdapter:

    return GitHubAdapter(
        repo=repo,
        token=token,
    )