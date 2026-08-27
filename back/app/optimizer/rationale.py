"""Selection rationale — the Coverage Plan's per-person sentences.

Piece 4 §7.  Generated from the actual evidence bands for the capabilities
each person was assigned, and from `ceiling_basis` — never a bare score, never
"the model selected".  Every clause traces to a stored raw record.
"""

from __future__ import annotations

from app.coverage.engine import World


def rationale_for(
    world: World,
    bands,
    person: str,
    assigned_caps: set[int],
) -> dict:
    """The sentence Piece 4 §7 specifies, plus the structured clauses that
    carry the traceability."""

    clauses = []
    structured = []
    for cap_id in sorted(assigned_caps, key=lambda c: (world.capabilities[c] or "")):
        br = bands[person][cap_id]
        basis = br.basis
        name = world.capabilities[cap_id]

        if basis is None:
            clauses.append(f"{br.band.name} on {name} (no recorded basis)")
            structured.append({
                "capability_id": cap_id, "name": name, "band": br.band.name,
                "via_authorship_exception": br.via_authorship, "unit_count": br.unit_count,
                "raw_record_id": None, "ceiling_basis": None,
            })
            continue

        clauses.append(
            f"{br.band.name} on {name}: {basis.ceiling_basis} ({basis.age_label}), "
            f"capped by {basis.binding_cap}"
        )
        structured.append({
            "capability_id": cap_id, "name": name, "band": br.band.name,
            "via_authorship_exception": br.via_authorship, "unit_count": br.unit_count,
            "raw_record_id": basis.raw_record_id, "ceiling_basis": basis.ceiling_basis,
            "binding_cap": basis.binding_cap, "age_label": basis.age_label,
            "occurred_at": basis.occurred_at.isoformat(),
        })

    return {
        "employee_id": person,
        "display_name": world.employees[person]["display_name"],
        "assignments": structured,
        "rationale": "Covering " + "; ".join(clauses) + ".",
    }