"""
Employee x Skill aggregation.

Combines all Evidence x Skill contributions for a given (employee, skill)
pair into one bounded [0,1] credibility score, an evidence band, a
chronological timeline, and full provenance back to source evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.engine.config import scoring_config as cfg
from backend.engine.credibility import EvidenceSkillContribution


def _band_for_score(score: float) -> str:
    for band_name, threshold in cfg.BAND_THRESHOLDS:
        if score >= threshold:
            return band_name
    return cfg.BAND_THRESHOLDS[-1][0]


def _aggregate_score(contributions: list[float]) -> float:
    if not contributions:
        return 0.0
    if cfg.AGGREGATION_METHOD == "noisy_or":
        # score = 1 - product(1 - c_i)
        # Standard way to combine independent evidence of "skill demonstrated
        # at least once" -- monotonic, saturates at 1, never needs an
        # arbitrary cap. Diminishing returns emerge naturally: a 5th piece
        # of weak evidence moves the score much less than the 1st does.
        product = 1.0
        for c in contributions:
            c = max(0.0, min(1.0, c))
            product *= (1.0 - c)
        return round(1.0 - product, 6)
    elif cfg.AGGREGATION_METHOD == "capped_sum":
        total = sum(contributions) * cfg.SUM_DAMPING_FACTOR
        return round(min(1.0, total), 6)
    else:
        raise ValueError(f"Unknown AGGREGATION_METHOD: {cfg.AGGREGATION_METHOD!r}")


@dataclass
class TimelineEntry:
    date: str | None
    evidence_id: str | None
    contribution: float


@dataclass
class EmployeeSkillResult:
    employee_id: str
    skill_id: str
    skill_name: str
    credibility_score: float
    evidence_band: str
    evidence_count: int
    first_demonstrated: str | None
    last_demonstrated: str | None
    timeline: list[TimelineEntry]
    supporting_evidence: list[dict]
    calculation_details: dict


def aggregate_employee_skills(
    contributions: list[EvidenceSkillContribution],
) -> list[EmployeeSkillResult]:
    """
    Group Evidence x Skill contributions by (employee_id, skill_id) and
    produce one bounded, banded, traceable result per pair.
    """
    groups: dict[tuple[str, str], list[EvidenceSkillContribution]] = {}
    for c in contributions:
        if not c.employee_id or not c.skill_id:
            continue  # unattributed or unmatched evidence doesn't aggregate
        groups.setdefault((c.employee_id, c.skill_id), []).append(c)

    results: list[EmployeeSkillResult] = []

    for (employee_id, skill_id), group in groups.items():
        skill_name = group[0].skill_name
        contribution_values = [g.evidence_contribution for g in group]
        score = _aggregate_score(contribution_values)
        band = _band_for_score(score)

        dated = [g for g in group if g.evidence_date]
        # Sort chronologically. Records with unparsed/invalid dates sort last
        # (they're still included -- never dropped -- just can't be placed
        # in chronological order).
        def _sort_key(g: EvidenceSkillContribution):
            return (g.age_days is None, g.age_days if g.age_days is not None else 0, g.evidence_id or "")

        # We want oldest-first chronologically: higher age_days = older = earlier.
        ordered = sorted(group, key=lambda g: (g.age_days is None, -(g.age_days or 0)))

        timeline = [
            TimelineEntry(date=g.evidence_date, evidence_id=g.evidence_id, contribution=g.evidence_contribution)
            for g in ordered
        ]

        dates_only = [g.evidence_date for g in ordered if g.evidence_date]
        first_demonstrated = dates_only[0] if dates_only else None
        last_demonstrated = dates_only[-1] if dates_only else None

        supporting_evidence = [
            {
                "evidence_id": g.evidence_id,
                "source": g.source,
                "evidence_type": g.evidence_type,
                "module_id": g.module_id,
                "date": g.evidence_date,
                "original_score": g.original_score,
                "skill_relevance": g.skill_relevance,
                "match_type": g.match_type,
                "matched_terms": g.matched_terms,
                "recency_factor": g.recency_factor,
                "evidence_contribution": g.evidence_contribution,
                "warnings": g.warnings,
            }
            for g in ordered
        ]

        results.append(
            EmployeeSkillResult(
                employee_id=employee_id,
                skill_id=skill_id,
                skill_name=skill_name,
                credibility_score=score,
                evidence_band=band,
                evidence_count=len(group),
                first_demonstrated=first_demonstrated,
                last_demonstrated=last_demonstrated,
                timeline=timeline,
                supporting_evidence=supporting_evidence,
                calculation_details={
                    "aggregation_method": cfg.AGGREGATION_METHOD,
                    "formula": "score = 1 - product(1 - contribution_i)"
                               if cfg.AGGREGATION_METHOD == "noisy_or"
                               else "score = min(1, sum(contribution_i) * damping_factor)",
                    "contribution_values": contribution_values,
                    "band_thresholds": cfg.BAND_THRESHOLDS,
                },
            )
        )

    # Stable, readable ordering: employee then skill name.
    results.sort(key=lambda r: (r.employee_id, r.skill_name or ""))
    return results
