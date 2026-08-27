"""Offline greedy baseline — the Case F comparison (Piece 4 §9).

Standard greedy set cover: repeatedly select the person covering the most
currently-uncovered target capabilities, until none remain.  Not wired to any
endpoint — it exists so the demo can state the Case F numbers as measured
rather than asserted: greedy 3, exact solver 2.

Deterministic: ties break toward the alphabetically-first employee id, so the
comparison is reproducible offline.
"""

from __future__ import annotations


def greedy_team(
    people: list[str],
    targets: list[int],
    qualifies: dict[str, dict[int, bool]],
) -> list[str]:
    """Returns the ordered list of people greedy would pick.  A person is
    selected at most once; selection stops when no one covers anything left
    (the rest is a residual gap)."""
    remaining = set(targets)
    chosen: list[str] = []
    unavailable = {p for p in people if not any(qualifies[p].values())}

    while remaining:
        scores = {}
        for p in people:
            if p in chosen or p in unavailable:
                continue
            scores[p] = len(remaining & {c for c in targets if qualifies[p][c]})
        if not scores or max(scores.values()) == 0:
            break
        # Largest marginal gain; ties resolve alphabetically by employee id.
        #
        # Comparing negated code points fails on ids of unequal length —
        # (-97,) sorts BELOW (-97, -98), so "ab" beat "a" and the tie went to
        # the alphabetically LAST id. Sort the candidates and take the first
        # maximum instead; that is the rule as written.
        best = min(sorted(scores), key=lambda p: -scores[p])
        chosen.append(best)
        remaining -= {c for c in targets if qualifies[best][c]}

    return chosen