"""Identity resolution — a ladder, like everything else in this system.

Piece 2 §6.2.  Real organisations solve identity with an SSO/SCIM directory or
email matching, PLUS a manual override table — and the override table always
exists, because the automated match never reaches 100%.  This module is the
automated half; `source_identity` is the override half.

The same design principle as every other ladder applies: try the best available
signal, fall back when it is absent, land on a defined floor, and RECORD WHICH
RUNG FIRED.  An unresolved actor is not an error — it is a data-quality signal
with a name.

Why this cannot be skipped by controlling the dataset: a real repository
produces actor identifiers we did not choose.  Concretely, ours already does —
GitHub's merge button authors commits as the person who clicked it, under
whatever email their account uses, and the platform's own noreply addresses look
nothing like a corporate directory entry.  Handling that here rather than by
adding rows we happen to know the answer for is the difference between a
pipeline and a fixture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg

from app.db.conn import query

# GitHub's privacy addresses: `12345678+octocat@users.noreply.github.com`
# and the older `octocat@users.noreply.github.com`.  Extremely common in real
# repositories — many organisations enforce them.
NOREPLY_RE = re.compile(
    r"^(?:(?P<id>\d+)\+)?(?P<login>[A-Za-z0-9-]+)@users\.noreply\.github\.com$",
    re.IGNORECASE,
)

# Automation identities that are not people.  Kept as a pattern list rather than
# an enumerated set, because a real deployment meets `jenkins@`, `release-bot@`,
# `argocd@` and friends that nobody enumerated in advance.
AUTOMATION_LOCAL_PARTS = (
    "ci", "cd", "build", "builds", "pipeline", "deploy", "deployer",
    "release", "release-bot", "automation", "bot", "robot", "jenkins",
    "actions", "no-reply", "noreply", "svc", "service",
)


@dataclass(frozen=True)
class Resolution:
    employee_id: str | None
    rung: str          # which rung of the ladder fired
    normalized: str    # the identifier the ladder actually matched on


def normalize_email(raw: str) -> str:
    """Lowercase, and strip a `+tag` suffix from the local part.

    Gmail-style tagging is real and shows up in commit metadata; treating
    `rahul+github@corp.com` and `rahul@corp.com` as different people would split
    one engineer's evidence in half.
    """
    value = (raw or "").strip().lower()
    if "@" not in value:
        return value
    local, _, domain = value.partition("@")
    local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def looks_like_automation(identifier: str) -> bool:
    """Heuristic ONLY, and used only to explain an unmapped actor — never to
    exclude one.  Exclusion is Stage A's decision, driven by the configured
    pattern list, so this cannot quietly drop a real person."""
    value = (identifier or "").strip().lower()
    if value.endswith("]") and "[" in value:      # `dependabot[bot]`
        return True
    local = value.split("@", 1)[0]
    return local in AUTOMATION_LOCAL_PARTS


class IdentityResolver:
    """Loaded once per run from `source_identity`."""

    def __init__(self, rows: list[dict]) -> None:
        self._exact: dict[tuple[str, str], str] = {}
        self._normalized: dict[tuple[str, str], str] = {}
        for r in rows:
            key = (r["source_type"], r["native_actor_id"])
            self._exact[key] = r["employee_id"]
            self._normalized[(r["source_type"], normalize_email(r["native_actor_id"]))] = r["employee_id"]

    @classmethod
    def load(cls, conn: psycopg.Connection) -> "IdentityResolver":
        return cls(query(
            conn,
            "SELECT source_type, native_actor_id, employee_id FROM source_identity",
        ))

    def resolve(self, source_type: str, *candidates: str) -> Resolution:
        """Walk the ladder over every identifier the record offered.

        Rungs, strongest first:
          1  exact match on a mapped identifier
          2  normalized-email match (case, +tags)
          3  GitHub noreply address decoded to its login, then matched
          -  unmapped: recorded, never guessed
        """
        cleaned = [c.strip() for c in candidates if c and c.strip()]

        for value in cleaned:
            hit = self._exact.get((source_type, value))
            if hit:
                return Resolution(hit, "exact", value)

        for value in cleaned:
            norm = normalize_email(value)
            hit = self._normalized.get((source_type, norm))
            if hit:
                return Resolution(hit, "normalized_email", norm)

        for value in cleaned:
            m = NOREPLY_RE.match(value)
            if not m:
                continue
            login = m.group("login")
            hit = (self._exact.get((source_type, login))
                   or self._normalized.get((source_type, login.lower())))
            if hit:
                return Resolution(hit, "github_noreply_login", login)

        return Resolution(None, "unmapped", cleaned[0] if cleaned else "")
