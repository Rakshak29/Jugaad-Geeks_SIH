"""Construct the demo repository and push it to GitHub.

Piece 5 §3.  What is REAL here is the pipeline: the adapter authenticates
against the live GitHub REST API and parses genuine GitHub payloads with all
their nesting.  What is CONSTRUCTED is the scenario — who did what, when.  The
wording that keeps this honest is fixed (Piece 5 §3.3):

    "We constructed a repository and ingested it through the real GitHub API."

Never "we analysed a real production repository."

Two mechanics matter:

1.  `GIT_AUTHOR_DATE` is writable, which is what carries the three-year
    timeline.  PR `created_at`/`merged_at` are server-assigned and are NOT
    writable, so any work unit containing a real PR is necessarily fresh.  That
    is realistic rather than a compromise: recent work has commits *and* PRs;
    three-year-old work is commits only.

2.  The commit authors are our six fictional engineers, on the `.invalid` TLD
    (RFC 2606 — reserved, and registrable by nobody), so the API returns
    `author: null` for every one of them.

    The first attempt used `@example.com` and GitHub attributed the commits to
    two REAL strangers who happen to have registered those addresses. On a
    public repository that puts fabricated commits in real people's names. The
    `.invalid` domain makes that impossible, and it makes the trap cleaner to
    demonstrate: attribution is null for 100% of commits, so identity has to be
    resolved deliberately rather than trusted.  This is exactly the real-GitHub trap in Piece 2 §6.2.
    Identity therefore resolves on `commit.author.email`, and `source_identity`
    carries a row for the email as well as the login.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.settings import settings
from app.dataset.recipes import Plan, build_plan
from app.dataset.spec import PEOPLE, SERVICE_ACCOUNTS

_ACTORS = {p.employee_id: p for p in (*PEOPLE, *SERVICE_ACCOUNTS)}
_BY_LOGIN = {p.github_login: p for p in (*PEOPLE, *SERVICE_ACCOUNTS)}


def _actor(ref: str):
    return _ACTORS.get(ref) or _BY_LOGIN[ref]


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> str:
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd, cwd=cwd, env=full_env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git failed: {' '.join(cmd)}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def build_repository(plan: Plan | None = None, workdir: Path | None = None,
                     push: bool = True) -> dict[str, int]:
    """Write every commit in the plan into a fresh clone and push to `main`."""
    plan = plan or build_plan()
    if not settings.github_repo or not settings.github_token:
        raise RuntimeError("GITHUB_REPO and GITHUB_TOKEN must be set in .env")

    tmp = Path(workdir or tempfile.mkdtemp(prefix="ece-repo-"))
    if tmp.exists() and workdir:
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    remote = (
        f"https://x-access-token:{settings.github_token}@github.com/"
        f"{settings.github_repo}.git"
    )

    _run(["git", "init", "-q", "-b", "main"], tmp)
    _run(["git", "config", "user.email", "pipeline@sih26.invalid"], tmp)
    _run(["git", "config", "user.name", "ECE Pipeline"], tmp)

    (tmp / "README.md").write_text(
        "# Payment Service\n\n"
        "A repository **constructed for the Engineering Continuity Engine "
        "prototype** (SIH26_174).\n\n"
        "The commit history is designed: author dates are set deliberately so "
        "evidence spans three years. The ingestion pipeline that reads it is "
        "real — it authenticates against the live GitHub REST API and parses "
        "genuine GitHub payloads.\n\n"
        "This is not a production repository and is never described as one.\n",
        encoding="utf-8",
    )
    _run(["git", "add", "-A"], tmp)
    _run(["git", "commit", "-q", "-m", "Initial commit"], tmp,
         env={"GIT_AUTHOR_DATE": "2023-07-01T09:00:00", "GIT_COMMITTER_DATE": "2023-07-01T09:00:00"})

    # Chronological order, so the history reads like a history.
    ordered = sorted(plan.commits, key=lambda c: (c.occurred_at, c.key))

    written = 0
    for spec in ordered:
        author = _actor(spec.author)
        name = author.display_name
        email = f"{author.employee_id}@sih26.invalid"

        if spec.is_merge:
            # A merge with no own changes. Recorded so Stage A has one to drop.
            (tmp / ".merge-marker").write_text(spec.key, encoding="utf-8")
            _run(["git", "add", "-A"], tmp)
        else:
            per_file = max(1, spec.lines_changed // max(1, len(spec.files) or 1))
            for f in spec.files:
                target = tmp / f
                target.parent.mkdir(parents=True, exist_ok=True)
                body = "\n".join(
                    f"# {spec.key} line {i}" for i in range(per_file)
                )
                target.write_text(
                    f'"""{spec.message.splitlines()[0]}"""\n\n{body}\n',
                    encoding="utf-8",
                )
            _run(["git", "add", "-A"], tmp)

        stamp = spec.occurred_at.strftime("%Y-%m-%dT%H:%M:%S")
        env = {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": stamp,
        }
        message = spec.message
        if spec.jira_ref and spec.jira_ref not in message:
            message += f". Closes {spec.jira_ref}"
        for co in spec.co_authors:
            p = _actor(co)
            message += (
                f"\n\nCo-authored-by: {p.display_name} "
                f"<{p.employee_id}@sih26.invalid>"
            )

        _run(["git", "commit", "-q", "--allow-empty", "-m", message], tmp, env=env)
        written += 1

    if push:
        _run(["git", "remote", "add", "origin", remote], tmp)
        _run(["git", "push", "-q", "--force", "-u", "origin", "main"], tmp)

    return {"commits": written, "workdir": str(tmp)}
