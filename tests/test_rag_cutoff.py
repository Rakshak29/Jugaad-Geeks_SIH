# tests/test_rag_cutoff.py
"""
Derived cutoffs: no configured relevance thresholds anywhere.

These tests exist to stop a tuned constant creeping back in. Each one asserts
a property that has to hold on any corpus -- scale invariance, size
independence, and the ability for an entire result set to be rejected.
"""

import pytest

from backend.rag.retrieval.cutoff import (
    CLEAR_LEAD_RATIO,
    mass_floor,
    natural_break_cut,
    separation,
)


# --- the absolute quality bar ----------------------------------------------


def test_floor_is_the_share_one_typical_term_contributes():
    # Four equal terms: each is a quarter of the query, and the median is too.
    assert mass_floor({"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0}) == pytest.approx(0.25)


def test_floor_scales_with_query_size_not_absolute_weight():
    """A short query and a long one both get a bar proportionate to themselves."""
    short = mass_floor({t: 1.0 for t in "abcdefgh"})           # 8 terms
    long = mass_floor({str(i): 1.0 for i in range(800)})       # 800 terms
    assert short == pytest.approx(1 / 8)
    assert long == pytest.approx(1 / 800)


def test_floor_is_invariant_to_uniform_rescaling():
    """Doubling every weight must not move the bar -- it is a share, not a level."""
    base = {"wal": 3.0, "restore": 2.0, "the": 0.1}
    scaled = {term: weight * 1000 for term, weight in base.items()}
    assert mass_floor(base) == pytest.approx(mass_floor(scaled))


def test_one_common_term_fails_the_bar_and_two_strong_terms_clear_it():
    term_mass = {"pitr": 5.0, "wal": 5.0, "restore": 4.0, "data": 0.5, "service": 0.4}
    floor = mass_floor(term_mass)
    total = sum(term_mass.values())

    weak = term_mass["service"] / total
    strong = (term_mass["pitr"] + term_mass["wal"]) / total

    assert weak <= floor
    assert strong > floor


def test_empty_query_has_no_bar():
    assert mass_floor({}) == 0.0
    assert mass_floor({"a": 0.0}) == 0.0


# --- the relative cut -------------------------------------------------------


def test_cut_lands_at_the_quality_cliff():
    """Real measured distribution: five good results, then a 4.5x drop."""
    scores = [1.00, 0.72, 0.67, 0.63, 0.51, 0.12, 0.12, 0.11, 0.10]
    assert natural_break_cut(scores) == 5


def test_a_smooth_run_of_scores_is_kept_whole():
    """
    The regression this function was rewritten for.

    Taking the *largest* gap cut five good results down to one, because the
    biggest step among them was a meaningless 1.35x. A gap only counts when
    quality actually falls off.
    """
    assert natural_break_cut([1.00, 0.74, 0.67, 0.58, 0.50]) == 5


def test_cut_is_invariant_to_scale():
    scores = [1.00, 0.72, 0.67, 0.12, 0.10]
    assert natural_break_cut(scores) == natural_break_cut([s * 1000 for s in scores])
    assert natural_break_cut(scores) == natural_break_cut([s * 0.001 for s in scores])


def test_cut_does_not_depend_on_how_many_results_follow_the_cliff():
    """A bigger corpus has a longer tail; that must not move the cut."""
    head = [1.00, 0.80, 0.70]
    assert natural_break_cut(head + [0.05]) == 3
    assert natural_break_cut(head + [0.05] * 500) == 3


def test_zero_and_single_and_empty_inputs():
    assert natural_break_cut([]) == 0
    assert natural_break_cut([0.5]) == 1
    assert natural_break_cut([1.0, 0.0, 0.0]) == 1


def test_min_drop_matches_the_shared_definition_of_a_clear_lead():
    just_under = [1.0, 1.0 / (CLEAR_LEAD_RATIO - 0.01)]
    just_over = [1.0, 1.0 / (CLEAR_LEAD_RATIO + 0.01)]
    assert natural_break_cut(just_under) == 2   # not a real drop, keep both
    assert natural_break_cut(just_over) == 1    # a real drop, cut


# --- separation -------------------------------------------------------------


def test_separation_is_a_ratio_not_a_difference():
    assert separation([10.0, 5.0]) == pytest.approx(2.0)
    assert separation([0.10, 0.05]) == pytest.approx(2.0)


def test_a_lone_candidate_has_nothing_to_be_confused_with():
    assert separation([0.42]) == float("inf")
    assert separation([0.42, 0.0]) == float("inf")


def test_no_candidates_means_no_separation():
    assert separation([]) == 0.0
