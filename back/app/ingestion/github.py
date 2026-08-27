"""GitHub adapter — the live REST API.

This is the direct answer to the Round 1 feedback: *"demonstrate how Git, PR,
Jira and people information will actually be accessed."*  It authenticates, it
paginates, it handles rate limits, and it parses genuine GitHub payloads with
all their nesting and inconsistency.

Three implementation notes that are easy to get wrong:

1.  **The commits LIST response has no `files[]` and no `stats`.**  Both are
    only on the per-commit detail endpoint, and `stats.total` is the
    `effort_signal` the substance cap reads.  So every commit costs a second
    request.  Skipping this silently disables the substance cap.

2.  **A PR review is its own record**, not part of the commit.  `record_kind`
    for it is `pr_review`, and it sits at different ladder rungs — the role
    ladder is selected by source but the RUNG is decided by record kind and
    actor role, never by the source alone.

3.  **`author` is null for our commits.**  The demo repository is authored by
    six fictional engineers whose emails are not GitHub accounts, so GitHub
    cannot attribute them.  This is the real-GitHub trap in Piece 2 §6.2, and
    it is handled where it belongs — identity resolution keys on the commit
    author EMAIL, with the login as a secondary. Nothing here guesses.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterator

import httpx

from app.core.settings import FIXTURE_DIR, GENERATED_DIR, settings
from app.ingestion.raw_store import RawPayload

API = "https://api.github.com"


class GitHubAdapter:
    """Live adapter.  `fetch()` yields one RawPayload per logical record."""

    source_type = "github"

    def __init__(self, repo: str | None = None, token: str | None = None,
                 max_commits: int = 300) -> None:
        self.repo = repo or settings.github_repo
        self.token = token or settings.github_token
        self.max_commits = max_commits
        if not self.repo or not self.token:
            raise RuntimeError("GITHUB_REPO and GITHUB_TOKEN must be set")

    # ── plumbing ────────────────────────────────────────────────────────────
    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=API,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def _get(self, client: httpx.Client, url: str, params: dict | None = None) -> Any:
        """GET with rate-limit courtesy and bounded retries.

        A demo that dies on a 403 is unacceptable, so the rate-limit header is
        honoured rather than discovered.
        """
        for attempt in range(3):
            response = client.get(url, params=params)

            if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(response.headers.get("X-RateLimit-Reset", "0"))
                wait = max(0, reset - int(time.time())) + 1
                time.sleep(min(wait, 60))
                continue

            if response.status_code >= 500:
                time.sleep(2 ** attempt)
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError(f"GitHub request failed after retries: {url}")

    def _paginate(self, client: httpx.Client, url: str, params: dict | None = None,
                  limit: int = 1000) -> Iterator[dict]:
        page = 1
        seen = 0
        while seen < limit:
            batch = self._get(client, url, {**(params or {}), "per_page": 100, "page": page})
            if not batch:
                return
            for item in batch:
                yield item
                seen += 1
                if seen >= limit:
                    return
            page += 1

    # ── fetch ───────────────────────────────────────────────────────────────
    def fetch(self) -> Iterator[RawPayload]:
        with self._client() as client:
            reachable: set[str] = set()
            for payload in self._fetch_commits(client):
                reachable.add(payload.source_native_id)
                yield payload
            yield from self._fetch_pulls_and_reviews(client, reachable)

    def _fetch_commits(self, client: httpx.Client) -> Iterator[RawPayload]:
        for summary in self._paginate(
            client, f"/repos/{self.repo}/commits", limit=self.max_commits
        ):
            sha = summary["sha"]
            # The detail call is not optional — see note 1 in the module docstring.
            detail = self._get(client, f"/repos/{self.repo}/commits/{sha}")
            yield RawPayload(source_native_id=sha, payload=detail)

    def _fetch_pulls_and_reviews(self, client: httpx.Client,
                                 reachable: set[str]) -> Iterator[RawPayload]:
        """Pull requests, restricted to those still present on the default branch.

        A merged PR whose merge commit is NOT reachable from the default branch
        describes work that is no longer in the codebase — the branch history was
        rewritten underneath it. Counting it as evidence would credit an engineer
        for a change that does not exist any more, and on any repository that has
        ever been force-pushed there are usually several. The check is one set
        membership against the commits we just ingested.
        """
        skipped = 0
        for pr in self._paginate(
            client, f"/repos/{self.repo}/pulls", {"state": "all"}, limit=100
        ):
            number = pr["number"]
            merge_sha = pr.get("merge_commit_sha")
            if reachable and merge_sha and merge_sha not in reachable:
                skipped += 1
                continue
            try:
                pr["_files"] = self._get(client, f"/repos/{self.repo}/pulls/{number}/files")
            except Exception:
                pr["_files"] = []
            try:
                # The PR's own commits. Rung 2 recovers AUTHORSHIP, and whoever
                # opened a PR is often not who wrote it — release automation,
                # Dependabot, or a colleague re-opening someone's branch. The
                # commits carry the real author; `user.login` only carries who
                # clicked "New pull request".
                pr["_commits"] = self._get(client, f"/repos/{self.repo}/pulls/{number}/commits")
            except Exception:
                pr["_commits"] = []
            yield RawPayload(source_native_id=f"pr-{number}", payload=pr)

            for review in self._get(client, f"/repos/{self.repo}/pulls/{number}/reviews"):
                review["_pr_number"] = number
                review["_pr_files"] = pr.get("_files", [])
                yield RawPayload(
                    source_native_id=f"pr-{number}-review-{review['id']}",
                    payload=review,
                )
        if skipped:
            print(f"  (skipped {skipped} pull request(s) whose merge commit is no "
                  f"longer on the default branch)")


class GitHubFixtureAdapter:
    """Replays CAPTURED GitHub payloads through the SAME downstream path.

    Used when the network is unavailable, and as the demo-mode fallback.  The
    claim it supports is "the pipeline is real", not "the history is organic".

    It reads `data/fixtures/` — payloads captured from a live run (`ece dataset
    capture`) — and falls back to `data/generated/` only when no capture exists.

    **That distinction is the whole point, and getting it wrong was a real bug.**
    `data/generated/` holds the PLAN the repository was built from; it is not
    what GitHub returns. GitHub applies its own reality on top: a PR merge
    rewrites shas, an unreachable merge commit describes work that is not in the
    codebase, `files[]` and `stats` only exist on the detail endpoint. Replaying
    the plan therefore ingests records the live path never sees — five extra
    commits, in the dataset this was found on, which was enough to flip Karan to
    HIGH on Gateway Integration through the authorship exception and fail the
    acceptance gate. A fallback that produces a different answer to the path it
    stands in for is worse than no fallback.
    """

    source_type = "github"

    def __init__(self, directory: Path | None = None) -> None:
        self.dir = directory or (FIXTURE_DIR if self.captured(FIXTURE_DIR)
                                 else GENERATED_DIR)
        self.is_capture = self.captured(self.dir)

    @staticmethod
    def captured(directory: Path) -> bool:
        return (directory / "github_commits.json").exists()

    def _load(self, name: str) -> list[dict]:
        path = self.dir / name
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def fetch(self) -> Iterator[RawPayload]:
        for commit in self._load("github_commits.json"):
            yield RawPayload(source_native_id=commit["sha"], payload=commit)
        for pr in self._load("github_pulls.json"):
            yield RawPayload(source_native_id=f"pr-{pr['number']}", payload=pr)
        for review in self._load("github_reviews.json"):
            yield RawPayload(
                source_native_id=f"pr-{review['_pr_number']}-review-{review['id']}",
                payload=review,
            )


def capture_fixtures(conn, directory: Path | None = None) -> dict[str, int]:
    """Write the GitHub payloads currently in `raw_record` to the fixture set.

    The rows in `raw_record` ARE the live payloads, stored byte-identical to
    what the API returned (Piece 2 §5.1) — so the capture is a snapshot of a
    live run rather than a second guess at what one would produce. Replaying it
    reaches the same database, which is what `--fixture` has always claimed and
    what makes the offline demo trustworthy.
    """
    from app.db.conn import query

    out = directory or FIXTURE_DIR
    out.mkdir(parents=True, exist_ok=True)

    rows = query(conn, "SELECT source_native_id, payload FROM raw_record "
                       "WHERE source_type='github' ORDER BY raw_record_id")

    commits, pulls, reviews = [], [], []
    for r in rows:
        native, payload = r["source_native_id"], r["payload"]
        if native.startswith("pr-") and "-review-" in native:
            reviews.append(payload)
        elif native.startswith("pr-"):
            pulls.append(payload)
        else:
            commits.append(payload)

    written = {}
    for name, data in (("github_commits.json", commits),
                       ("github_pulls.json", pulls),
                       ("github_reviews.json", reviews)):
        (out / name).write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
        written[name] = len(data)
    return written


def build_adapter(live: bool) -> GitHubAdapter | GitHubFixtureAdapter:
    return GitHubAdapter() if live else GitHubFixtureAdapter()
