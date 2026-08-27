"""Open real pull requests against the constructed repository.

Piece 5 §3.4.  PR `created_at` and `merged_at` are server-assigned and cannot be
backdated, so every real PR lands in the fresh window.  That is accepted rather
than fought, and it is realistic: recent work has commits *and* PRs, while
three-year-old work is commits only — which is exactly how an old codebase
looks.  The aged cases are carried by commits and the synthetic sources.

One GitHub constraint shapes the review evidence: **you cannot APPROVE your own
pull request.**  A `COMMENT` review is allowed, so review evidence here lands at
GitHub rung 3 (reviewer who left substantive comments).  Rung 4 (approval with
no comments) has no reachable record on a single-account repository; it stays
implemented and unit-tested, with no live instance.  Recorded rather than
quietly dropped.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

from app.core.settings import settings
from app.dataset.recipes import build_plan
from app.dataset.spec import CAPABILITY_BY_KEY, PEOPLE

API = "https://api.github.com"
_PEOPLE = {p.employee_id: p for p in PEOPLE}


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=API,
        headers={
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    )


def _git(cmd: list[str], cwd: Path, env: dict | None = None) -> str:
    import os

    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})},
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git failed: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout.strip()


def create_pull_requests(workdir: str | Path) -> list[dict]:
    """Branch, push, open, review and merge one PR per PRSpec."""
    plan = build_plan()
    tmp = Path(workdir)
    repo = settings.github_repo
    created: list[dict] = []

    with _client() as client:
        existing = {}
        try:
            for pr in client.get(f"/repos/{repo}/pulls",
                                 params={"state": "all", "per_page": 100}).json():
                existing.setdefault(pr["title"], pr)
        except Exception:
            existing = {}

        for spec in plan.prs:
            author = _PEOPLE[spec.author]
            branch = f"feature/pr-{spec.number}"

            # Rebuilding the repository must not open a duplicate pull request
            # on every run — that inflates authorship for whoever the PRs belong
            # to, which is precisely the kind of quiet drift the validator exists
            # to catch.
            if spec.title in existing:
                created.append({"number": existing[spec.title]["number"],
                                "title": spec.title, "author": author.employee_id,
                                "merged": True, "reused": True})
                continue

            _git(["git", "checkout", "-q", "main"], tmp)
            _git(["git", "checkout", "-q", "-b", branch], tmp)

            for key in spec.capability_keys:
                prefix = CAPABILITY_BY_KEY[key].path_prefix
                target = tmp / prefix / "service.py"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    f'"""{spec.title}"""\n\n'
                    + "\n".join(f"# pr-{spec.number} line {i}" for i in range(40))
                    + "\n",
                    encoding="utf-8",
                )

            body = spec.title + (f"\n\nCloses {spec.jira_ref}" if spec.jira_ref else "")
            _git(["git", "add", "-A"], tmp)
            _git(["git", "commit", "-q", "-m", body], tmp, env={
                "GIT_AUTHOR_NAME": author.display_name,
                "GIT_AUTHOR_EMAIL": f"{author.employee_id}@sih26.invalid",
                "GIT_COMMITTER_NAME": author.display_name,
                "GIT_COMMITTER_EMAIL": f"{author.employee_id}@sih26.invalid",
            })
            _git(["git", "push", "-q", "--force", "origin", branch], tmp)

            resp = client.post(f"/repos/{repo}/pulls", json={
                "title": spec.title,
                "head": branch,
                "base": "main",
                "body": body,
            })
            if resp.status_code >= 300:
                created.append({"spec": spec.number, "error": resp.json().get("message")})
                continue
            pr = resp.json()
            number = pr["number"]

            # COMMENT review — APPROVE is rejected on your own PR (see docstring).
            for reviewer, substantive in spec.reviewers:
                if not substantive:
                    continue
                client.post(f"/repos/{repo}/pulls/{number}/reviews", json={
                    "event": "COMMENT",
                    "body": (
                        f"[{_PEOPLE[reviewer].display_name}] Checked the retry path "
                        f"and the boundary cases; this looks right."
                    ),
                })

            merge = client.put(f"/repos/{repo}/pulls/{number}/merge",
                               json={"merge_method": "merge"})
            created.append({
                "number": number,
                "title": spec.title,
                "author": author.employee_id,
                "merged": merge.status_code < 300,
                "reviews": sum(1 for _, s in spec.reviewers if s),
            })

    _git(["git", "checkout", "-q", "main"], tmp)
    return created
