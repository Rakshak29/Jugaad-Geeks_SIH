"""
Evidence-level contribution calculation.

evidence_contribution = evidence_strength x skill_relevance x recency_factor

`evidence_strength` is read from the record's existing `score` field
(config.EVIDENCE_STRENGTH_FIELD) without reinterpreting or overwriting it.
The original value is always preserved as `original_score` in the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.engine.config import scoring_config as cfg
from backend.engine.mapper import MappedEvidence
from backend.engine.recency import RecencyResult, compute_recency


@dataclass
class EvidenceSkillContribution:
    evidence_id: str | None
    employee_id: str | None
    skill_id: str
    skill_name: str
    original_score: float          # preserved verbatim from input
    evidence_strength: float       # == original_score today; named separately
                                    # so a future engine can redefine strength
                                    # without touching the preserved field
    skill_relevance: float
    match_type: str
    matched_terms: list[str]
    recency_factor: float
    age_days: float | None
    evidence_date: str | None
    evidence_contribution: float
    warnings: list[str] = field(default_factory=list)
    source: str | None = None
    evidence_type: str | None = None
    module_id: str | None = None


def _extract_evidence_strength(record: dict, warnings: list[str]) -> tuple[float, float]:
    """Returns (original_score_for_output, evidence_strength_used_in_formula)."""
    raw_score = record.get(cfg.EVIDENCE_STRENGTH_FIELD)
    if raw_score is None:
        warnings.append(f"missing_score: no '{cfg.EVIDENCE_STRENGTH_FIELD}' field; defaulted "
                         f"evidence_strength to {cfg.DEFAULT_EVIDENCE_STRENGTH}")
        return None, cfg.DEFAULT_EVIDENCE_STRENGTH
    try:
        val = float(raw_score)
    except (TypeError, ValueError):
        warnings.append(f"invalid_score: '{raw_score}' is not numeric; defaulted evidence_strength "
                         f"to {cfg.DEFAULT_EVIDENCE_STRENGTH}")
        return raw_score, cfg.DEFAULT_EVIDENCE_STRENGTH
    if not (0.0 <= val <= 1.0):
        warnings.append(f"out_of_range_score: {val} is outside [0,1]; clamped for use in the formula "
                         f"(original value preserved in original_score)")
        return val, max(0.0, min(1.0, val))
    return val, val


def compute_contributions(
    mapped: list[MappedEvidence],
    reference_date=None,
) -> list[EvidenceSkillContribution]:
    """
    Expand each MappedEvidence (which may have 0..N skill matches) into one
    EvidenceSkillContribution row per Evidence x Skill pair.
    """
    contributions: list[EvidenceSkillContribution] = []

    for me in mapped:
        record = me.original_record
        warnings = list(me.validation_warnings)

        recency: RecencyResult = compute_recency(record.get("date"), reference_date=reference_date)
        if recency.warning:
            warnings.append(recency.warning)

        original_score, evidence_strength = _extract_evidence_strength(record, warnings)

        if not me.skill_matches:
            # Still emit a row (with skill_id=None) so the evidence remains
            # visible/traceable in the evidence-level output even though it
            # contributes to no Employee x Skill aggregation.
            contributions.append(
                EvidenceSkillContribution(
                    evidence_id=me.evidence_id,
                    employee_id=me.employee_id,
                    skill_id=None,
                    skill_name=None,
                    original_score=original_score,
                    evidence_strength=evidence_strength,
                    skill_relevance=0.0,
                    match_type="none",
                    matched_terms=[],
                    recency_factor=recency.recency_factor,
                    age_days=recency.age_days,
                    evidence_date=recency.evidence_date,
                    evidence_contribution=0.0,
                    warnings=warnings,
                    source=record.get("source"),
                    evidence_type=record.get("type"),
                    module_id=me.module_id,
                )
            )
            continue

        for match in me.skill_matches:
            contribution_value = round(evidence_strength * match.relevance * recency.recency_factor, 6)
            contributions.append(
                EvidenceSkillContribution(
                    evidence_id=me.evidence_id,
                    employee_id=me.employee_id,
                    skill_id=match.skill_id,
                    skill_name=match.skill_name,
                    original_score=original_score,
                    evidence_strength=evidence_strength,
                    skill_relevance=match.relevance,
                    match_type=match.match_type,
                    matched_terms=match.matched_terms,
                    recency_factor=recency.recency_factor,
                    age_days=recency.age_days,
                    evidence_date=recency.evidence_date,
                    evidence_contribution=contribution_value,
                    warnings=list(warnings),
                    source=record.get("source"),
                    evidence_type=record.get("type"),
                    module_id=me.module_id,
                )
            )

    return contributions
