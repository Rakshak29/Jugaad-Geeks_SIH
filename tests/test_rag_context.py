# tests/test_rag_context.py
"""
Gap context: the step between "which capabilities are LOW/NONE" and
"search for their documentation".
"""

from backend.rag.coverage.context import build_context_for_capability, build_gap_contexts


def test_contexts_are_built_for_exactly_the_gaps(rag_session):
    contexts = build_gap_contexts(rag_session, ["E003"])
    assert {c.capability_id for c in contexts} == {"C003", "C005"}


def test_context_carries_the_coverage_figures(rag_session):
    context = next(c for c in build_gap_contexts(rag_session, ["E003"]) if c.capability_id == "C003")

    assert context.band_before == "HIGH"
    assert context.band_after == "NONE"
    assert context.score_after == 0.0
    assert context.caused_by_absence
    assert context.remaining_engineers == []
    assert "No remaining engineer" in context.explanation


def test_context_carries_modules_and_their_services(rag_session):
    context = next(c for c in build_gap_contexts(rag_session, ["E003"]) if c.capability_id == "C003")

    assert [m.module_id for m in context.modules] == ["M003"]
    assert context.modules[0].service_name == "Data & Reliability Infrastructure"


def test_context_exposes_the_query_that_will_be_searched(rag_session):
    context = next(c for c in build_gap_contexts(rag_session, ["E003"]) if c.capability_id == "C003")

    terms = {entry["term"] for entry in context.query_terms}
    assert "wal" in terms      # from CAPABILITY_KEYWORD_OVERRIDES
    assert "pitr" in terms

    for entry in context.query_terms:
        assert entry["weight"] > 0
        assert "discrimination" in entry
        assert "from_evidence" in entry


def test_query_terms_are_ordered_strongest_first(rag_session):
    context = next(c for c in build_gap_contexts(rag_session, ["E003"]) if c.capability_id == "C003")
    weights = [entry["weight"] for entry in context.query_terms]
    assert weights == sorted(weights, reverse=True)


def test_query_helper_returns_the_bm25_input_shape(rag_session):
    context = next(c for c in build_gap_contexts(rag_session, ["E003"]) if c.capability_id == "C003")
    query = context.query()
    assert isinstance(query, dict)
    assert all(isinstance(v, float) for v in query.values())


def test_terms_shared_by_every_capability_carry_no_weight(rag_session):
    """
    Capability-IDF replaced a hard 60% ubiquity cutoff. A term under every
    capability should fall out on its own rather than at a configured line.
    """
    contexts = build_gap_contexts(rag_session, ["E003"])
    for context in contexts:
        for entry in context.query_terms:
            # Anything that survived must discriminate at least a little.
            assert entry["discrimination"] > 0


def test_context_works_before_any_confluence_sync(rag_session):
    """Step 1 and 2 must not depend on step 3 having run."""
    contexts = build_gap_contexts(rag_session, ["E003"])
    assert len(contexts) == 2
    assert all(c.query_terms for c in contexts)


def test_single_capability_context_works_for_a_non_gap(rag_session):
    context = build_context_for_capability(rag_session, "C001", ["E003"])
    assert context is not None
    assert context.capability_id == "C001"
    assert context.band_after == "HIGH"


def test_unknown_capability_returns_none(rag_session):
    assert build_context_for_capability(rag_session, "C999", ["E003"]) is None


def test_context_serializes_for_the_api(rag_session):
    payload = build_gap_contexts(rag_session, ["E003"])[0].as_dict()
    assert set(payload) >= {
        "capability_id", "capability_name", "coverage", "modules",
        "retrieval_context", "explanation",
    }
    assert "query_terms" in payload["retrieval_context"]
