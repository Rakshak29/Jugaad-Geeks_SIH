"""
Transfer package assembly.

    absence simulation -> LOW/NONE gaps -> retrieval -> package

Everything in the package is either computed by the existing deterministic
engine or copied verbatim from Confluence with its source URL attached. No
model writes any of it: the "summary" is a table of facts, and the prose is
the organization's own documentation, quoted with attribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.rag.coverage.simulate import CapabilityCoverage, simulate_absence
from backend.rag.retrieval.retrieve import CapabilityRetrieval, KnowledgeIndex


@dataclass
class GapEntry:
    coverage: CapabilityCoverage
    retrieval: CapabilityRetrieval

    @property
    def documented(self) -> bool:
        return self.retrieval.has_results


@dataclass
class TransferPackage:
    generated_at: datetime
    absent_employee_ids: list[str]
    absent_employee_names: list[str]

    total_capabilities: int
    gaps: list[GapEntry] = field(default_factory=list)

    index_page_count: int = 0
    index_section_count: int = 0
    index_empty: bool = False

    # Capabilities that stayed covered -- reported for completeness so the
    # reader can see what was checked, not only what failed.
    maintained: list[CapabilityCoverage] = field(default_factory=list)

    @property
    def none_gaps(self) -> list[GapEntry]:
        return [g for g in self.gaps if g.coverage.band_after == "NONE"]

    @property
    def low_gaps(self) -> list[GapEntry]:
        return [g for g in self.gaps if g.coverage.band_after == "LOW"]

    @property
    def undocumented_gaps(self) -> list[GapEntry]:
        """Gaps with no supporting documentation -- the ones that need writing."""
        return [g for g in self.gaps if not g.documented]

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "absent_employee_ids": self.absent_employee_ids,
            "absent_employee_names": self.absent_employee_names,
            "total_capabilities": self.total_capabilities,
            "gap_count": len(self.gaps),
            "none_count": len(self.none_gaps),
            "low_count": len(self.low_gaps),
            "undocumented_count": len(self.undocumented_gaps),
            "index": {
                "pages": self.index_page_count,
                "sections": self.index_section_count,
                "empty": self.index_empty,
            },
            "gaps": [
                {
                    "capability_id": g.coverage.capability_id,
                    "capability_name": g.coverage.capability_name,
                    "band_before": g.coverage.band_before,
                    "band_after": g.coverage.band_after,
                    "score_after": round(g.coverage.score_after, 4),
                    "explanation": g.coverage.gap_explanation(),
                    "documents": [d.as_dict() for d in g.retrieval.documents],
                    "query_terms": g.retrieval.query_terms,
                }
                for g in self.gaps
            ],
        }


def build_transfer_package(db_session, absent_employee_ids: list[str]) -> TransferPackage:
    """Run the full gap -> retrieval pipeline for one absence scenario."""
    simulation = simulate_absence(db_session, absent_employee_ids)
    index = KnowledgeIndex(db_session)

    entries: list[GapEntry] = []
    for coverage in simulation.gaps:
        retrieval = index.retrieve_for_capability(coverage.capability_id)
        entries.append(GapEntry(coverage=coverage, retrieval=retrieval))

    # NONE before LOW, then weakest first -- worst problems at the top.
    entries.sort(key=lambda e: (e.coverage.band_after != "NONE", e.coverage.score_after))

    return TransferPackage(
        generated_at=datetime.now(timezone.utc),
        absent_employee_ids=simulation.absent_employee_ids,
        absent_employee_names=simulation.absent_employee_names,
        total_capabilities=len(simulation.capabilities),
        gaps=entries,
        index_page_count=index.page_count,
        index_section_count=index.section_count,
        index_empty=index.is_empty(),
        maintained=[c for c in simulation.capabilities if not c.is_gap],
    )
