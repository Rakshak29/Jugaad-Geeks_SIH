"""
Server-side absence simulation.

The frontend already does this in DetailsPanel.jsx; the RAG needs the same
answer server-side, because retrieval cannot run in the browser. This module
reproduces that calculation against the database and nothing else -- it does
not modify, replace, or re-score anything.

Band thresholds are imported from the engine's own config rather than
restated, so the two can never drift apart.

Coverage for a capability is the strongest single engineer on it -- the
existing MVP rule ("at least one evidence-qualified engineer per capability",
PROJECT_RULES #6/#7). Removing an engineer removes only their own evidence;
everyone else's scores are untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.models.core import Capability, CapabilityScore, Employee, EvidenceRecord, Module
from backend.rag import config as cfg
from backend.rag.compat import band_for_score as _compat_band_for_score


def band_for_score(score: float) -> str:
    """HIGH / MODERATE / LOW / NONE, straight from scoring_config.BAND_THRESHOLDS."""
    return _compat_band_for_score(score)


@dataclass
class RemainingCoverage:
    employee_id: str
    employee_name: str
    score: float
    band: str


@dataclass
class CapabilityCoverage:
    capability_id: str
    capability_name: str
    description: str

    score_before: float
    band_before: str
    score_after: float
    band_after: str

    is_gap: bool                 # band_after is LOW or NONE
    caused_by_absence: bool      # the band actually dropped
    absent_contribution: float   # what the absent engineer held

    remaining: list[RemainingCoverage] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    evidence_by_source: dict = field(default_factory=dict)
    evidence_total: int = 0

    def gap_explanation(self) -> str:
        """A factual sentence about the gap. No generated prose, no speculation."""
        if not self.is_gap:
            return "Coverage remains %s (%.2f)." % (self.band_after, self.score_after)

        if self.band_after == "NONE":
            head = "No remaining engineer has evidence-qualified coverage of this capability."
        else:
            head = "Remaining coverage is residual only (%s, %.2f)." % (
                self.band_after,
                self.score_after,
            )

        if self.caused_by_absence:
            head += " Coverage fell from %s (%.2f) to %s (%.2f) with this absence." % (
                self.band_before,
                self.score_before,
                self.band_after,
                self.score_after,
            )
        else:
            head += " This capability was already at %s before the absence." % self.band_before

        if self.remaining:
            best = self.remaining[0]
            head += " Strongest remaining: %s (%.2f, %s)." % (
                best.employee_name,
                best.score,
                best.band,
            )
        return head


@dataclass
class SimulationResult:
    absent_employee_ids: list[str]
    absent_employee_names: list[str]
    capabilities: list[CapabilityCoverage]

    @property
    def gaps(self) -> list[CapabilityCoverage]:
        """LOW or NONE after the absence -- the documentation requirements."""
        return [c for c in self.capabilities if c.is_gap]

    def as_dict(self) -> dict:
        return {
            "absent_employee_ids": self.absent_employee_ids,
            "absent_employee_names": self.absent_employee_names,
            "total_capabilities": len(self.capabilities),
            "gap_count": len(self.gaps),
            "capabilities": [
                {
                    "capability_id": c.capability_id,
                    "capability_name": c.capability_name,
                    "score_before": round(c.score_before, 4),
                    "band_before": c.band_before,
                    "score_after": round(c.score_after, 4),
                    "band_after": c.band_after,
                    "is_gap": c.is_gap,
                    "caused_by_absence": c.caused_by_absence,
                    "modules": c.modules,
                    "remaining": [
                        {
                            "employee_id": r.employee_id,
                            "employee_name": r.employee_name,
                            "score": round(r.score, 4),
                            "band": r.band,
                        }
                        for r in c.remaining
                    ],
                    "explanation": c.gap_explanation(),
                }
                for c in self.capabilities
            ],
        }


def simulate_absence(db_session, absent_employee_ids: list[str]) -> SimulationResult:
    """
    Recompute per-capability coverage with the given engineers removed.

    Every capability is evaluated, not only the ones the absent engineers
    touched -- a capability that was already uncovered is still a
    documentation requirement.
    """
    absent = set(absent_employee_ids)

    employees = {e.id: e for e in db_session.query(Employee).all()}
    unknown = [eid for eid in absent if eid not in employees]
    if unknown:
        raise ValueError("Unknown employee id(s): %s" % ", ".join(sorted(unknown)))

    scores_by_capability: dict[str, list[CapabilityScore]] = {}
    for score in db_session.query(CapabilityScore).all():
        scores_by_capability.setdefault(score.capability_id, []).append(score)

    modules_by_capability = _modules_by_capability(db_session)
    evidence_by_capability = _evidence_by_capability(db_session)

    results: list[CapabilityCoverage] = []

    for capability in db_session.query(Capability).order_by(Capability.id).all():
        rows = scores_by_capability.get(capability.id, [])

        before_scores = [r.score for r in rows]
        after_rows = [r for r in rows if r.employee_id not in absent]
        after_scores = [r.score for r in after_rows]

        score_before = max(before_scores) if before_scores else 0.0
        score_after = max(after_scores) if after_scores else 0.0

        band_before = band_for_score(score_before)
        band_after = band_for_score(score_after)

        absent_contribution = max(
            [r.score for r in rows if r.employee_id in absent] or [0.0]
        )

        remaining = sorted(
            (
                RemainingCoverage(
                    employee_id=r.employee_id,
                    employee_name=employees[r.employee_id].name
                    if r.employee_id in employees
                    else r.employee_id,
                    score=r.score,
                    band=band_for_score(r.score),
                )
                for r in after_rows
            ),
            key=lambda r: r.score,
            reverse=True,
        )

        evidence = evidence_by_capability.get(capability.id, {})

        results.append(
            CapabilityCoverage(
                capability_id=capability.id,
                capability_name=capability.name,
                description=capability.description or "",
                score_before=score_before,
                band_before=band_before,
                score_after=score_after,
                band_after=band_after,
                is_gap=band_after in cfg.GAP_BANDS,
                caused_by_absence=band_after != band_before,
                absent_contribution=absent_contribution,
                remaining=remaining,
                modules=modules_by_capability.get(capability.id, []),
                evidence_by_source=evidence,
                evidence_total=sum(evidence.values()),
            )
        )

    return SimulationResult(
        absent_employee_ids=list(absent_employee_ids),
        absent_employee_names=[
            employees[eid].name for eid in absent_employee_ids if eid in employees
        ],
        capabilities=results,
    )


def _modules_by_capability(db_session) -> dict[str, list[str]]:
    """capability_id -> module names, for retrieval context and the report."""
    out: dict[str, list[str]] = {}
    for module in db_session.query(Module).all():
        for capability in module.capabilities:
            out.setdefault(capability.id, []).append(module.name)
    return out


def _evidence_by_capability(db_session) -> dict[str, dict[str, int]]:
    """capability_id -> {source: count}, straight from evidence_records."""
    out: dict[str, dict[str, int]] = {}
    for record in db_session.query(
        EvidenceRecord.capability_id, EvidenceRecord.source
    ).all():
        capability_id, source = record
        bucket = out.setdefault(capability_id, {})
        bucket[source] = bucket.get(source, 0) + 1
    return out
