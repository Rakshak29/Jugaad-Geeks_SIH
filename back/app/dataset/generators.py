"""Source generators — record specs become real API shapes.

Piece 5 §6.  Field names mirror the real APIs exactly, so a real connector is a
pure adapter swap with nothing downstream changing.  Two fields carry more
weight than the rest and a generator that omits either silently makes a rule
untestable:

  * Jira `changelog.histories[]` — Jira rung 1 ("made both the In Progress and
    Done transitions") reads it.  Without it every ticket falls to rung 2.
  * PagerDuty `log_entries[]` — the escalation-target signal lives here, and it
    is the strongest rung in the system.  A generator emitting only a flat
    `responder` field would make it unreachable.

The GitHub shape is produced for the *fallback* path only.  The live adapter
pulls the real API against a repository constructed with these same commits, so
both paths produce the same normalized rows — that is what makes the swap a flag
rather than a rewrite.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.core.settings import GENERATED_DIR
from app.dataset.recipes import (
    CommitSpec,
    IncidentSpec,
    Plan,
    PRSpec,
    TicketSpec,
    build_plan,
)
from app.dataset.spec import (
    CAPABILITY_BY_KEY,
    PEOPLE,
    SERVICE_ACCOUNTS,
)

_ALL_ACTORS = {p.employee_id: p for p in (*PEOPLE, *SERVICE_ACCOUNTS)}
_BY_GITHUB = {p.github_login: p for p in (*PEOPLE, *SERVICE_ACCOUNTS)}


def _person(ref: str):
    """Accept an employee_id or a raw login (bots are referenced by login)."""
    if ref in _ALL_ACTORS:
        return _ALL_ACTORS[ref]
    if ref in _BY_GITHUB:
        return _BY_GITHUB[ref]
    raise KeyError(f"unknown actor: {ref}")


def _sha(key: str) -> str:
    """Deterministic 40-char SHA from the spec key, so two runs of the
    generator produce byte-identical output (Piece 5 assertion 18)."""
    return hashlib.sha1(f"ece:{key}".encode()).hexdigest()


def _num(key: str, mod: int) -> int:
    """Deterministic numeric id.  NOT Python's hash(): string hashing is salted
    per process, so hash() here would make two generator runs differ and break
    the byte-identical-rerun guarantee."""
    return int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) % mod


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# GitHub
# ─────────────────────────────────────────────────────────────────────────────
def github_commit(spec: CommitSpec) -> dict[str, Any]:
    author = _person(spec.author)
    message = spec.message
    if spec.jira_ref and spec.jira_ref not in message:
        message += f". Closes {spec.jira_ref}"
    for co in spec.co_authors:
        p = _person(co)
        message += f"\n\nCo-authored-by: {p.display_name} <{p.employee_id}@sih26.invalid>"

    additions = int(spec.lines_changed * 0.7)
    deletions = spec.lines_changed - additions
    per_file = max(1, spec.lines_changed // max(1, len(spec.files) or 1))

    return {
        "sha": _sha(spec.key),
        "commit": {
            "author": {
                "name": author.display_name,
                "email": f"{author.employee_id}@sih26.invalid",
                # The AUTHORED date. Writable via GIT_AUTHOR_DATE, which is what
                # carries the three-year timeline. Never the committer date.
                "date": _iso(spec.occurred_at),
            },
            "committer": {"name": author.display_name, "date": _iso(spec.occurred_at)},
            "message": message,
        },
        "author": {"login": author.github_login, "id": _num(author.github_login, 10**7)},
        "committer": {"login": author.github_login},
        "parents": [{"sha": _sha(f"{spec.key}~{i}")} for i in range(spec.parents)],
        "stats": {"additions": additions, "deletions": deletions, "total": spec.lines_changed},
        "files": [
            {
                "filename": f,
                "additions": per_file,
                "deletions": 0,
                "changes": per_file,
                "status": "modified",
            }
            for f in spec.files
        ],
    }


def github_pull_request(spec: PRSpec) -> dict[str, Any]:
    author = _person(spec.author)
    files: list[str] = []
    for k in spec.capability_keys:
        files.extend(f"{CAPABILITY_BY_KEY[k].path_prefix}/service.py" for _ in range(1))
    body = spec.title
    if spec.jira_ref:
        body += f"\n\nCloses {spec.jira_ref}"
    return {
        "number": spec.number,
        "title": spec.title,
        "body": body,
        "user": {"login": author.github_login},
        "state": "closed",
        "merged": True,
        # Server-assigned in reality and NOT backdatable, which is exactly why
        # any work unit containing a real PR is necessarily fresh (Piece 5 §3.4).
        "created_at": _iso(spec.occurred_at),
        "merged_at": _iso(spec.occurred_at + timedelta(days=1)),
        "merge_commit_sha": _sha(f"pr-{spec.number}"),
        "_files": [{"filename": f} for f in files],
    }


def github_reviews(spec: PRSpec) -> list[dict[str, Any]]:
    out = []
    for idx, (reviewer, substantive) in enumerate(spec.reviewers):
        p = _person(reviewer)
        out.append({
            "id": spec.number * 100 + idx,
            "_pr_number": spec.number,
            "user": {"login": p.github_login},
            "state": "APPROVED",
            # Body presence is what separates rung 3 (substantive comments) from
            # rung 4 (bare approval). Both cap at LOW, but the rung is the
            # sentence the drill-down says out loud.
            "body": "Checked the retry path and the boundary cases; this looks right."
            if substantive else "",
            "submitted_at": _iso(spec.occurred_at + timedelta(hours=6)),
            "_capability_keys": list(spec.capability_keys),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Jira
# ─────────────────────────────────────────────────────────────────────────────
def jira_issue(spec: TicketSpec) -> dict[str, Any]:
    assignee = _person(spec.assignee)
    cap = CAPABILITY_BY_KEY[spec.capability_key] if spec.capability_key else None

    components = []
    labels: list[str] = []
    if cap and spec.with_component:
        components = [{"name": cap.jira_component, "id": str(_num(cap.key, 9999))}]
    if cap and spec.with_label:
        labels = [cap.key]

    histories = []
    if spec.transitioned_by:
        actor = _person(spec.transitioned_by)
        author_block = {
            "accountId": actor.jira_account_id,
            "displayName": actor.display_name,
        }
        # BOTH transitions -> rung 1. The changelog is core Jira behaviour, not
        # an optional field, which is why the workhorse rung rests on it.
        histories = [
            {
                "id": f"{spec.key}-h1",
                "created": _iso(spec.occurred_at - timedelta(days=3)),
                "author": author_block,
                "items": [{"field": "status", "fromString": "To Do",
                           "toString": "In Progress"}],
            },
            {
                "id": f"{spec.key}-h2",
                "created": _iso(spec.occurred_at),
                "author": author_block,
                "items": [{"field": "status", "fromString": "In Progress",
                           "toString": "Done"}],
            },
        ]

    comments = [
        {
            "id": f"{spec.key}-c{i}",
            "author": {
                "accountId": _person(c).jira_account_id,
                "displayName": _person(c).display_name,
            },
            "body": "Reproduced on staging; the retry window is the trigger.",
            "created": _iso(spec.occurred_at - timedelta(days=1)),
        }
        for i, c in enumerate(spec.commenters)
    ]

    return {
        "key": spec.key,
        "fields": {
            "project": {"key": "PAY", "name": "Payment Service"},
            "issuetype": {"name": spec.issue_type},
            "summary": spec.summary,
            "description": spec.description,
            "components": components,
            "labels": labels,
            "assignee": {
                "accountId": assignee.jira_account_id,
                "displayName": assignee.display_name,
            },
            "reporter": {
                "accountId": _person("karan").jira_account_id,
                "displayName": "Karan Mehta",
            },
            "status": {"name": "Done" if spec.resolution else "In Progress"},
            "resolution": {"name": spec.resolution} if spec.resolution else None,
            "resolutiondate": _iso(spec.occurred_at) if spec.resolution else None,
            "created": _iso(spec.occurred_at - timedelta(days=5)),
            "updated": _iso(spec.occurred_at),
        },
        "changelog": {"histories": histories},
        "comment": {"comments": comments},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Incidents — PagerDuty shape
# ─────────────────────────────────────────────────────────────────────────────
def incident(spec: IncidentSpec) -> dict[str, Any]:
    cap = CAPABILITY_BY_KEY[spec.capability_key]
    t0 = spec.occurred_at

    def agent(ref: str) -> dict[str, Any]:
        if ref == "monitoring":
            return {"id": "PMONITOR", "type": "service_reference",
                    "summary": "Datadog Monitor"}
        p = _person(ref)
        return {"id": p.pagerduty_id, "type": "user_reference",
                "summary": p.display_name}

    log: list[dict[str, Any]] = [{
        "id": f"{spec.key}-L0",
        "type": "trigger_log_entry",
        "created_at": _iso(t0),
        "agent": agent(spec.triggered_by),
    }]
    if spec.acknowledged_by:
        log.append({
            "id": f"{spec.key}-L1",
            "type": "acknowledge_log_entry",
            "created_at": _iso(t0 + timedelta(minutes=2)),
            "agent": agent(spec.acknowledged_by),
        })
    if spec.escalated_to:
        # THE strongest signal in the system, and invisible to Git: someone else
        # chose this person. `assignees` names the target of the escalation.
        log.append({
            "id": f"{spec.key}-L2",
            "type": "escalate_log_entry",
            "created_at": _iso(t0 + timedelta(minutes=4)),
            "agent": agent(spec.acknowledged_by or spec.triggered_by),
            "assignees": [agent(spec.escalated_to)],
        })
    if spec.resolved_by:
        log.append({
            "id": f"{spec.key}-L3",
            "type": "resolve_log_entry",
            "created_at": _iso(t0 + timedelta(minutes=41)),
            "agent": agent(spec.resolved_by),
        })

    return {
        "id": spec.key,
        "incident_number": int(spec.key.split("-")[1]),
        "title": spec.summary,
        "status": "resolved" if spec.resolved_by else "triggered",
        # urgency, not priority: priority is plan-gated and often absent, while
        # urgency is always present (Piece 3 §16).
        "urgency": spec.urgency,
        "created_at": _iso(t0),
        "resolved_at": _iso(t0 + timedelta(minutes=41)) if spec.resolved_by else None,
        "service": {"id": cap.service_id, "summary": cap.service_id,
                    "type": "service_reference"},
        "service_id": cap.service_id,
        "responder": _person(spec.resolved_by).pagerduty_id if spec.resolved_by else None,
        # Tracking ticket. Real incident tools carry one, and it is what places
        # an incident on a capability rather than merely on a service.
        "tracking_ticket": spec.linked_ticket,
        "log_entries": log,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Emit
# ─────────────────────────────────────────────────────────────────────────────
def _write(path: Path, payload: Any) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(payload) if isinstance(payload, list) else 1


def generate_all(plan: Plan | None = None) -> dict[str, int]:
    plan = plan or build_plan()

    commits = [github_commit(c) for c in plan.commits]
    prs = [github_pull_request(p) for p in plan.prs]
    reviews = [r for p in plan.prs for r in github_reviews(p)]
    tickets = [jira_issue(t) for t in plan.tickets]
    incidents = [incident(i) for i in plan.incidents]

    written = {
        "github_commits": _write(GENERATED_DIR / "github_commits.json", commits),
        "github_pulls": _write(GENERATED_DIR / "github_pulls.json", prs),
        "github_reviews": _write(GENERATED_DIR / "github_reviews.json", reviews),
        "jira_issues": _write(GENERATED_DIR / "jira_issues.json", tickets),
        "incidents": _write(GENERATED_DIR / "incidents.json", incidents),
    }
    return written
