import time
import requests
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class GitHubRecord:
    source_native_id: str
    payload: dict
    record_type: str


class GitHubAdapter:

    def __init__(self, repo, token):
        self.repo = repo.strip("/")
        self.token = token

        self.session = requests.Session()
        pool_adapter = requests.adapters.HTTPAdapter(
            pool_connections=15,
            pool_maxsize=15,
            max_retries=0
        )
        self.session.mount("https://", pool_adapter)
        self.session.mount("http://", pool_adapter)
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json"
        })

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

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=(10, 30)
                )

                # GitHub primary rate limit handling (403 with X-RateLimit-Remaining: 0)
                if response.status_code == 403:
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    if remaining == "0":
                        reset_time = int(
                            response.headers.get(
                                "X-RateLimit-Reset",
                                time.time() + 60
                            )
                        )
                        wait_time = max(reset_time - int(time.time()), 1)
                        time.sleep(min(wait_time + 1, 60))
                        continue

                # Secondary rate limit or abuse detection (429 or 403 with Retry-After)
                if response.status_code in (429, 403) and "Retry-After" in response.headers:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()

            except (requests.RequestException, requests.Timeout):
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)

    # =========================================================
    # PAGINATED GET
    # =========================================================

    def _get_all(self, endpoint, params=None):
        if params is None:
            params = {}

        params = params.copy()
        params["per_page"] = 100
        page = 1

        while True:
            params["page"] = page
            data = self._get(endpoint, params)

            if not data or not isinstance(data, list):
                break

            for item in data:
                yield item

            if len(data) < 100:
                break

            page += 1

    # =========================================================
    # REPOSITORY
    # =========================================================

    def fetch_repository(self):
        repository = self._get("")
        self.raw_data["repository"] = repository
        return repository

    # =========================================================
    # SINGLE COMMIT DETAIL HELPER
    # =========================================================

    def _fetch_commit_detail(self, commit):
        sha = commit["sha"]
        detail = self._get(f"commits/{sha}")
        return commit, detail

    # =========================================================
    # COMMITS
    # =========================================================

    def fetch_commits(self):
        commits = list(self._get_all("commits"))
        total = len(commits)

        print(f"Fetching commits: 0/{total}", flush=True)

        details = [None] * total
        completed = 0

        with ThreadPoolExecutor(max_workers=10) as executor:
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

                completed += 1
                if completed % 100 == 0 or completed == total:
                    print(f"Fetching commits: {completed}/{total}", flush=True)

        for item in details:
            if item is None:
                continue
            commit, detail = item
            sha = commit["sha"]

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
        print("Fetching issues...", flush=True)
        issues = self._get_all(
            "issues",
            {"state": "all"}
        )

        for issue in issues:
            # GitHub /issues endpoint also returns pull requests
            if "pull_request" in issue:
                continue

            issue_id = str(issue["id"])
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
        print("Fetching pull requests...", flush=True)
        pull_requests = self._get_all(
            "pulls",
            {"state": "all"}
        )

        for pr in pull_requests:
            pr_id = str(pr["id"])
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
        print("Fetching reviews...", flush=True)
        pull_requests = self.raw_data.get("pull_requests")
        if not pull_requests:
            pull_requests = list(self._get_all("pulls", {"state": "all"}))
            self.raw_data["pull_requests"] = pull_requests

        for pr in pull_requests:
            pr_number = pr["number"]
            reviews = self._get_all(f"pulls/{pr_number}/reviews")

            for review in reviews:
                review_id = str(review["id"])
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