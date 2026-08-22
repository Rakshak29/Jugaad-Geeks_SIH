"""
Skill relevance calculation.

For a given evidence record, determine which skill(s) (capabilities) it is
relevant to and how relevant (0-1), with a transparent explanation
(matched_terms) for every match. No black-box model -- pure rule/keyword
matching over the existing taxonomy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.engine.config import scoring_config as cfg
from backend.engine.skills import SkillTaxonomy, _tokenize


@dataclass
class SkillMatch:
    skill_id: str
    skill_name: str
    relevance: float
    match_type: str  # "structural" | "structural+textual" | "textual_only"
    matched_terms: list[str] = field(default_factory=list)


def _keyword_overlap(evidence_tokens: set[str], capability_keywords: set[str]) -> tuple[float, list[str]]:
    """Return (overlap_ratio, matched_terms) between evidence text and a capability's keyword set."""
    if not evidence_tokens or not capability_keywords:
        return 0.0, []
    matched = sorted(evidence_tokens & capability_keywords)
    if not matched:
        return 0.0, []
    # Ratio relative to the smaller set keeps this stable regardless of
    # description length, so a short precise match still scores well.
    denom = min(len(evidence_tokens), len(capability_keywords)) or 1
    ratio = len(matched) / denom
    return min(ratio, 1.0), matched


def compute_skill_matches(evidence: dict, taxonomy: SkillTaxonomy) -> list[SkillMatch]:
    """
    Compute all Evidence x Skill relevance matches for one evidence record.

    Returns a list of SkillMatch, one per matched capability (an evidence
    record may match multiple skills).
    """
    description = evidence.get("description") or ""
    ev_type = evidence.get("type") or ""
    evidence_tokens = _tokenize(description) | _tokenize(ev_type)

    module_id = evidence.get("module_id")
    structural_capability_ids = set(taxonomy.module_to_capabilities(module_id)) if module_id else set()

    matches: dict[str, SkillMatch] = {}

    # --- Structural matches: module declares this capability -------------
    for cap_id in structural_capability_ids:
        cap = taxonomy.capabilities.get(cap_id)
        if not cap:
            continue
        overlap_ratio, matched_terms = _keyword_overlap(evidence_tokens, cap.keywords)
        bonus = overlap_ratio * cfg.STRUCTURAL_KEYWORD_BONUS_CAP
        relevance = min(1.0, cfg.STRUCTURAL_BASE_RELEVANCE + bonus)
        match_type = "structural+textual" if matched_terms else "structural"
        matches[cap_id] = SkillMatch(
            skill_id=cap_id,
            skill_name=cap.name,
            relevance=round(relevance, 4),
            match_type=match_type,
            matched_terms=matched_terms,
        )

    # --- Textual-only matches: keyword overlap with a capability the ------
    # --- module does NOT structurally declare (secondary skill signal) ---
    for cap_id, cap in taxonomy.capabilities.items():
        if cap_id in structural_capability_ids:
            continue  # already handled above
        overlap_ratio, matched_terms = _keyword_overlap(evidence_tokens, cap.keywords)
        if overlap_ratio < cfg.TEXTUAL_ONLY_MIN_OVERLAP:
            continue
        relevance = round(min(cfg.TEXTUAL_ONLY_RELEVANCE_CAP, overlap_ratio * cfg.TEXTUAL_ONLY_RELEVANCE_CAP * 2), 4)
        if relevance <= 0:
            continue
        matches[cap_id] = SkillMatch(
            skill_id=cap_id,
            skill_name=cap.name,
            relevance=relevance,
            match_type="textual_only",
            matched_terms=matched_terms,
        )

    return list(matches.values())
