"""Environment configuration.

Distinct from `config_table`, and the distinction matters: this file holds
*deployment* settings (where the database is, which token to use).  The `config`
TABLE holds every value that affects a CONCLUSION the system states, so that
"why is that number what it is?" is answerable by pointing at a row rather than
grepping for a constant (Piece 0 §6, SC7).

Nothing here is read by the coverage engine or the optimizer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
DATA_DIR = BACKEND_ROOT / "data"
GENERATED_DIR = DATA_DIR / "generated"
#: Payloads CAPTURED from a live run (`ece dataset capture`). Distinct from
#: GENERATED_DIR, which holds the plan the repository was built from — GitHub
#: applies its own reality on top, so the two are not interchangeable.
FIXTURE_DIR = DATA_DIR / "fixtures"


def _load_dotenv() -> None:
    """Minimal .env loader.  Avoids a dependency for eight lines of parsing."""
    for candidate in (REPO_ROOT / ".env", BACKEND_ROOT / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    github_token: str | None
    github_repo: str | None
    namer: str            # 'rule' | 'llm'
    demo_mode: bool
    log_level: str

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5432/ece",
            ),
            github_token=os.environ.get("GITHUB_TOKEN") or None,
            github_repo=os.environ.get("GITHUB_REPO") or None,
            # 'rule' ships today and is fully deterministic. 'llm' routes to a
            # provider adapter once one is chosen — the naming BOUNDARY is
            # identical either way: the namer labels an already-formed group and
            # cannot add, remove or move a single item (Piece 0 §6, SC4).
            namer=os.environ.get("NAMER", "rule").strip().lower(),
            demo_mode=_flag("DEMO_MODE", False),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )


settings = Settings.load()
