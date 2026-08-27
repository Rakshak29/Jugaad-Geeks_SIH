"""
Compatibility layer over the existing engine.

The RAG reuses four things from the scoring engine so that both halves of the
system agree on what a band is and what a term match is. Three of them are
private names (`_band_for_score`, `_tokenize`, `_keyword_overlap`), which means
a refactor over in `backend/engine/` could rename them without anyone thinking
about this package.

Every import is therefore attempted and falls back to a local implementation
if the name has moved. The rules:

  - BANDS must never silently diverge. The fallback re-derives them from
    `scoring_config.BAND_THRESHOLDS`, which is public configuration, so it
    still tracks a retune of the engine. It cannot drift.

  - TOKENIZING and OVERLAP are matching heuristics. A fallback that behaves
    slightly differently degrades retrieval quality a little; it does not
    produce a wrong answer. Losing them entirely would.

Nothing here modifies the engine. If the engine's own functions are present --
the normal case -- they are used unchanged, and the fallbacks never run.
"""

from __future__ import annotations

import logging
import re

from backend.engine.config import scoring_config as engine_cfg

logger = logging.getLogger("rag.compat")


# ---------------------------------------------------------------------------
# bands
# ---------------------------------------------------------------------------

try:
    from backend.engine.aggregation import _band_for_score as _engine_band_for_score
except ImportError:  # pragma: no cover - only when the engine has been refactored
    _engine_band_for_score = None
    logger.warning(
        "backend.engine.aggregation._band_for_score not found; bands will be derived "
        "directly from scoring_config.BAND_THRESHOLDS instead"
    )


def band_for_score(score: float) -> str:
    """HIGH / MODERATE / LOW / NONE for a coverage score."""
    if _engine_band_for_score is not None:
        return _engine_band_for_score(score)

    # Same rule the engine applies: first threshold the score reaches, in the
    # order the config lists them.
    for band_name, threshold in engine_cfg.BAND_THRESHOLDS:
        if score >= threshold:
            return band_name
    return engine_cfg.BAND_THRESHOLDS[-1][0]


# ---------------------------------------------------------------------------
# tokenizing
# ---------------------------------------------------------------------------

try:
    from backend.engine.skills import _tokenize as _engine_tokenize
except ImportError:  # pragma: no cover
    _engine_tokenize = None
    logger.warning("backend.engine.skills._tokenize not found; using the local fallback")

_FALLBACK_WORD_RE = re.compile(r"[a-zA-Z0-9+/#.\-]+")


def tokenize(text: str) -> set[str]:
    """Lowercased, stopword-stripped tokens."""
    if _engine_tokenize is not None:
        return _engine_tokenize(text)

    if not text:
        return set()
    stopwords = getattr(engine_cfg, "STOPWORDS", set())
    tokens = {t.strip(".,;:()").lower() for t in _FALLBACK_WORD_RE.findall(text)}
    return {t for t in tokens if t and t not in stopwords and len(t) > 2}


# ---------------------------------------------------------------------------
# keyword overlap
# ---------------------------------------------------------------------------

try:
    from backend.engine.relevance import _keyword_overlap as _engine_keyword_overlap
except ImportError:  # pragma: no cover
    _engine_keyword_overlap = None
    logger.warning("backend.engine.relevance._keyword_overlap not found; using the local fallback")


def keyword_overlap(left: set[str], right: set[str]) -> tuple[float, list[str]]:
    """(overlap_ratio, matched_terms) between two token sets."""
    if _engine_keyword_overlap is not None:
        return _engine_keyword_overlap(left, right)

    if not left or not right:
        return 0.0, []
    matched = sorted(left & right)
    if not matched:
        return 0.0, []
    denom = min(len(left), len(right)) or 1
    return min(len(matched) / denom, 1.0), matched


# ---------------------------------------------------------------------------
# label -> module aliases
# ---------------------------------------------------------------------------

try:
    from backend.mapper import LABEL_TO_MODULE_MAP as _engine_label_map
except (ImportError, AttributeError):  # pragma: no cover
    _engine_label_map = {}
    logger.warning(
        "backend.mapper.LABEL_TO_MODULE_MAP not found; Confluence labels will resolve "
        "from modules.json jira_component and module names only"
    )


def label_module_aliases() -> dict:
    """
    The curated GitHub/Jira label aliases, reused so Confluence resolves the
    same way. Optional: the two data-driven sources cover the common cases on
    their own, so losing this only costs the hand-written aliases.
    """
    return dict(_engine_label_map or {})


def engine_status() -> dict:
    """Which engine functions were found, for the doctor script."""
    return {
        "band_for_score": _engine_band_for_score is not None,
        "tokenize": _engine_tokenize is not None,
        "keyword_overlap": _engine_keyword_overlap is not None,
        "label_aliases": bool(_engine_label_map),
    }
