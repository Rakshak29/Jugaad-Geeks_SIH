"""
Persistence for derived Confluence -> taxonomy mappings.

This file is an OUTPUT of the sync, not an input a human authors. The sync
derives what it can and writes its decisions here with the reason for each
one. A human only ever edits the entries the sync flagged as undecidable.

Rules:
  - status "manual" is never overwritten by a later sync
  - everything else is re-derived on every sync, so renaming a space or
    adding a service is picked up automatically
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.rag import config as cfg
from backend.rag.mapping.derive import AMBIGUOUS, AUTO, MANUAL, UNMATCHED, SpaceMatch


def load_mapping(path: Path | None = None) -> dict:
    """Read the mapping file, returning an empty structure if absent."""
    path = path or cfg.MAPPING_FILE
    if not path.exists():
        return {"generated_at": None, "spaces": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"generated_at": None, "spaces": {}}
    data.setdefault("spaces", {})
    return data


def save_mapping(mapping: dict, path: Path | None = None) -> Path:
    """Write the mapping file, creating its directory if needed."""
    path = path or cfg.MAPPING_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    mapping["generated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return path


def merge_space_matches(existing: dict, matches: list[SpaceMatch]) -> dict:
    """
    Fold freshly-derived space matches into the stored mapping.

    A human's decision (status "manual") always wins -- that is the whole
    point of recording it. Everything else is replaced by the new derivation.
    """
    spaces = dict(existing.get("spaces", {}))

    for match in matches:
        prior = spaces.get(match.space_key)
        if prior and prior.get("status") == MANUAL:
            # Keep the decision, refresh the descriptive fields around it.
            prior["space_name"] = match.space_name
            prior["candidates"] = match.candidates
            spaces[match.space_key] = prior
            continue

        spaces[match.space_key] = {
            "space_name": match.space_name,
            "service_id": match.service_id,
            "status": match.status,
            "score": match.score,
            "reasons": match.reasons,
            "candidates": match.candidates,
        }

    merged = dict(existing)
    merged["spaces"] = spaces
    return merged


def resolved_space_service(mapping: dict) -> dict[str, str]:
    """space_key -> service_id for every space that actually resolved."""
    out: dict[str, str] = {}
    for key, entry in mapping.get("spaces", {}).items():
        if entry.get("status") in (AUTO, MANUAL) and entry.get("service_id"):
            out[key] = entry["service_id"]
    return out


def unresolved_spaces(mapping: dict) -> list[dict]:
    """
    Spaces the derivation could not decide, for surfacing to a human.

    An entry here is not an error -- pages in these spaces still reach the
    package through labels or keyword search. It only means the space itself
    contributes no signal.
    """
    out = []
    for key, entry in mapping.get("spaces", {}).items():
        if entry.get("status") in (AMBIGUOUS, UNMATCHED):
            out.append(
                {
                    "space_key": key,
                    "space_name": entry.get("space_name", ""),
                    "status": entry.get("status"),
                    "score": entry.get("score", 0.0),
                    "reasons": entry.get("reasons", []),
                    "candidates": entry.get("candidates", []),
                }
            )
    return sorted(out, key=lambda e: e["space_key"])


def set_manual(space_key: str, service_id: str | None, path: Path | None = None) -> dict:
    """
    Record a human's decision for one space.

    Passing service_id=None deliberately marks a space as "maps to nothing",
    which is a real answer -- an HR or meeting-notes space genuinely has no
    service -- and stops it being re-flagged on every sync.
    """
    mapping = load_mapping(path)
    entry = mapping["spaces"].get(space_key, {})
    entry.update(
        {
            "service_id": service_id,
            "status": MANUAL,
            "reasons": ["set manually"],
        }
    )
    entry.setdefault("space_name", "")
    entry.setdefault("candidates", [])
    entry.setdefault("score", 0.0)
    mapping["spaces"][space_key] = entry
    save_mapping(mapping, path)
    return entry
