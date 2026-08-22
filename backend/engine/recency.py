"""
Recency / time-decay calculation.

recency_factor = exp(-DECAY_LAMBDA * age_in_days / DECAY_TIME_UNIT_DAYS)

Older evidence contributes less. The decay rate is fully configurable in
config/scoring_config.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

from backend.engine.config import scoring_config as cfg


@dataclass
class RecencyResult:
    evidence_date: str | None      # original date string, preserved verbatim
    age_days: float | None
    recency_factor: float
    valid_date: bool
    warning: str | None = None


def _reference_date() -> date:
    if cfg.REFERENCE_DATETIME_OVERRIDE is not None:
        return cfg.REFERENCE_DATETIME_OVERRIDE
    return datetime.now(timezone.utc).date()


def _parse_date(raw: str) -> date | None:
    """Try a small set of common date formats; ISO 8601 (YYYY-MM-DD[THH:MM:SS]) first."""
    if not raw or not isinstance(raw, str):
        return None
    candidates = [raw, raw.split("T")[0] if "T" in raw else raw]
    fmts = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%d-%m-%Y"]
    for cand in candidates:
        for fmt in fmts:
            try:
                return datetime.strptime(cand, fmt).date()
            except ValueError:
                continue
    return None


def compute_recency(evidence_date_raw: str | None, reference_date: date | None = None) -> RecencyResult:
    ref = reference_date or _reference_date()

    if not evidence_date_raw:
        return RecencyResult(
            evidence_date=None,
            age_days=None,
            recency_factor=0.0,
            valid_date=False,
            warning="missing_date: evidence has no date; recency_factor defaulted to 0.0 "
                    "(evidence is still retained and traceable, just contributes no credibility "
                    "until a date is supplied)",
        )

    parsed = _parse_date(evidence_date_raw)
    if parsed is None:
        return RecencyResult(
            evidence_date=evidence_date_raw,
            age_days=None,
            recency_factor=0.0,
            valid_date=False,
            warning=f"invalid_date: could not parse '{evidence_date_raw}'; recency_factor defaulted to 0.0",
        )

    if parsed > ref:
        # Future-dated evidence: clamp age to 0 (treated as "as of today") rather
        # than producing a >1 recency factor or a negative age.
        age_days = 0.0
        warning = f"future_date: evidence date '{evidence_date_raw}' is after the reference date; age clamped to 0"
    else:
        age_days = (ref - parsed).days
        warning = None

    recency_factor = math.exp(-cfg.DECAY_LAMBDA * age_days / cfg.DECAY_TIME_UNIT_DAYS)

    return RecencyResult(
        evidence_date=evidence_date_raw,
        age_days=age_days,
        recency_factor=round(recency_factor, 6),
        valid_date=True,
        warning=warning,
    )
