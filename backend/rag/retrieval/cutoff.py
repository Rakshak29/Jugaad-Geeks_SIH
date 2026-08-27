"""
Deciding how many retrieved sections to keep, without a tuned threshold.

Two independent questions, answered separately because they fail in
different ways:

  1. "Is anything here good enough?"   -- an ABSOLUTE quality bar
  2. "Where does good stop?"           -- a RELATIVE cut

Question 1 has to be absolute. Any purely relative rule ranks the best of a
worthless set at 1.0, so a capability with no documentation at all would
still come back with a confident-looking answer. Reporting "no documentation
exists for this gap" is one of the most valuable things the package can say,
and it is only possible with a bar that a whole result set can fail.

Question 2 has to be relative, because the useful cut lands in a different
place for every query and no fixed number can find it.

Neither reads a configured constant. The numbers come from the query and the
result set being scored.
"""

from __future__ import annotations

from statistics import median

# What counts as "clearly ahead": twice as good as the alternative.
#
# This is a definition, not a tuned value. It is a ratio, so it reads
# identically whether scores run 0-1 or 0-1000, and it means the same thing
# on a four-page wiki as on a forty-thousand-page one. Moving it does not
# re-tune relevance -- it only changes how sharp a drop has to be before it
# counts as a drop. Shared by the retrieval cut and by space -> service
# matching so "clear winner" means one thing across the system.
CLEAR_LEAD_RATIO = 2.0


def mass_floor(term_mass: dict[str, float]) -> float:
    """
    The absolute quality bar, as a share of the query's total IDF mass.

    A match has to be worth more than one typical query term. `term_mass`
    maps each query term to weight x IDF -- its share of what the query is
    actually asking about -- so the median entry is what a single ordinary
    term contributes. Matching one common word lands at or below this and is
    rejected; matching two solid words, or one rare one, clears it.

    Derived entirely from the query. A vocabulary of 8 terms and one of 800
    both get a bar proportionate to themselves.
    """
    if not term_mass:
        return 0.0
    total = sum(term_mass.values())
    if total <= 0:
        return 0.0
    return median(term_mass.values()) / total


def natural_break_cut(scores: list[float], min_drop: float = CLEAR_LEAD_RATIO) -> int:
    """
    How many of these descending scores to keep, cut where quality falls off.

    Relevant and irrelevant results separate by a step much larger than the
    steps within either group, so the cut goes at the first point where a
    score is at least `min_drop` times the next one -- quality halving is the
    cliff, wherever it happens to be, at whatever scale.

    Measured on a real query: scores ran 1.00, 0.72, 0.67, 0.63, 0.51, then
    0.12, 0.12, 0.11, 0.10. Steps inside each group were all under 1.2x; the
    step between the groups was 4.5x. No tuned number is needed to see that.

    Crucially it takes the FIRST qualifying break, not the largest one. Simply
    taking the largest was the first version and it was wrong: among five
    genuinely good results the biggest step was a meaningless 1.35x, so four
    good sections were thrown away. Requiring a real drop means a smooth run
    of scores is kept whole, which is the right answer -- the absolute quality
    bar has already ruled on whether that whole run is worth anything.
    """
    if len(scores) <= 1:
        return len(scores)

    for i in range(1, len(scores)):
        previous, current = scores[i - 1], scores[i]
        if current <= 0:
            return i
        if previous / current >= min_drop:
            return i

    return len(scores)


def separation(scores: list[float]) -> float:
    """
    How clearly the best score leads the rest, as a ratio: best / runner-up.

    2.0 means "twice as good as the next candidate". Used to decide whether a
    Confluence space maps to one obvious service or is genuinely ambiguous.
    Scale-free, so it reads the same whether scores run 0-1 or 0-100.

    Infinity when there is only one candidate: nothing to be confused with.
    """
    if not scores:
        return 0.0
    if len(scores) == 1:
        return float("inf")

    ordered = sorted(scores, reverse=True)
    if ordered[1] <= 0:
        return float("inf")
    return ordered[0] / ordered[1]
