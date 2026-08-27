"""Optimum uniqueness — the no-good-cut re-solve (Piece 4 §8, Piece 5 §8.15).

There is no tie-break rule by design.  Determinism therefore rests on the
dataset having a provably unique optimum: re-solve with the found solution
excluded by a no-good cut and confirm the runner-up is strictly worse on SOME
tier.  If it is not, the DATA is adjusted, never the rules.
"""

from __future__ import annotations

from app.optimizer.solve import Solution, _solve_tiers


def objective_tuple(sol: Solution) -> tuple[int, int, int, int]:
    """Lexicographic objective as a comparable tuple.  The fourth tier is
    inverted (a maximisation) so that "strictly better" is always `<`."""
    return (sol.abandoned, sol.people, sol.switching, -sol.high_assignments)


def runner_up_objective(
    people: list[str],
    targets: list[int],
    qualifies: dict[str, dict[int, bool]],
    comps_of: dict[int, list[str]],
    band_of,
    found: Solution,
) -> tuple[int, int, int, int]:
    """Re-solve with the found ASSIGNMENT excluded by a no-good cut.  The cut
    prohibits that exact combination of person-capability assignments, so the
    runner-up may differ in team or in who-covers-what."""
    from app.optimizer.solve import _build_model

    def _with_no_good(model_args, priors):
        m, x, y, u, z, objs = _build_model(*model_args, priors)
        assigned = [(p, c) for p in people for c in found.assignments.get(p, set())]
        zero = m.NewConstant(0)
        # If the found assignment selected nobody, prohibit the empty team by
        # requiring at least one person.
        if assigned:
            m.Add(sum(y.get(pair, zero) for pair in assigned) <= len(assigned) - 1)
        else:
            m.Add(sum(x.values()) >= 1)
        return m, x, y, u, z, objs

    solver, _m, (_x, _y, _u, _z, objs) = _solve_tiers(
        (people, targets, qualifies, comps_of, band_of),
        [],
        model_factory=_with_no_good,
    )
    return (
        int(solver.Value(objs[1])),
        int(solver.Value(objs[2])),
        int(solver.Value(objs[3])),
        -int(solver.Value(objs[4])),
    )


def is_unique(found: Solution, runner_up: tuple[int, int, int, int]) -> bool:
    """Runner-up strictly worse means it loses on the FIRST tier where it
    differs — which is exactly the lexicographic comparison."""
    return runner_up > objective_tuple(found)