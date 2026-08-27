"""Stage A — Eligibility.

Piece 3 §4.  Removes records that are not evidence of human engineering work.
Every exclusion is stored on the row WITH ITS REASON, so any absence is
explainable — and the schema's CHECK constraint makes a reasonless exclusion
impossible to write.

What Stage A deliberately does NOT exclude: **departed employees.**  Eligibility
and countability are separate questions:

    Is this evidence that work happened?   Yes, regardless of whether the
                                           person still works here.
    Can this person be counted on today?   No — and that is the coverage set's
                                           question, not this one.

Removing their evidence would delete the very finding the system exists to
produce: a capability would read as uncovered with no explanation of why.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Any

from app.core.config_table import Config
from app.core.enums import RecordKind

REVERT_RE = re.compile(r'^\s*Revert\s+"', re.IGNORECASE)


@dataclass(frozen=True)
class Verdict:
    eligible: bool
    reason: str | None = None


def _matches_any(value: str, patterns: list[str]) -> bool:
    lowered = (value or "").lower()
    return any(fnmatch.fnmatch(lowered, p.lower()) for p in patterns)


def assess(
    *,
    record_kind: RecordKind,
    actor_role: str,
    payload: dict[str, Any],
    is_service_account: bool,
    native_actor_id: str,
    cfg: Config,
) -> Verdict:
    """Decide eligibility for one (record, actor) pair."""

    # ── Service and bot accounts ─────────────────────────────────────────────
    # A Dependabot commit is not evidence of human knowledge.
    if is_service_account or _matches_any(native_actor_id, cfg.bot_actor_patterns):
        return Verdict(False, "bot")

    if record_kind is RecordKind.COMMIT:
        commit = payload.get("commit") or {}
        message = commit.get("message", "") or ""
        files = [f.get("filename", "") for f in (payload.get("files") or [])]
        parents = payload.get("parents") or []

        # ── Merge commits with no own changes ────────────────────────────────
        # Records a merge, not work.
        if len(parents) >= 2 and not files:
            return Verdict(False, "merge_commit")

        # ── Revert commits themselves ────────────────────────────────────────
        # Undoing work is not the same as doing it.
        if REVERT_RE.match(message):
            return Verdict(False, "revert")

        # ── Machine-only file changes ────────────────────────────────────────
        # Version bumps and regenerated code demonstrate nothing. Only fires
        # when EVERY path is machine-authored — a change that touches a lockfile
        # alongside real code is still real work.
        if files and all(_matches_any(f, cfg.excluded_path_patterns) for f in files):
            return Verdict(False, "generated_paths")

    if record_kind is RecordKind.TICKET:
        fields = payload.get("fields") or {}
        resolution = fields.get("resolution")

        # ── Tickets never reaching a done state ──────────────────────────────
        # Unfinished work is not evidence.
        if not resolution:
            return Verdict(False, "unresolved_ticket")

        # ── Resolved as duplicate / won't do / cannot reproduce ──────────────
        # Closed without work being done.
        name = (resolution or {}).get("name", "")
        if name in cfg.non_work_resolutions:
            return Verdict(False, "non_work_resolution")

        # ── Reporter-only relation ───────────────────────────────────────────
        # Filing a bug is not knowing the system.
        if actor_role == "reporter_only":
            return Verdict(False, "reporter_only")

    if record_kind is RecordKind.INCIDENT:
        # ── Notified-only relation ───────────────────────────────────────────
        # Being on a paging list is not expertise.
        if actor_role == "notified_only":
            return Verdict(False, "notified_only")

    # Ladder floors that carry no evidence at all.
    if actor_role in {"merger_only"}:
        return Verdict(False, "merger_only")

    return Verdict(True, None)


# ── Specified, deliberately not built (Piece 3 §4, §19) ──────────────────────
#
# Commits that were LATER REVERTED: work that did not survive is weak evidence.
# The rule is stated so the question has an answer, but it requires a reverse
# lookup over the whole history (find the revert, resolve the reverted SHA,
# check it landed within `revert_window_days`), and nothing in the demo depends
# on it. Hardening tier.
LATER_REVERTED_IMPLEMENTED = False
