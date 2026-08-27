"""Minimum Coverage Team optimizer — Piece 4.

Given a loss, the smallest group of remaining people that restores coverage,
and an honest statement of what no group can restore.

    targets.py     T = everything the departing person was covering (P4 §2.3)
    solve.py       CP-SAT, four strictly lexicographic solves (P4 §3–§4)
    residual.py    u[c]=1 capabilities, with who is closest and why (P4 §6)
    rationale.py   the Coverage Plan's per-person sentences (P4 §7)
    greedy.py      the offline greedy comparison for Case F (P4 §9)
    uniqueness.py  the no-good-cut re-solve that proves the optimum is unique (P4 §8)

Nothing here writes a row and nothing here makes a network call.  The
optimiser reads bands that Piece 3 computed as pure functions over the
database, which is what keeps SC9 structurally true.
"""

from __future__ import annotations

from app.optimizer.targets import (
    candidates,
    qualifications,
    target_set_of_departure,
)
from app.optimizer.solve import Solution, solve
from app.optimizer.greedy import greedy_team
from app.optimizer.uniqueness import objective_tuple, runner_up_objective

__all__ = [
    "Solution", "solve", "candidates", "qualifications",
    "target_set_of_departure", "greedy_team", "objective_tuple",
    "runner_up_objective",
]