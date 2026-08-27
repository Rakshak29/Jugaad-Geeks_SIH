# tests/test_rag_simulate.py
"""Server-side absence simulation and gap identification."""

import pytest

from backend.engine.config import scoring_config
from backend.rag.coverage.simulate import band_for_score, simulate_absence


def test_bands_come_from_the_engine_config():
    """The RAG must never restate thresholds -- drift here would be silent."""
    for name, threshold in scoring_config.BAND_THRESHOLDS:
        assert band_for_score(threshold) == name
    assert band_for_score(1.0) == "HIGH"
    assert band_for_score(0.0) == "NONE"


def test_single_point_of_failure_becomes_a_none_gap(rag_session):
    result = simulate_absence(rag_session, ["E003"])
    c003 = next(c for c in result.capabilities if c.capability_id == "C003")

    assert c003.band_before == "HIGH"
    assert c003.band_after == "NONE"
    assert c003.score_after == 0.0
    assert c003.is_gap
    assert c003.caused_by_absence
    assert c003.remaining == []


def test_residual_coverage_becomes_a_low_gap(rag_session):
    result = simulate_absence(rag_session, ["E003"])
    c005 = next(c for c in result.capabilities if c.capability_id == "C005")

    assert c005.band_before == "HIGH"
    assert c005.band_after == "LOW"
    assert c005.is_gap
    assert [r.employee_name for r in c005.remaining] == ["Amit"]


def test_well_covered_capability_is_not_a_gap(rag_session):
    result = simulate_absence(rag_session, ["E003"])
    c001 = next(c for c in result.capabilities if c.capability_id == "C001")

    assert c001.band_after == "HIGH"
    assert not c001.is_gap
    assert not c001.caused_by_absence


def test_coverage_is_the_strongest_remaining_engineer(rag_session):
    """MVP rule: one evidence-qualified engineer is coverage; scores do not sum."""
    result = simulate_absence(rag_session, ["E001"])
    c001 = next(c for c in result.capabilities if c.capability_id == "C001")
    assert c001.score_after == pytest.approx(0.91)


def test_gaps_property_returns_only_low_and_none(rag_session):
    result = simulate_absence(rag_session, ["E003"])
    assert {c.capability_id for c in result.gaps} == {"C003", "C005"}
    assert all(c.band_after in ("LOW", "NONE") for c in result.gaps)


def test_multiple_absences_compound(rag_session):
    result = simulate_absence(rag_session, ["E002", "E003"])
    c005 = next(c for c in result.capabilities if c.capability_id == "C005")
    assert c005.band_after == "NONE"


def test_every_capability_is_evaluated_not_only_touched_ones(rag_session):
    """An already-uncovered capability is still a documentation requirement."""
    result = simulate_absence(rag_session, ["E001"])
    assert len(result.capabilities) == 3


def test_unknown_employee_is_rejected(rag_session):
    with pytest.raises(ValueError, match="Unknown employee"):
        simulate_absence(rag_session, ["E999"])


def test_gap_explanation_states_facts_not_speculation(rag_session):
    result = simulate_absence(rag_session, ["E003"])
    c003 = next(c for c in result.capabilities if c.capability_id == "C003")
    explanation = c003.gap_explanation()

    assert "No remaining engineer" in explanation
    assert "HIGH" in explanation and "NONE" in explanation


def test_result_serializes_for_the_api(rag_session):
    payload = simulate_absence(rag_session, ["E003"]).as_dict()
    assert payload["gap_count"] == 2
    assert payload["absent_employee_names"] == ["Sneha"]
    assert len(payload["capabilities"]) == 3
