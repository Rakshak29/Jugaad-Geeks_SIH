"""
Capability gap context: the bridge between the coverage engine and retrieval.

This is the step between "which capabilities are LOW or NONE" and "search for
their documentation". It was previously implicit -- build_transfer_package
went straight from gaps to retrieval -- which made it impossible to inspect
what the system was about to search for, or to feed the gap set into anything
other than the built-in retriever.

    simulate_absence()      -> which capabilities fall to LOW / NONE
    build_gap_contexts()    -> everything known about each of those   <-- here
    KnowledgeIndex.retrieve -> the documentation that addresses them

Each context is a self-contained description of one gap: what the capability
is, how badly it is uncovered, which modules and services it lives in, and
the exact search vocabulary assembled for it, with the evidence-derived terms
called out separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.models.core import Module, Service
from backend.rag.coverage.simulate import CapabilityCoverage, simulate_absence
from backend.rag.retrieval.vocabulary import CapabilityVocabulary, build_vocabularies


@dataclass
class ModuleContext:
    module_id: str
    module_name: str
    module_description: str
    service_id: str | None
    service_name: str | None


@dataclass
class CapabilityContext:
    """Everything the retrieval layer knows about one gap, before searching."""

    capability_id: str
    capability_name: str
    description: str

    # -- how bad is it -----------------------------------------------------
    band_before: str
    band_after: str
    score_before: float
    score_after: float
    caused_by_absence: bool
    remaining_engineers: list[dict] = field(default_factory=list)

    # -- where does it live ------------------------------------------------
    modules: list[ModuleContext] = field(default_factory=list)

    # -- what will be searched for ----------------------------------------
    query_terms: list[dict] = field(default_factory=list)   # term, weight, discrimination
    evidence_terms: list[str] = field(default_factory=list)
    evidence_by_source: dict = field(default_factory=dict)
    evidence_total: int = 0

    explanation: str = ""

    def query(self) -> dict[str, float]:
        """The weighted term set, in the shape BM25Index.search expects."""
        return {entry["term"]: entry["weight"] for entry in self.query_terms}

    def as_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "capability_name": self.capability_name,
            "description": self.description,
            "coverage": {
                "band_before": self.band_before,
                "band_after": self.band_after,
                "score_before": round(self.score_before, 4),
                "score_after": round(self.score_after, 4),
                "caused_by_absence": self.caused_by_absence,
                "remaining": self.remaining_engineers,
            },
            "modules": [
                {
                    "module_id": m.module_id,
                    "module_name": m.module_name,
                    "description": m.module_description,
                    "service_id": m.service_id,
                    "service_name": m.service_name,
                }
                for m in self.modules
            ],
            "retrieval_context": {
                "query_terms": self.query_terms,
                "evidence_terms": self.evidence_terms,
                "evidence_by_source": self.evidence_by_source,
                "evidence_total": self.evidence_total,
            },
            "explanation": self.explanation,
        }


def build_gap_contexts(db_session, absent_employee_ids: list[str]) -> list[CapabilityContext]:
    """
    Steps 1 and 2 in one call: find the LOW/NONE capabilities, then assemble
    everything retrieval would use for each of them.

    Runs no retrieval itself, so it works with an empty Confluence index and
    can be used to check what the system is about to search for.
    """
    simulation = simulate_absence(db_session, absent_employee_ids)
    vocabularies = build_vocabularies(db_session)
    modules_by_capability = _modules_by_capability(db_session)

    return [
        _context_for(coverage, vocabularies.get(coverage.capability_id), modules_by_capability)
        for coverage in simulation.gaps
    ]


def build_context_for_capability(db_session, capability_id: str, absent_employee_ids: list[str]):
    """The same, for one capability, whether or not it is currently a gap."""
    simulation = simulate_absence(db_session, absent_employee_ids)
    coverage = next(
        (c for c in simulation.capabilities if c.capability_id == capability_id), None
    )
    if coverage is None:
        return None

    vocabularies = build_vocabularies(db_session)
    return _context_for(
        coverage, vocabularies.get(capability_id), _modules_by_capability(db_session)
    )


def _context_for(
    coverage: CapabilityCoverage,
    vocabulary: CapabilityVocabulary | None,
    modules_by_capability: dict[str, list[ModuleContext]],
) -> CapabilityContext:
    query_terms: list[dict] = []
    evidence_terms: list[str] = []

    if vocabulary:
        for term, weight in sorted(vocabulary.terms.items(), key=lambda kv: kv[1], reverse=True):
            query_terms.append(
                {
                    "term": term,
                    "weight": round(weight, 4),
                    # How well this term separates capabilities: 0 means it
                    # appears under all of them and carries no signal.
                    "discrimination": round(vocabulary.discrimination.get(term, 0.0), 4),
                    "from_evidence": term in vocabulary.evidence_terms,
                }
            )
        evidence_terms = list(vocabulary.evidence_terms)

    return CapabilityContext(
        capability_id=coverage.capability_id,
        capability_name=coverage.capability_name,
        description=coverage.description,
        band_before=coverage.band_before,
        band_after=coverage.band_after,
        score_before=coverage.score_before,
        score_after=coverage.score_after,
        caused_by_absence=coverage.caused_by_absence,
        remaining_engineers=[
            {
                "employee_id": r.employee_id,
                "employee_name": r.employee_name,
                "score": round(r.score, 4),
                "band": r.band,
            }
            for r in coverage.remaining
        ],
        modules=modules_by_capability.get(coverage.capability_id, []),
        query_terms=query_terms,
        evidence_terms=evidence_terms,
        evidence_by_source=coverage.evidence_by_source,
        evidence_total=coverage.evidence_total,
        explanation=coverage.gap_explanation(),
    )


def _modules_by_capability(db_session) -> dict[str, list[ModuleContext]]:
    """capability_id -> the modules and services that implement it."""
    services = {s.id: s for s in db_session.query(Service).all()}
    out: dict[str, list[ModuleContext]] = {}

    for module in db_session.query(Module).all():
        service = services.get(module.service_id) if module.service_id else None
        entry = ModuleContext(
            module_id=module.id,
            module_name=module.name,
            module_description=module.description or "",
            service_id=module.service_id,
            service_name=service.name if service else None,
        )
        for capability in module.capabilities:
            out.setdefault(capability.id, []).append(entry)

    return out
