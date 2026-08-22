"""
Top-level orchestrator for the Evidence & Skill Intelligence Engine.

Pipeline:
    normalized evidence records
      -> mapper.map_evidence_to_skills        (skill categorization)
      -> credibility.compute_contributions     (relevance x recency x strength)
      -> aggregation.aggregate_employee_skills (Employee x Skill credibility)

Public API:
    Engine.process_evidence(records)         -- full (re)processing of a batch
    Engine.update_with_new_evidence(records) -- add new evidence, recalculate

The engine keeps ALL evidence it has ever seen in memory (self._all_records)
so that "update" always recalculates from the complete, correct evidence
set. Recalculation is currently a safe deterministic full recompute (cheap
at this data scale and always correct); the pipeline is already split into
independent, side-effect-free stages, so swapping in true incremental
recalculation later (e.g. only re-aggregating affected Employee x Skill
groups) does not require restructuring anything.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from backend.engine.aggregation import EmployeeSkillResult, aggregate_employee_skills
from backend.engine.credibility import EvidenceSkillContribution, compute_contributions
from backend.engine.mapper import MappedEvidence, map_evidence_to_skills
from backend.engine.skills import SkillTaxonomy, load_taxonomy

import logging

logger = logging.getLogger("evidence_engine.engine")


def _to_jsonable(obj):
    if dataclasses.is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


class Engine:
    def __init__(self, taxonomy: SkillTaxonomy):
        self.taxonomy = taxonomy
        self._all_records: dict[str, dict] = {}   # keyed by evidence id when present
        self._unkeyed_records: list[dict] = []      # records with no id, kept in insertion order
        self.mapped: list[MappedEvidence] = []
        self.contributions: list[EvidenceSkillContribution] = []
        self.employee_skill_results: list[EmployeeSkillResult] = []

    @classmethod
    def from_input_dir(cls, input_dir: str | Path) -> "Engine":
        """
        Build an Engine from the JSON taxonomy files. Used for local demo
        data and tests only -- the production path is `from_database`.
        """
        taxonomy = load_taxonomy(input_dir)
        return cls(taxonomy)

    @classmethod
    def from_database(cls, session) -> "Engine":
        """Build an Engine with its taxonomy loaded from PostgreSQL (production path)."""
        from db.repository import load_taxonomy_from_db  # local import: db layer is optional

        taxonomy = load_taxonomy_from_db(session)
        return cls(taxonomy)

    # -- ingestion -----------------------------------------------------

    def _ingest(self, records: list[dict]) -> None:
        for r in records:
            ev_id = r.get("id") if isinstance(r, dict) else None
            if ev_id:
                if ev_id in self._all_records:
                    logger.warning(
                        "duplicate_evidence_id: '%s' was already ingested; the incoming record "
                        "replaces the previous one (last-write-wins), consistent with how "
                        "update_with_new_evidence re-submits evidence by id. Evidence is never "
                        "silently dropped -- exactly one current version per id is kept.",
                        ev_id,
                    )
                self._all_records[ev_id] = r  # last write wins for a given id
            else:
                self._unkeyed_records.append(r)

    def _all_records_list(self) -> list[dict]:
        return list(self._all_records.values()) + list(self._unkeyed_records)

    # -- pipeline --------------------------------------------------------

    def _recompute(self, reference_date=None) -> None:
        records = self._all_records_list()
        self.mapped = map_evidence_to_skills(records, self.taxonomy)
        self.contributions = compute_contributions(self.mapped, reference_date=reference_date)
        self.employee_skill_results = aggregate_employee_skills(self.contributions)

    def process_evidence(self, records: list[dict], reference_date=None) -> "Engine":
        """Full (re)processing of the given evidence batch, replacing any prior state."""
        self._all_records = {}
        self._unkeyed_records = []
        self._ingest(records)
        self._recompute(reference_date=reference_date)
        return self

    def update_with_new_evidence(self, new_records: list[dict], reference_date=None) -> "Engine":
        """Add new normalized evidence to whatever has already been processed, and recalculate."""
        self._ingest(new_records)
        self._recompute(reference_date=reference_date)
        return self

    # -- database-first entry points ----------------------------------------
    #
    # These are the production path: PostgreSQL is the source of truth for
    # both input (normalized evidence) and output (skill_evidence,
    # employee_skill_assessments). There is no required JSON stage. See
    # db/repository.py for the actual read/write SQL.

    def process_database(self, session, reference_date=None) -> "Engine":
        """
        Load normalized evidence from PostgreSQL and run the full pipeline
        against it. Equivalent to process_evidence(), but the evidence
        comes from the `evidence` table instead of being passed in.

        Safe to call again later (e.g. after new evidence rows have been
        inserted) -- each call is a full, deterministic recompute over
        whatever is currently in the database (spec section 14: MVP does a
        complete recalculation; the pipeline stages are independent and
        side-effect-free, so incremental recalculation can be added later
        without restructuring this).
        """
        from db.repository import load_evidence_from_db  # local import: db layer is optional

        records = load_evidence_from_db(session)
        return self.process_evidence(records, reference_date=reference_date)

    def write_results_to_database(self, session) -> dict:
        """
        Persist the engine's current in-memory results (self.contributions,
        self.employee_skill_results) to PostgreSQL: upserts skill_evidence
        and employee_skill_assessments. Returns a small summary dict with
        row counts written. Must be called after process_database() /
        process_evidence() in the same Engine instance.
        """
        from db.repository import write_results_to_db  # local import: db layer is optional

        return write_results_to_db(session, self)

    # -- output ------------------------------------------------------------

    def evidence_level_output(self) -> list[dict]:
        return [_to_jsonable(c) for c in self.contributions]

    def employee_skill_summary_output(self) -> list[dict]:
        """Grouped by employee, per spec section 11.B."""
        by_employee: dict[str, list[dict]] = {}
        for r in self.employee_skill_results:
            entry = {
                "skill_id": r.skill_id,
                "skill_name": r.skill_name,
                "credibility_score": r.credibility_score,
                "evidence_band": r.evidence_band,
                "evidence_count": r.evidence_count,
                "first_demonstrated": r.first_demonstrated,
                "last_demonstrated": r.last_demonstrated,
            }
            by_employee.setdefault(r.employee_id, []).append(entry)
        return [{"employee_id": emp_id, "skills": skills} for emp_id, skills in sorted(by_employee.items())]

    def employee_skill_detail_output(self) -> list[dict]:
        """Full provenance/detail per Employee x Skill pair (timeline, supporting_evidence, calc details)."""
        return [_to_jsonable(r) for r in self.employee_skill_results]

    def explain(self, employee_id: str, skill_id: str) -> dict | None:
        """
        Human-readable answer to "why does <employee> have <band> credibility for <skill>?"
        Returns the full traceable breakdown, or None if no such pair exists.
        """
        for r in self.employee_skill_results:
            if r.employee_id == employee_id and r.skill_id == skill_id:
                return {
                    "employee_id": r.employee_id,
                    "skill_id": r.skill_id,
                    "skill_name": r.skill_name,
                    "credibility_score": r.credibility_score,
                    "evidence_band": r.evidence_band,
                    "explanation": (
                        f"{employee_id} has {r.evidence_band} credibility ({r.credibility_score}) "
                        f"for '{r.skill_name}' based on {r.evidence_count} piece(s) of evidence "
                        f"spanning {r.first_demonstrated} to {r.last_demonstrated}. "
                        f"Aggregation method: {r.calculation_details['aggregation_method']} "
                        f"({r.calculation_details['formula']})."
                    ),
                    "supporting_evidence": r.supporting_evidence,
                    "timeline": _to_jsonable(r.timeline),
                }
        return None

    def write_outputs(self, output_dir: str | Path) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = {
            "evidence_level": output_dir / "evidence_level.json",
            "employee_skill_summary": output_dir / "employee_skill_summary.json",
            "employee_skill_detail": output_dir / "employee_skill_detail.json",
        }
        paths["evidence_level"].write_text(json.dumps(self.evidence_level_output(), indent=2))
        paths["employee_skill_summary"].write_text(json.dumps(self.employee_skill_summary_output(), indent=2))
        paths["employee_skill_detail"].write_text(json.dumps(self.employee_skill_detail_output(), indent=2))
        return paths
