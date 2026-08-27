"""Target set and candidate computation (Piece 4 §2.3, §3.1)."""

from __future__ import annotations

from app.core.config_table import Config
from app.coverage.engine import BandResult, World


def qualifies(band: BandResult | None, cfg: Config) -> bool:
    """`band(p, c) >= coverage_threshold` (MODERATE).  This IS the boolean
    the solver needs to know when it may stop adding people."""
    return band is not None and band.band >= cfg.coverage_threshold


def target_set_of_departure(world: World, bands, employee_id: str) -> list[int]:
    """T = the capabilities for which the departing person was a coverer,
    REGARDLESS of whether anyone else remains (Piece 4 §2.3).

    This framing is load-bearing.  A Lost-only target set is by definition
    disjoint from every candidate's qualifications, so the model would return
    an empty team on every run.  The Coverage Team answers "who holds these
    now?", not "which capabilities are still covered?" — status already answers
    that.  The Lost members of T need no special handling: no candidate
    qualifies for them, so u[c]=1 falls out of constraint C1 and they surface
    as the residual gap.
    """
    return sorted(
        cap for cap in world.capabilities
        if qualifies(bands.get(employee_id, {}).get(cap), world.cfg)
    )


def candidates(world: World, employee_id: str | None) -> list[str]:
    """P = the coverage set, minus the person being simulated.  Departed
    employees are excluded from the coverage set everywhere (Piece 3 §10.1)."""
    people = [p for p in world.coverage_set if p != employee_id]
    return sorted(people)


def qualifications(
    world: World,
    bands,
    people: list[str],
    targets: list[int],
) -> dict[str, dict[int, bool]]:
    """person -> capability -> clears the threshold.  `y` variables are created
    only where this is true (Piece 4 §3.2)."""
    return {
        p: {c: qualifies(bands.get(p, {}).get(c), world.cfg) for c in targets}
        for p in people
    }