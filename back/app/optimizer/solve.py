"""CP-SAT solve — four strictly lexicographic tiers (Piece 4 §3–§4).

The tiers are implemented as four sequential solves, exactly as Piece 4 §4
requires.  A weighted objective would require inventing coefficients large
enough to enforce priority — the tuned-constant problem the project avoids
everywhere — and four solves at demo size complete in milliseconds, so the
priority order is a fact about the code rather than an emergent property of
arithmetic.

Determinism (Piece 4 §8): num_search_workers = 1 and a fixed random_seed.  A
tie-break rule does not exist by design; uniqueness comes from the dataset, and
this pinned solver is the safety net on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.core.bands import Band
from app.core.errors import OptimizerError

#: Fixed solver seed — a duplicate optimum would resolve identically between
#: rehearsal and stage.  A safety net, not a substitute for dataset uniqueness.
SEED = 20260504
TIME_LIMIT_SECONDS = 10.0


@dataclass(frozen=True)
class Solution:
    team: list[str]
    assignments: dict[str, set[int]]       # person -> capabilities assigned
    uncovered: set[int]                     # u[c] = 1 — the residual gap
    abandoned: int                          # tier 1 value
    people: int                             # tier 2 value
    switching: int                          # tier 3 value
    high_assignments: int                   # tier 4 value


def _solver() -> cp_model.CpSolver:
    s = cp_model.CpSolver()
    s.parameters.num_search_workers = 1
    s.parameters.random_seed = SEED
    s.parameters.max_time_in_seconds = TIME_LIMIT_SECONDS
    return s


def _build_model(
    people: list[str],
    targets: list[int],
    qualifies: dict[str, dict[int, bool]],
    comps_of: dict[int, list[str]],
    band_of,
    priors: list[tuple[int, int]],
):
    """One fresh CP-SAT model, with any earlier tiers' optimal values frozen."""
    m = cp_model.CpModel()
    zero = m.NewConstant(0)

    x = {p: m.NewBoolVar(f"x_{p}") for p in people}
    y = {}
    for p in people:
        for c in targets:
            if qualifies[p][c]:
                y[p, c] = m.NewBoolVar(f"y_{p}_{c}")
    u = {c: m.NewBoolVar(f"u_{c}") for c in targets}

    # C3: covering a capability means touching every component it maps to.
    z: dict[tuple[str, str], object] = {}
    for (p, c) in y:
        for k in comps_of.get(c, []):
            z.setdefault((p, k), m.NewBoolVar(f"z_{p}_{k}"))
            m.Add(z[p, k] >= y[p, c])

    # C1 — every target gets exactly one assigned coverer, OR is marked
    # uncovered.  This is the switch that keeps the model always solvable
    # (Piece 4 §4.1).
    for c in targets:
        m.Add(sum(y.get((p, c), zero) for p in people) + u[c] == 1)
    # C2 — only selected people can be assigned.
    for (p, c) in y:
        m.Add(y[p, c] <= x[p])
    # C4 — nobody is on the team without an assignment (kills idle selections
    # surviving in a tied solution).
    for p in people:
        m.Add(x[p] <= sum(y.get((p, c), zero) for c in targets))

    objs: dict[int, object] = {}
    objs[1] = m.NewIntVar(0, len(targets), "t1")
    m.Add(objs[1] == sum(u.values()))
    objs[2] = m.NewIntVar(0, len(people), "t2")
    m.Add(objs[2] == sum(x.values()))
    max_comp = max((len(comps_of.get(c, [])) for c in targets), default=0)
    objs[3] = m.NewIntVar(0, len(people) * max_comp, "t3")
    m.Add(objs[3] == sum(z.values()))
    high = [(p, c) for (p, c) in y if band_of[p][c] == Band.HIGH]
    objs[4] = m.NewIntVar(0, len(high), "t4")
    m.Add(objs[4] == sum(y[p, c] for (p, c) in high))

    for tier, value in priors:
        m.Add(objs[tier] == value)

    return m, x, y, u, z, objs


def _solve_tiers(model_args, priors: list[tuple[int, int]], model_factory=None):
    """Run the four tiers in order, freezing each optimum.  Returns
    (solver, model, variables) from the final tier so assignments can be read."""
    solver = None
    model, x, y, u, z, objs = None, None, None, None, None, None

    for tier in (1, 2, 3, 4):
        if model_factory is not None:
            model, x, y, u, z, objs = model_factory(model_args, priors)
        else:
            model, x, y, u, z, objs = _build_model(*model_args, priors)
        if tier <= 3:
            model.Minimize(objs[tier])
        else:
            model.Maximize(objs[tier])
        solver = _solver()
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise OptimizerError(f"CP-SAT returned status {status} on tier {tier}")
        priors.append((tier, int(solver.Value(objs[tier]))))

    return solver, model, (x, y, u, z, objs)


def solve(
    people: list[str],
    targets: list[int],
    qualifies: dict[str, dict[int, bool]],
    comps_of: dict[int, list[str]],
    band_of,
) -> Solution:
    """Solve the four lexicographic tiers and read the assignments."""
    if not targets:
        return Solution([], {}, set(), 0, 0, 0, 0)

    model_args = (people, targets, qualifies, comps_of, band_of)
    solver, _model, (x, y, u, z, objs) = _solve_tiers(model_args, [])

    team = [p for p in people if solver.Value(x[p])]
    assignments: dict[str, set[int]] = {}
    for (p, c) in y:
        if solver.Value(y[p, c]):
            assignments.setdefault(p, set()).add(c)
    uncovered = {c for c in targets if solver.Value(u[c])}

    return Solution(
        team=sorted(team),
        assignments=assignments,
        uncovered=uncovered,
        abandoned=int(solver.Value(objs[1])),
        people=int(solver.Value(objs[2])),
        switching=int(solver.Value(objs[3])),
        high_assignments=int(solver.Value(objs[4])),
    )