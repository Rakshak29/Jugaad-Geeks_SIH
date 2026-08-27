"""
Configuration for the Capability Gap RAG subsystem.

Kept separate from backend/config.py so the RAG layer can be configured (or
left entirely unconfigured) without touching the existing scoring stack.
Everything here has a working default except the Confluence credentials --
without those the sync is unavailable, but every downstream stage still runs
against whatever pages are already in the database.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Confluence connection
# ---------------------------------------------------------------------------
# Cloud site base URL, including the /wiki suffix, e.g.
#   https://acme.atlassian.net/wiki
CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL", "").rstrip("/")

# Atlassian account email + API token (id.atlassian.com -> Security -> API tokens).
# These are sent as HTTP Basic auth.
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL", "")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "")

# Comma-separated space keys to sync. Empty means "every space the token can read".
CONFLUENCE_SPACE_KEYS = [
    s.strip() for s in os.getenv("CONFLUENCE_SPACE_KEYS", "").split(",") if s.strip()
]

# Page fetch size per API request (Confluence caps this server-side).
CONFLUENCE_PAGE_LIMIT = int(os.getenv("CONFLUENCE_PAGE_LIMIT", "50"))

# Seconds to wait on any single Confluence HTTP call.
CONFLUENCE_TIMEOUT = float(os.getenv("CONFLUENCE_TIMEOUT", "30"))


_REQUIRED_CONFLUENCE_SETTINGS = (
    "CONFLUENCE_BASE_URL",
    "CONFLUENCE_EMAIL",
    "CONFLUENCE_API_TOKEN",
)

# Values that are obviously not real, as a backstop for when .env.example is
# unavailable. Matched case-insensitively as substrings.
_PLACEHOLDER_MARKERS = (
    "your-site",
    "your_site",
    "you@example.com",
    "your_confluence",
    "token_here",
    "changeme",
    "<your",
)


def _example_values() -> dict[str, str]:
    """
    The placeholder values as written in .env.example.

    Comparing against this file is the reliable way to spot an untouched
    setting, because it catches whatever placeholder text the team actually
    used rather than a list guessed here.
    """
    example_path = BASE_DIR / ".env.example"
    if not example_path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        for line in example_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    except OSError:
        return {}
    return values


def _looks_generic(value: str) -> bool:
    """True when a value is visibly a stand-in rather than a real setting."""
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _is_placeholder(name: str, value: str) -> bool:
    """
    True when a setting still holds an unedited example value.

    Matching .env.example is only treated as evidence when the example value
    is *itself* visibly a stand-in. People do paste real credentials into
    .env.example -- it has happened on this project -- and without that guard
    a working configuration gets reported as unconfigured and the sync refuses
    to run.

    The bias is deliberate. Wrongly rejecting a valid setup blocks the user
    with a misleading message; wrongly accepting a placeholder just produces
    an HTTP 401 that now explains itself clearly. The second failure is much
    cheaper than the first.
    """
    if not value:
        return False
    if _looks_generic(value):
        return True

    example = _example_values().get(name, "")
    return bool(example) and example == value and _looks_generic(example)


def _current_confluence_settings() -> dict[str, str]:
    return {
        "CONFLUENCE_BASE_URL": CONFLUENCE_BASE_URL,
        "CONFLUENCE_EMAIL": CONFLUENCE_EMAIL,
        "CONFLUENCE_API_TOKEN": CONFLUENCE_API_TOKEN,
    }


def reload_persisted_confluence_settings() -> dict:
    """
    (Re)apply Confluence settings saved from the dashboard's Setup tab.

    Settings written by the UI live in data/rag/settings.json (see
    backend.rag.settings). Values there override the ``.env`` defaults by
    re-assigning the module globals, so every consumer that reads
    ``cfg.CONFLUENCE_*`` -- the client, the sync, the status endpoint -- picks
    them up without any change.

    Returns the effective values actually in force, with the API token included
    so callers in-process can tell whether one is present (it is never sent
    back to the browser).
    """
    global CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, CONFLUENCE_SPACE_KEYS  # noqa: PLW0603
    try:
        from backend.rag.settings import load as _load_settings

        overrides = _load_settings()
    except Exception:  # pragma: no cover - defensive; settings is a thin module
        overrides = {}

    if overrides:
        base_url = (overrides.get("base_url") or "").strip().rstrip("/")
        if base_url:
            CONFLUENCE_BASE_URL = base_url
        if overrides.get("email"):
            CONFLUENCE_EMAIL = overrides["email"].strip()
        if overrides.get("api_token"):
            CONFLUENCE_API_TOKEN = overrides["api_token"].strip()
        if "space_keys" in overrides:
            CONFLUENCE_SPACE_KEYS = [
                s.strip() for s in str(overrides.get("space_keys") or "").split(",") if s.strip()
            ]

    return {
        "base_url": CONFLUENCE_BASE_URL or None,
        "email": CONFLUENCE_EMAIL or None,
        "api_token": CONFLUENCE_API_TOKEN or None,
        "space_keys": CONFLUENCE_SPACE_KEYS or None,
    }


def unset_confluence_settings() -> list[str]:
    """Required settings that are empty."""
    current = _current_confluence_settings()
    return [name for name in _REQUIRED_CONFLUENCE_SETTINGS if not current[name]]


def placeholder_confluence_settings() -> list[str]:
    """
    Required settings still holding an unedited .env.example value.

    Worth separating from "unset": a placeholder looks configured, so without
    this check the sync makes a real request and comes back with HTTP 401,
    which sends the reader hunting for a bad token when the actual problem is
    that .env was never edited.
    """
    current = _current_confluence_settings()
    return [
        name for name in _REQUIRED_CONFLUENCE_SETTINGS
        if current[name] and _is_placeholder(name, current[name])
    ]


def confluence_is_configured() -> bool:
    """True when enough is set to attempt a sync."""
    return not unset_confluence_settings() and not placeholder_confluence_settings()


def missing_confluence_settings() -> list[str]:
    """Names of the required settings that are unset or still placeholders."""
    return unset_confluence_settings() + placeholder_confluence_settings()


def confluence_config_problem() -> str | None:
    """A precise, actionable description of why Confluence cannot be used yet."""
    unset = unset_confluence_settings()
    placeholders = placeholder_confluence_settings()
    if not unset and not placeholders:
        return None

    env_path = BASE_DIR / ".env"
    parts = []

    if unset:
        parts.append("not set: %s" % ", ".join(unset))
    if placeholders:
        parts.append(
            "still the example value from .env.example: %s" % ", ".join(placeholders)
        )

    detail = "; ".join(parts)
    location = str(env_path) if env_path.exists() else "%s (create it from .env.example)" % env_path

    return (
        "Confluence is not configured -- %s. Edit %s and set real values. "
        "The API token comes from "
        "https://id.atlassian.com/manage-profile/security/api-tokens, and "
        "CONFLUENCE_BASE_URL must be your own Atlassian site including the "
        "/wiki suffix." % (detail, location)
    )


# ---------------------------------------------------------------------------
# Mapping derivation
# ---------------------------------------------------------------------------
# Where the derived space->service / label->module decisions are persisted.
# This file is an OUTPUT of the sync, not something a human authors: the sync
# derives what it can and records it here. Entries a human has resolved are
# marked "manual" and are never overwritten by a later sync.
MAPPING_FILE = Path(
    os.getenv("RAG_MAPPING_FILE", str(BASE_DIR / "data" / "rag" / "confluence_mapping.json"))
)

# NOTE: space -> service matching has no tuned thresholds. A space with no
# vocabulary overlap is unmatched; otherwise the decision is whether the best
# candidate clearly leads the runner-up, expressed as a scale-free ratio in
# mapping/derive.py (CLEAR_WINNER_RATIO). Nothing here to configure.


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
# BM25 tuning. The published Okapi defaults -- these describe term-frequency
# saturation and length normalization, which behave the same on any corpus.
# They are not corpus-specific and should not need tuning per deployment.
BM25_K1 = float(os.getenv("RAG_BM25_K1", "1.5"))
BM25_B = float(os.getenv("RAG_BM25_B", "0.75"))

# NOTE: there is deliberately no relevance threshold here.
#
# How many keyword results survive is decided per query, from the query and
# the result set: an absolute quality bar derived from the query's own term
# weights, then a natural-break cut through the scores. See retrieval/cutoff.py.
#
# An earlier version had RAG_KEYWORD_MIN_SCORE and RAG_KEYWORD_MIN_TERMS here.
# Both were calibrated against a four-page test wiki, which meant every new
# deployment inherited that wiki's shape and had to re-tune them by hand.

# --- size caps, not quality thresholds -------------------------------------
# These bound how much ends up in the final document. They do not decide what
# is relevant -- the cutoffs above have already done that -- so raising them
# only makes the package longer, never less accurate.

# Maximum source documents shown per capability gap.
MAX_DOCS_PER_GAP = int(os.getenv("RAG_MAX_DOCS_PER_GAP", "5"))

# Maximum extracted sections shown from a keyword-matched document.
MAX_SECTIONS_PER_DOC = int(os.getenv("RAG_MAX_SECTIONS_PER_DOC", "4"))

# How many distinct terms to mine from a capability's historical evidence.
MAX_EVIDENCE_TERMS = int(os.getenv("RAG_MAX_EVIDENCE_TERMS", "40"))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
# Where generated transfer packages are written.
OUTPUT_DIR = Path(os.getenv("RAG_OUTPUT_DIR", str(BASE_DIR / "data" / "rag" / "packages")))

# Coverage bands that constitute a documentation requirement.
GAP_BANDS = {"LOW", "NONE"}
