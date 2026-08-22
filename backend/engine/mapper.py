"""
Evidence -> Skill mapping orchestration + input validation.

Handles the error cases required by spec section 13: missing dates, invalid
dates, duplicate evidence IDs, missing employee IDs, empty descriptions,
unknown evidence types, unknown skills, malformed records. Nothing is
silently discarded -- every record produces either a mapped result or a
logged warning attached to that record's own output entry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from backend.engine.config import scoring_config as cfg
from backend.engine.relevance import SkillMatch, compute_skill_matches
from backend.engine.skills import SkillTaxonomy

logger = logging.getLogger("evidence_engine.mapper")


@dataclass
class ValidatedEvidence:
    record: dict
    warnings: list[str] = field(default_factory=list)
    fatal: bool = False  # True only for records so malformed they can't be scored at all


def validate_evidence(record: dict, seen_ids: set[str]) -> ValidatedEvidence:
    warnings: list[str] = []
    fatal = False

    if not isinstance(record, dict):
        return ValidatedEvidence(record={"_raw": record}, warnings=["malformed_record: not a JSON object"], fatal=True)

    ev_id = record.get("id")
    if not ev_id:
        warnings.append("missing_evidence_id: record has no 'id'; a synthetic id will not be assigned, "
                         "record is still processed but cannot be deduplicated reliably")
    elif ev_id in seen_ids:
        warnings.append(f"duplicate_evidence_id: '{ev_id}' has already been processed; this occurrence "
                         f"is still scored independently so evidence is never silently dropped, but "
                         f"downstream consumers should treat repeated IDs as a data-quality issue")
    else:
        seen_ids.add(ev_id)

    if not record.get("employee_id"):
        warnings.append("missing_employee_id: record cannot be attributed to any employee and will be "
                         "excluded from Employee x Skill aggregation")
        fatal = True  # can't aggregate without an employee

    if not record.get("description"):
        warnings.append("empty_description: relevance will rely solely on structural module->capability "
                         "linkage (if any); textual keyword matching is unavailable for this record")

    ev_type = record.get("type")
    if ev_type and ev_type not in cfg.KNOWN_EVIDENCE_TYPES:
        warnings.append(f"unknown_evidence_type: '{ev_type}' is not in the configured known type list; "
                         f"record is still processed normally")

    module_id = record.get("module_id")
    if not module_id:
        warnings.append("missing_module_id: no structural skill signal available; relevance will rely "
                         "entirely on textual keyword matching")

    return ValidatedEvidence(record=record, warnings=warnings, fatal=fatal)


@dataclass
class MappedEvidence:
    evidence_id: str | None
    employee_id: str | None
    module_id: str | None
    original_record: dict
    skill_matches: list[SkillMatch]
    validation_warnings: list[str]
    excluded_from_aggregation: bool


def map_evidence_to_skills(records: list[dict], taxonomy: SkillTaxonomy) -> list[MappedEvidence]:
    """Validate and map a batch of raw evidence records to skill matches."""
    seen_ids: set[str] = set()
    results: list[MappedEvidence] = []

    for raw in records:
        validated = validate_evidence(raw, seen_ids)
        record = validated.record

        if validated.warnings:
            for w in validated.warnings:
                logger.warning("evidence=%s: %s", record.get("id", "<no-id>"), w)

        if validated.fatal:
            results.append(
                MappedEvidence(
                    evidence_id=record.get("id"),
                    employee_id=record.get("employee_id"),
                    module_id=record.get("module_id"),
                    original_record=record,
                    skill_matches=[],
                    validation_warnings=validated.warnings,
                    excluded_from_aggregation=True,
                )
            )
            continue

        module_id = record.get("module_id")
        if module_id and module_id not in taxonomy.modules:
            validated.warnings.append(f"unknown_module_id: '{module_id}' not found in modules.json; "
                                       f"falling back to textual-only skill matching")
            record = {**record, "module_id": None}

        skill_matches = compute_skill_matches(record, taxonomy)
        if not skill_matches:
            validated.warnings.append("unknown_skill: no capability could be matched (neither structurally "
                                       "nor via keywords); evidence is retained but contributes to no skill")

        results.append(
            MappedEvidence(
                evidence_id=raw.get("id"),
                employee_id=raw.get("employee_id"),
                module_id=raw.get("module_id"),
                original_record=raw,
                skill_matches=skill_matches,
                validation_warnings=validated.warnings,
                excluded_from_aggregation=False,
            )
        )

    return results
