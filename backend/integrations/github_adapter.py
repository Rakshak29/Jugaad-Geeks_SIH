import os
import time
import requests
from pathlib import Path
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


@dataclass
class GitHubRecord:
    source_native_id: str
    payload: dict
    record_type: str


class GitHubAdapter:

    def __init__(self, repo=None, token=None, max_commits=None):
        self.repo = (repo or os.getenv("GITHUB_REPO", "")).strip("/")
        token_candidate = token if (token and str(token).strip()) else os.getenv("GITHUB_TOKEN", "")
        self.token = str(token_candidate).strip()
        self.max_commits = max_commits

        self.session = requests.Session()
        pool_adapter = requests.adapters.HTTPAdapter(
            pool_connections=30,
            pool_maxsize=30,
            max_retries=0
        )
        self.session.mount("https://", pool_adapter)
        self.session.mount("http://", pool_adapter)
        
        headers = {
            "Accept": "application/vnd.github+json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.update(headers)

        self.rate_limited = False
        self.last_error = None
        self.raw_data = {
            "repository": {},
            "commits": [],
            "commit_details": [],
            "issues": [],
            "pull_requests": [],
            "reviews": []
        }

    # =========================================================
    # GET REQUEST WITH TIMEOUT, RETRY, AND RATE LIMIT HANDLING
    # =========================================================

    def _get(self, endpoint="", params=None):
        endpoint = (endpoint or "").strip("/")
        if endpoint:
            url = f"https://api.github.com/repos/{self.repo}/{endpoint}"
        else:
            url = f"https://api.github.com/repos/{self.repo}"

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=(5, 15)
                )

                # Fallback to unauthenticated if token is invalid/expired (401)
                if response.status_code == 401 and "Authorization" in self.session.headers:
                    del self.session.headers["Authorization"]
                    self.token = None
                    continue

                # GitHub primary rate limit handling (403 with X-RateLimit-Remaining: 0)
                if response.status_code == 403:
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    if remaining == "0":
                        self.rate_limited = True
                        self.last_error = "GitHub API rate limit reached."
                        if not self.token or attempt >= 1:
                            return None
                        reset_time = int(
                            response.headers.get(
                                "X-RateLimit-Reset",
                                time.time() + 5
                            )
                        )
                        wait_time = min(max(reset_time - int(time.time()), 1), 5)
                        time.sleep(wait_time)
                        continue

                # Secondary rate limit or abuse detection (429 or 403 with Retry-After)
                if response.status_code in (429, 403) and "Retry-After" in response.headers:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    time.sleep(min(retry_after, 5))
                    continue

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return response.json()

            except (requests.RequestException, requests.Timeout):
                if attempt == max_retries - 1:
                    return None
                time.sleep(1)
        return None

    # =========================================================
    # PAGINATED GET (UNLIMITED BY DEFAULT)
    # =========================================================

    def _get_all(self, endpoint, params=None, max_items=None):
        if params is None:
            params = {}

        params = params.copy()
        params["per_page"] = 100
        page = 1
        yielded = 0

        while True:
            if max_items is not None and yielded >= max_items:
                break

            params["page"] = page
            data = self._get(endpoint, params)

            if not data or not isinstance(data, list):
                break

            for item in data:
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    break

            if len(data) < params["per_page"]:
                break

            page += 1

    # =========================================================
    # REPOSITORY
    # =========================================================

    def fetch_repository(self):
        repository = self._get("") or {}
        self.raw_data["repository"] = repository
        return repository

    # =========================================================
    # SINGLE COMMIT DETAIL HELPER
    # =========================================================

    def _fetch_commit_detail(self, commit):
        sha = commit.get("sha")
        if not sha:
            return commit, commit
        try:
            detail = self._get(f"commits/{sha}")
            return commit, (detail or commit)
        except Exception:
            return commit, commit

    # =========================================================
    # COMMITS
    # =========================================================

    def fetch_commits(self):
        commits = list(self._get_all("commits", max_items=self.max_commits))
        total = len(commits)

        details = [None] * total

        # Concurrently fetch commit details across 20 workers
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_idx = {
                executor.submit(self._fetch_commit_detail, commit): idx
                for idx, commit in enumerate(commits)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    commit, detail = future.result()
                    details[idx] = (commit, detail)
                except Exception:
                    details[idx] = (commits[idx], commits[idx])

        for item in details:
            if item is None:
                continue
            commit, detail = item
            sha = commit.get("sha", "")
            if not sha:
                continue

            self.raw_data["commits"].append(commit)
            self.raw_data["commit_details"].append(detail)

            yield GitHubRecord(
                source_native_id=sha,
                payload=detail,
                record_type="commit"
            )

    # =========================================================
    # ISSUES
    # =========================================================

    def fetch_issues(self):
        issues = self._get_all("issues", {"state": "all"}, max_items=None)

        for issue in issues:
            if not isinstance(issue, dict) or "pull_request" in issue:
                continue

            issue_id = str(issue.get("id", ""))
            if not issue_id:
                continue

            self.raw_data["issues"].append(issue)

            yield GitHubRecord(
                source_native_id=issue_id,
                payload=issue,
                record_type="issue"
            )

    # =========================================================
    # PULL REQUESTS
    # =========================================================

    def fetch_pull_requests(self):
        pull_requests = list(self._get_all("pulls", {"state": "all"}, max_items=None))

        for pr in pull_requests:
            if not isinstance(pr, dict):
                continue
            pr_id = str(pr.get("id", ""))
            if not pr_id:
                continue

            self.raw_data["pull_requests"].append(pr)

            yield GitHubRecord(
                source_native_id=pr_id,
                payload=pr,
                record_type="pull_request"
            )

    # =========================================================
    # REVIEWS
    # =========================================================

    def fetch_reviews(self):
        pull_requests = self.raw_data.get("pull_requests", [])
        if not pull_requests:
            pull_requests = list(self._get_all("pulls", {"state": "all"}, max_items=50))
            self.raw_data["pull_requests"] = pull_requests

        for pr in pull_requests:
            pr_number = pr.get("number")
            if not pr_number:
                continue

            reviews = self._get(f"pulls/{pr_number}/reviews")
            if not reviews or not isinstance(reviews, list):
                continue

            for review in reviews:
                if not isinstance(review, dict):
                    continue
                review_id = str(review.get("id", ""))
                if not review_id:
                    continue

                payload = {
                    **review,
                    "pull_request_number": pr_number
                }
                self.raw_data["reviews"].append(payload)

                yield GitHubRecord(
                    source_native_id=review_id,
                    payload=payload,
                    record_type="review"
                )

    # =========================================================
    # MAIN FETCH
    # =========================================================

    def fetch(self):
        self.fetch_repository()
        yield from self.fetch_commits()
        yield from self.fetch_issues()
        yield from self.fetch_pull_requests()
        yield from self.fetch_reviews()