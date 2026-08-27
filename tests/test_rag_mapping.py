# tests/test_rag_mapping.py
"""Deriving Confluence -> taxonomy mappings from API metadata alone."""

from backend.rag.mapping import store as mapping_store
from backend.rag.mapping.derive import (
    AMBIGUOUS,
    AUTO,
    UNMATCHED,
    PageMapper,
    SpaceMatch,
    build_label_module_rules,
    derive_space_service,
    normalize_slug,
)


def test_normalize_slug_matches_confluence_label_shape():
    assert normalize_slug("API Gateway") == "api-gateway"
    assert normalize_slug("Database Recovery") == "database-recovery"
    assert normalize_slug("  Deployment & Rollback  ") == "deployment-rollback"
    assert normalize_slug("") == ""


def test_label_rules_come_from_jira_component_and_module_name(rag_session):
    rules = build_label_module_rules(rag_session)
    # jira_component in modules.json
    assert rules["database-recovery"].module_id == "M003"
    # normalized module name
    assert rules["api-gateway"].module_id == "M001"
    # curated alias reused from the existing ingestion mapper
    assert "acmepay-db" in rules


def test_label_resolves_page_to_capability(rag_session):
    mapper = PageMapper(rag_session)
    links = mapper.resolve(labels=["database-recovery"], ancestor_titles=[], space_key="ANY")
    assert [l.capability_id for l in links] == ["C003"]
    assert links[0].match_type == "label"
    assert "jira_component" in links[0].evidence[0]


def test_ancestor_title_resolves_page_to_capability(rag_session):
    mapper = PageMapper(rag_session)
    links = mapper.resolve(labels=[], ancestor_titles=["Database Recovery"], space_key="ANY")
    assert [l.capability_id for l in links] == ["C003"]
    assert links[0].match_type == "ancestor"


def test_space_only_applies_when_nothing_explicit_matched(rag_session):
    """
    A space maps to a whole service, so it must not add capabilities to a page
    the author already labelled -- otherwise a rollback runbook filed under
    Payments comes back as Payment Reconciliation documentation.
    """
    mapper = PageMapper(rag_session, space_service={"DEPLOY": "S003"})

    labelled = mapper.resolve(labels=["api-gateway"], ancestor_titles=[], space_key="DEPLOY")
    assert [l.capability_id for l in labelled] == ["C001"]
    assert all(l.match_type == "label" for l in labelled)

    unlabelled = mapper.resolve(labels=[], ancestor_titles=[], space_key="DEPLOY")
    assert [l.capability_id for l in unlabelled] == ["C005"]
    assert unlabelled[0].match_type == "space"


def test_unknown_labels_resolve_to_nothing(rag_session):
    mapper = PageMapper(rag_session)
    assert mapper.resolve(labels=["lunch-menu"], ancestor_titles=[], space_key="GEN") == []


def test_space_matches_service_by_name_overlap(rag_session):
    match = derive_space_service(
        "DBOPS", "Database Operations",
        "Database reliability, recovery and data integrity runbooks.",
        rag_session,
    )
    assert match.status == AUTO
    assert match.service_id == "S002"
    assert match.reasons


def test_space_with_no_overlap_is_unmatched_not_guessed(rag_session):
    match = derive_space_service("GEN", "General", "Team notes.", rag_session)
    assert match.status == UNMATCHED
    assert match.service_id is None


def test_manual_decision_survives_a_later_sync(tmp_path):
    path = tmp_path / "mapping.json"

    mapping = mapping_store.merge_space_matches(
        {"spaces": {}},
        [SpaceMatch(space_key="PLAT", space_name="Platform", service_id=None, status=AMBIGUOUS)],
    )
    mapping_store.save_mapping(mapping, path)
    assert mapping_store.unresolved_spaces(mapping)[0]["space_key"] == "PLAT"

    mapping_store.set_manual("PLAT", "S003", path)

    # A later sync re-derives the same ambiguity; the human's answer must win.
    reloaded = mapping_store.load_mapping(path)
    merged = mapping_store.merge_space_matches(
        reloaded,
        [SpaceMatch(space_key="PLAT", space_name="Platform", service_id=None, status=AMBIGUOUS)],
    )
    assert mapping_store.resolved_space_service(merged) == {"PLAT": "S003"}
    assert mapping_store.unresolved_spaces(merged) == []


def test_manual_null_mapping_stops_a_space_being_reflagged(tmp_path):
    """'This space maps to nothing' is a real answer, not an unresolved one."""
    path = tmp_path / "mapping.json"
    mapping_store.set_manual("HR", None, path)
    mapping = mapping_store.load_mapping(path)
    assert mapping_store.unresolved_spaces(mapping) == []
    assert "HR" not in mapping_store.resolved_space_service(mapping)
