"""
Persisted Confluence connection settings, saved from the dashboard's Setup tab.

The RAG subsystem originally read Confluence credentials from ``.env`` (the
CLI-oriented path). The Setup tab lets the user enter them in the UI instead;
this module is where those UI-saved values live on disk, separate from the
version-controlled source tree.

Precedence is simple: a value written here overrides the ``.env`` default,
because it was saved last and is reloaded into the in-process config. Empty
values are never written, so leaving a field blank keeps whatever ``.env``
already provides.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.rag import config as cfg


def settings_file() -> Path:
    """Where the UI-saved settings live. Output, not source -- not committed."""
    return cfg.BASE_DIR / "data" / "rag" / "settings.json"


def load() -> dict:
    """The persisted Confluence settings (empty dict when none saved yet)."""
    path = settings_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    conn = data.get("confluence") or {}
    return conn if isinstance(conn, dict) else {}


def save(confluence: dict) -> dict:
    """
    Persist Confluence settings.

    Only non-empty values are stored, so a blank field means "keep whatever is
    already configured" rather than "clear this setting".
    """
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {k: v for k, v in (confluence or {}).items() if v not in (None, "")}
    path.write_text(
        json.dumps({"confluence": cleaned}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return cleaned
