"""Actor role resolution — the signal ladders.

Piece 3 §2.4 and §6.1.  No rule assumes a field exists.  Every ceiling decision
walks an ORDERED ladder of signals: use the best available, fall back when
absent, and always land on a defined floor.  The rung that fired is recorded per
record, so the system can always say what it had to work with.

Each resolver returns `(actor_role, rung, ceiling_basis)`.  The *cap* for that
role is looked up from the `role_ceiling` table at band time — this module
decides WHAT ROLE YOU HELD, never how much it counts.  Keeping those separate is
what lets a trivial commit stay at rung 1 and be held down by the substance cap
instead of being excluded at the ladder, which would lose it from the drill-down.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CO_AUTHOR_RE = re.compile(r"^Co-authored-by:\s*(?P<name>.+?)\s*<(?P<email>[^>]+)>\s*$",
                          re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class RoleResult:
    actor_role: str
    rung: int
    ceiling_basis: str          # the sentence the drill-down says out loud
    native_actor_id: str


def co_authors(message: str) -> list[tuple[str, str]]:
    """(name, email) per Co-authored-by trailer.

    Core, not hardening (Piece 3 §19): without it a pairing session credits only
    whoever ran `git commit`, and in a squash-merge repository every commit is
    credited to whoever pressed the button — which would corrupt the authorship
    exception outright.
    """
    return [(m.group("name").strip(), m.group("email").strip())
            for m in CO_AUTHOR_RE.finditer(message or "")]


# ── GitHub ───────────────────────────────────────────────────────────────────
def github_commit_roles(payload: dict[str, Any]) -> list[RoleResult]:
    """Rung 1 for the author and for every co-author — unless this is a merge.

    **A commit with two or more parents is a MERGE, and its author pressed a
    button.**  GitHub's merge button authors the commit as whoever clicked it,
    so treating that as rung-1 authorship credits the person who reviewed and
    merged as though they had written the change.  In any repository that uses
    merge commits — which is most of them — that quietly corrupts the authorship
    exception, because merge volume correlates with seniority rather than with
    who built the thing.

    So a merge lands at rung 5 (`merger_only`, not evidence).  Note this is a
    different rule from Stage A's `merge_commit` exclusion, which fires only on
    a merge with an EMPTY diff: GitHub returns the first-parent diff for a merge
    commit, so that diff is usually non-empty and the Stage A test alone would
    never catch this.  Both rules are needed.
    """
    commit = payload.get("commit") or {}
    author = commit.get("author") or {}
    email = (author.get("email") or "").strip()
    login = ((payload.get("author") or {}).get("login") or "").strip()

    # The email is the reliable id here: `author` is null whenever the address
    # does not belong to a GitHub account (Piece 2 §6.2).
    primary = email or login

    if len(payload.get("parents") or []) >= 2:
        return [RoleResult("merger_only", 5,
                           "merged it without authoring or reviewing", primary)]

    out = [RoleResult("author", 1, "authored the commit", primary)]

    for _name, co_email in co_authors(commit.get("message", "")):
        if co_email and co_email != email:
            out.append(RoleResult(
                "author", 1, "co-authored the commit (Co-authored-by trailer)", co_email
            ))
    return out


def github_pr_roles(payload: dict[str, Any]) -> list[RoleResult]:
    """Rung 2 — author of a merged PR.

    Recovers authorship in squash-merge histories, where the committer is
    whoever pressed merge rather than whoever wrote the change.
    """
    # The PR *list* endpoint returns `merged_at` but NOT `merged` — that flag
    # only appears on the per-PR detail response. Checking `merged` alone
    # silently disables rung 2 against the real API, which is exactly the kind
    # of thing that passes on fixtures and fails on live data.
    if not (payload.get("merged") or payload.get("merged_at")):
        return []

    # Prefer the authors of the PR's own commits. `user.login` is who OPENED
    # the pull request, which is routinely not who wrote it: release
    # automation, dependency bots, and colleagues re-opening a branch all
    # produce a `user` that would be credited with authorship they do not hold.
    # A ladder, as everywhere else — best signal first, defined floor last.
    authors: list[str] = []
    for commit in payload.get("_commits") or []:
        email = (((commit.get("commit") or {}).get("author") or {}).get("email") or "").strip()
        login = ((commit.get("author") or {}).get("login") or "").strip()
        candidate = email or login
        if candidate and candidate not in authors:
            authors.append(candidate)

    if authors:
        return [RoleResult("pr_author", 2,
                           "authored the merged pull request", a) for a in authors]

    login = ((payload.get("user") or {}).get("login") or "").strip()
    return [RoleResult("pr_author", 2,
                       "opened the merged pull request (no commit detail available)",
                       login)] if login else []


def github_review_roles(payload: dict[str, Any]) -> list[RoleResult]:
    """Rung 3 if the review carries a body, rung 4 if it is a bare approval.

    Both cap at LOW; the rung is what the drill-down says. Note that rung 4 has
    no live instance in this dataset — GitHub does not permit approving your own
    pull request, so a single-account repository cannot produce one.
    """
    login = ((payload.get("user") or {}).get("login") or "").strip()
    if not login:
        return []
    body = (payload.get("body") or "").strip()
    if body:
        return [RoleResult("reviewer_substantive", 3,
                           "reviewed it with substantive comments", login)]
    return [RoleResult("reviewer_approval", 4,
                       "approved it without comments", login)]


# ── Jira ─────────────────────────────────────────────────────────────────────
def jira_roles(payload: dict[str, Any]) -> list[RoleResult]:
    """Walk the Jira ladder top-down and take the first rung that fires.

    Rung 1 is the workhorse and rests on the changelog, which is core Jira
    behaviour rather than an optional field.  The ASSIGNEE is the weakest usable
    signal because it is routinely bulk-set — transitions record who actually
    moved the work.
    """
    fields = payload.get("fields") or {}
    histories = ((payload.get("changelog") or {}).get("histories")) or []

    moved_in_progress: set[str] = set()
    moved_done: set[str] = set()
    for h in histories:
        actor = ((h.get("author") or {}).get("accountId") or "").strip()
        for item in h.get("items", []):
            if item.get("field") != "status":
                continue
            to = (item.get("toString") or "").strip().lower()
            if to == "in progress":
                moved_in_progress.add(actor)
            elif to in {"done", "closed", "resolved"}:
                moved_done.add(actor)

    out: list[RoleResult] = []
    seen: set[str] = set()

    # Rung 1 — made BOTH transitions.
    for actor in sorted(moved_in_progress & moved_done):
        if actor:
            out.append(RoleResult("transition_actor", 1,
                                  "moved it through In Progress to Done", actor))
            seen.add(actor)

    assignee = ((fields.get("assignee") or {}).get("accountId") or "").strip()
    resolution = fields.get("resolution")

    if assignee and assignee not in seen:
        if resolution:
            # Rung 2 — assignee at resolution, no transition detail available.
            out.append(RoleResult("assignee_at_resolution", 2,
                                  "was the assignee when it was resolved", assignee))
        else:
            # Rung 4 — assigned but never moved it.
            out.append(RoleResult("assignee_only", 4,
                                  "was assigned it but never moved it", assignee))
        seen.add(assignee)

    # Rung 3 — substantive commenter.
    for c in ((payload.get("comment") or {}).get("comments")) or []:
        actor = ((c.get("author") or {}).get("accountId") or "").strip()
        if actor and actor not in seen and (c.get("body") or "").strip():
            out.append(RoleResult("commenter_substantive", 3,
                                  "commented substantively on it", actor))
            seen.add(actor)

    # Rung 5 — reporter only. Filing a bug is not knowing the system, so this is
    # emitted and then dropped by Stage A rather than silently skipped.
    reporter = ((fields.get("reporter") or {}).get("accountId") or "").strip()
    if reporter and reporter not in seen:
        out.append(RoleResult("reporter_only", 5, "filed it and nothing more", reporter))

    return out


# ── Incidents ────────────────────────────────────────────────────────────────
def incident_roles(payload: dict[str, Any]) -> list[RoleResult]:
    """Walk the incident ladder over `log_entries`.

    Rung 2 — "was escalated to" — is the strongest signal in the entire system
    and is invisible to Git: someone else chose this person.  A person may hold
    several roles on one incident; their STRONGEST rung wins, which is why the
    results are collapsed per actor at the end.
    """
    log = payload.get("log_entries") or []

    # Rung 1 — postmortem author.
    #
    # `availability` on this rung is `bonus`: PagerDuty exposes postmortems
    # through a separate resource, so many incidents simply do not carry one and
    # the ladder must not depend on it. It was seeded in `role_ceiling` and had
    # no resolver at all, which meant an incident that DID carry a postmortem
    # would silently fall through to rung 2 or 3 — the strongest available
    # signal quietly discarded because nothing read the field.
    postmortem = payload.get("postmortem") or {}
    pm_author = ((postmortem.get("author") or {}).get("id") or "").strip()

    escalated_to: set[str] = set()
    acknowledged: set[str] = set()
    resolved: set[str] = set()
    triggered: set[str] = set()

    for entry in log:
        kind = (entry.get("type") or "").strip()
        agent = entry.get("agent") or {}
        agent_id = (agent.get("id") or "").strip()
        is_user = agent.get("type") == "user_reference"

        if kind.startswith("escalate"):
            for target in entry.get("assignees") or []:
                if target.get("type") == "user_reference":
                    tid = (target.get("id") or "").strip()
                    if tid:
                        escalated_to.add(tid)
            if is_user and agent_id:
                acknowledged.add(agent_id)   # escalating away implies engagement
        elif kind.startswith("acknowledge") and is_user and agent_id:
            acknowledged.add(agent_id)
        elif kind.startswith("resolve") and is_user and agent_id:
            resolved.add(agent_id)
        elif kind.startswith("trigger") and is_user and agent_id:
            triggered.add(agent_id)

    # Fall back to the flat `responder` field when there is no log detail at all
    # — rung 5. A real deployment with a thin incident tool lands here. A
    # postmortem still counts: it is a separate resource and does not depend on
    # the log.
    if not log:
        out: list[RoleResult] = []
        if pm_author:
            out.append(RoleResult("postmortem_author", 1,
                                  "wrote the postmortem", pm_author))
        responder = (payload.get("responder") or "").strip()
        if responder and responder != pm_author:
            out.append(RoleResult("assigned_no_detail", 5,
                                  "was assigned it, with no log detail available",
                                  responder))
        return out

    out: list[RoleResult] = []
    seen: set[str] = set()

    def add(actor: str, role: str, rung: int, basis: str) -> None:
        if actor and actor not in seen:
            out.append(RoleResult(role, rung, basis, actor))
            seen.add(actor)

    add(pm_author, "postmortem_author", 1, "wrote the postmortem")
    for actor in sorted(escalated_to):
        add(actor, "escalation_target", 2,
            "was escalated to — someone else chose them")
    for actor in sorted(resolved):
        add(actor, "resolver", 3, "resolved the incident")
    for actor in sorted(acknowledged):
        # Acknowledged, then escalated away: engaged, but the person others
        # turned to is the one credited (Piece 3 §15).
        add(actor, "ack_then_escalated_away", 4,
            "acknowledged it, then escalated it away")
    for actor in sorted(triggered):
        add(actor, "notified_only", 6, "was on the paging list and nothing more")

    return out
