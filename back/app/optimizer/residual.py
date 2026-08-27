"""Residual gaps — capabilities no available combination of people can cover.

Piece 4 §6.  An **output** of the optimiser, not a failure of it:
abandoning a capability is the explicit decision tier 1 minimises, and each gap
states who is closest and why, so "closest" is explained rather than asserted.
"""

from __future__ import annotations

from app.core.bands import Band
from app.coverage.engine import World


def closest_candidate(world: World, bands, cap_id: int, people: list[str]) -> dict | None:
    """The highest band any remaining person holds, even though it is below
    threshold.  Its `ceiling_basis` and `raw_record_id` make it traceable."""
    best, holder = Band.NONE, None
    for p in people:
        br = bands.get(p, {}).get(cap_id)
        if br is not None and br.band > best:
            best, holder = br.band, p
    if holder is None:
        return None
    br = bands[holder][cap_id]
    basis = br.basis
    return {
        "employee_id": holder,
        "display_name": world.employees[holder]["display_name"],
        "band": best.name,
        "ceiling_basis": basis.ceiling_basis if basis else None,
        "raw_record_id": basis.raw_record_id if basis else None,
        "age_label": basis.age_label if basis else None,
        "occurred_at": basis.occurred_at.isoformat() if basis else None,
        "binding_cap": basis.binding_cap if basis else None,
    }


def why_sentence(cap_name: str, closest: dict | None) -> str:
    """The sentence Piece 4 §6 exists to make possible:
    *"nobody can cover Database Recovery; Amit is closest at LOW, from three
    commits eighteen months ago."*  Every clause traces to a stored basis."""
    if closest is None:
        return f"no one in the coverage set holds any evidence for {cap_name}."
    return (
        f"nobody can cover {cap_name}; {closest['display_name']} is closest at "
        f"{closest['band']}, from {closest['ceiling_basis'] or 'their strongest record'}"
        f" ({closest['age_label'] or 'unknown age'}, capped by "
        f"{closest['binding_cap'] or 'role'})."
    )


def residual_entry(world: World, bands, cap_id: int, people: list[str],
                   exposure_map: dict[int, object]) -> dict:
    """One residual gap, carrying the capability's own attributes so the
    report says what it is before it says who is closest (Piece 4 §6)."""
    from app.coverage.engine import activity, density

    cap_name = world.capabilities[cap_id]
    closest = closest_candidate(world, bands, cap_id, people)
    return {
        "capability_id": cap_id,
        "name": cap_name,
        "components": sorted(world.components_of.get(cap_id, [])),
        "exposure": exposure_map.get(cap_id).value if cap_id in exposure_map else "none",
        "activity": activity(cap_id, world).value,
        "density": density(cap_id, world).value,
        "closest": closest,
        "why": why_sentence(cap_name, closest),
    }