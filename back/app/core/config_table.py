"""Typed access to the `config` table — the only reader of it.

Piece 0 §6 (SC7): no tuned constants.  Every value the engine reads is one of
five kinds, and `kind` records which:

    derived        a percentile of the frozen dataset's own distribution,
                   stored with the percentile that produced it
    natural_unit   a calendar boundary a person already uses when speaking
    definitional   encodes a distinction rather than a magnitude — changing it
                   would change what the rule MEANS, not how strict it is
    mapping        an org-specific lookup, not a threshold at all
    operational    affects maintenance scheduling only; no stated conclusion
                   depends on it

A number somebody picked because it felt reasonable appears nowhere, and a
missing key raises rather than defaulting — because a silent default is exactly
how a tuned constant gets in.

`as_of_date` lives here too.  It is the ONLY time source the engine may use:
all recency is measured against it, never against now().  Without that, the
dataset ages between rehearsal and the graded run and the demo quietly changes
behaviour on its own (Piece 3 §13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg

from app.core.bands import Band
from app.core.errors import MissingConfigError

# Derived keys are absent until calibration runs at dataset freeze.
DERIVED_KEYS = frozenset({
    "as_of_date",
    "effort_p10",
    "breadth_p90",
    "breadth_p98",
    "density_min",
    "clustering_overlap_threshold",
})


@dataclass(frozen=True)
class ConfigRow:
    key: str
    value: Any
    kind: str
    basis: str
    rationale: str
    owned_by: str


class Config:
    """Loaded once per process.  Values are frozen at dataset freeze and are
    never recomputed at query time — a threshold that moved when data was added
    would let new evidence in one place silently change conclusions in another.
    """

    def __init__(self, rows: dict[str, ConfigRow]) -> None:
        self._rows = rows

    # ── loading ──────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, conn: psycopg.Connection) -> "Config":
        with conn.cursor() as cur:
            cur.execute("SELECT key, value, kind, basis, rationale, owned_by FROM config")
            rows = {r["key"]: ConfigRow(**r) for r in cur.fetchall()}
        return cls(rows)

    def raw(self, key: str) -> Any:
        row = self._rows.get(key)
        if row is None:
            raise MissingConfigError(key)
        return row.value

    def row(self, key: str) -> ConfigRow:
        row = self._rows.get(key)
        if row is None:
            raise MissingConfigError(key)
        return row

    def has(self, key: str) -> bool:
        return key in self._rows

    def all_rows(self) -> list[ConfigRow]:
        return sorted(self._rows.values(), key=lambda r: r.key)

    def missing_derived(self) -> list[str]:
        return sorted(k for k in DERIVED_KEYS if k not in self._rows)

    # ── the values the engine reads ──────────────────────────────────────────
    @property
    def as_of_date(self) -> datetime:
        """Pinned to the newest occurred_at at freeze.  Never now()."""
        value = self.raw("as_of_date")
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    @property
    def coverage_threshold(self) -> Band:
        """MODERATE. Defines what 'covered' MEANS, which is why it is
        definitional rather than tuned: 'we only count people we would
        actually page.'"""
        return Band(int(self.raw("coverage_threshold")))

    @property
    def fresh_window_months(self) -> int:
        return int(self.raw("fresh_window_months"))

    @property
    def aging_window_months(self) -> int:
        return int(self.raw("aging_window_months"))

    @property
    def revert_window_days(self) -> int:
        return int(self.raw("revert_window_days"))

    @property
    def propagation_max_hops(self) -> int:
        return int(self.raw("propagation_max_hops"))

    @property
    def effort_p10(self) -> float:
        """Trivial-change floor: 10th percentile of lines changed. Code only."""
        return float(self.raw("effort_p10"))

    @property
    def breadth_p90(self) -> float:
        return float(self.raw("breadth_p90"))

    @property
    def breadth_p98(self) -> float:
        return float(self.raw("breadth_p98"))

    @property
    def density_min(self) -> float:
        """25th percentile of work units per capability. Over UNITS, never over
        people — a percentile taken over people would make a band relative to
        colleagues, which SC2 forbids."""
        return float(self.raw("density_min"))

    @property
    def clustering_overlap_threshold(self) -> float:
        return float(self.raw("clustering_overlap_threshold"))

    @property
    def unclassified_rediscovery_threshold(self) -> int:
        return int(self.raw("unclassified_rediscovery_threshold"))

    @property
    def issue_type_map(self) -> dict[str, str]:
        return dict(self.raw("issue_type_map"))

    @property
    def excluded_path_patterns(self) -> list[str]:
        return list(self.raw("excluded_path_patterns"))

    @property
    def bot_actor_patterns(self) -> list[str]:
        return list(self.raw("bot_actor_patterns"))

    @property
    def non_work_resolutions(self) -> list[str]:
        return list(self.raw("non_work_resolutions"))


def set_value(
    conn: psycopg.Connection,
    key: str,
    value: Any,
    kind: str,
    basis: str,
    rationale: str,
    owned_by: str,
) -> None:
    """Write a config row.  Used by calibration for derived values only —
    everything else is seeded as specification in `seed_rules.sql`."""
    import json

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO config (key, value, kind, basis, rationale, owned_by)
            VALUES (%s, %s::jsonb, %s, %s, %s, %s)
            ON CONFLICT (key) DO UPDATE
              SET value = EXCLUDED.value, kind = EXCLUDED.kind,
                  basis = EXCLUDED.basis, rationale = EXCLUDED.rationale,
                  owned_by = EXCLUDED.owned_by
            """,
            (key, json.dumps(value, default=str), kind, basis, rationale, owned_by),
        )
