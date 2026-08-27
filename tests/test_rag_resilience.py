# tests/test_rag_resilience.py
"""
The RAG must keep working when the rest of the project changes.

It reads the taxonomy, the evidence tables and parts of the scoring engine, so
ordinary work elsewhere -- adding a capability, adding an evidence source,
retuning the bands, refactoring a private engine helper -- must not break it or
silently degrade it.

Each test simulates one such change and asserts the RAG still behaves.
"""

import pytest
from sqlalchemy import Column, Integer, String, Text

from backend.database import Base
from backend.models.core import Capability, CapabilityScore, Employee, Module, Service
from backend.rag import compat
from backend.rag.confluence.sync import run_sync
from backend.rag.coverage.context import build_gap_contexts
from backend.rag.coverage.simulate import band_for_score, simulate_absence
from backend.rag.packaging.build import build_transfer_package
from backend.rag.retrieval.retrieve import KnowledgeIndex
from backend.rag.retrieval.vocabulary import build_vocabularies
from tests.test_rag_retrieval import FakeConfluenceClient


# --- taxonomy changes -------------------------------------------------------


def test_a_new_capability_is_picked_up_without_configuration(rag_session):
    """Adding a capability must not require touching the RAG."""
    capability = Capability(
        id="C009", name="Message Queue Operations",
        description="Operating and recovering Kafka topics and consumer groups.",
    )
    module = Module(id="M009", service_id="S003", name="Queue Platform",
                    description="Kafka brokers, topics and consumer group tooling.")
    module.capabilities.append(capability)
    rag_session.add_all([capability, module])
    rag_session.add(CapabilityScore(employee_id="E003", capability_id="C009",
                                    score=0.9, evidence_count=4))
    rag_session.commit()

    result = simulate_absence(rag_session, ["E003"])
    assert "C009" in {c.capability_id for c in result.capabilities}

    new_gap = next(c for c in result.gaps if c.capability_id == "C009")
    assert new_gap.band_after == "NONE"

    vocabularies = build_vocabularies(rag_session)
    assert "kafka" in vocabularies["C009"].terms


def test_a_new_module_creates_a_working_label_rule(rag_session):
    """A page labelled after a brand-new module resolves with no config."""
    capability = Capability(id="C009", name="Message Queue Operations", description="Kafka.")
    module = Module(id="M009", service_id="S003", name="Queue Platform", description="Kafka.")
    module.capabilities.append(capability)
    rag_session.add_all([capability, module])
    rag_session.commit()

    from backend.rag.mapping.derive import PageMapper

    links = PageMapper(rag_session).resolve(
        labels=["queue-platform"], ancestor_titles=[], space_key="ANY"
    )
    assert [l.capability_id for l in links] == ["C009"]


def test_removing_a_capability_does_not_break_retrieval(rag_session):
    """A capability deleted from the taxonomy must not orphan the pipeline."""
    run_sync(rag_session, client=FakeConfluenceClient())

    rag_session.query(CapabilityScore).filter_by(capability_id="C005").delete()
    rag_session.query(Capability).filter_by(id="C005").delete()
    rag_session.commit()

    result = simulate_absence(rag_session, ["E003"])
    assert "C005" not in {c.capability_id for c in result.capabilities}

    package = build_transfer_package(rag_session, ["E003"])
    assert package.gaps  # C003 is still a gap


# --- engine changes ---------------------------------------------------------


def test_bands_follow_a_retuned_engine_config(rag_session, monkeypatch):
    """
    If someone retunes the scoring engine's bands, the RAG must follow.

    This is why band_for_score delegates rather than restating the numbers.
    """
    from backend.engine.config import scoring_config

    monkeypatch.setattr(
        scoring_config, "BAND_THRESHOLDS",
        [("HIGH", 0.95), ("MODERATE", 0.90), ("LOW", 0.85), ("NONE", 0.0)],
    )
    monkeypatch.setattr(compat, "_engine_band_for_score", None)  # force the fallback path

    # 0.91 was HIGH under the default thresholds; under these it is MODERATE.
    assert band_for_score(0.91) == "MODERATE"
    assert band_for_score(0.5) == "NONE"


def test_the_rag_survives_a_renamed_private_engine_helper(rag_session, monkeypatch):
    """
    The engine's _tokenize / _keyword_overlap / _band_for_score are private.
    A refactor there must degrade the RAG, not break it.
    """
    monkeypatch.setattr(compat, "_engine_tokenize", None)
    monkeypatch.setattr(compat, "_engine_keyword_overlap", None)
    monkeypatch.setattr(compat, "_engine_band_for_score", None)

    assert compat.tokenize("Database Recovery runbook") >= {"database", "recovery", "runbook"}
    ratio, matched = compat.keyword_overlap({"wal", "restore"}, {"wal", "backup"})
    assert matched == ["wal"] and ratio > 0
    assert band_for_score(1.0) == "HIGH"

    run_sync(rag_session, client=FakeConfluenceClient())
    assert KnowledgeIndex(rag_session).retrieve_for_capability("C003").documents


def test_missing_label_aliases_still_leave_labels_working(rag_session, monkeypatch):
    """
    backend/mapper.py's curated aliases are a bonus, not the foundation.
    Without them, jira_component and module names still resolve labels.
    """
    monkeypatch.setattr(compat, "_engine_label_map", {})

    from backend.rag.mapping.derive import PageMapper

    links = PageMapper(rag_session).resolve(
        labels=["database-recovery"], ancestor_titles=[], space_key="ANY"
    )
    assert [l.capability_id for l in links] == ["C003"]


# --- evidence pipeline changes ---------------------------------------------


def test_a_new_evidence_source_feeds_the_vocabulary_automatically(rag_session):
    """
    The failure this guards against is silent.

    A new ingestion source writes an unfamiliar `source` value to
    evidence_records. Its text must still reach the search vocabulary --
    otherwise retrieval quietly gets worse with nothing in the logs.
    """
    from backend.models.core import EvidenceRecord
    from backend.models.raw import RawIncident
    from datetime import datetime, timezone

    rag_session.add(
        RawIncident(
            incident_id="PAGERDUTY-777", reporter_id="E003", lead_responder_id="E003",
            participants=[], timestamp=datetime.now(timezone.utc),
            title="Kafka consumer lag storm", severity="SEV1", service="queue",
            summary="Consumer group rebalanced repeatedly under partition skew.",
            root_cause="Zookeeper session expiry cascaded into a rebalance loop.",
        )
    )
    rag_session.add(
        EvidenceRecord(
            id="EV-NEWSRC", employee_id="E003", capability_id="C003", module_id="M003",
            source="pagerduty_alert",          # a source nobody registered
            source_ref="PAGERDUTY-777",
            event_date=datetime.now(timezone.utc), weight=1.0,
        )
    )
    rag_session.commit()

    terms = build_vocabularies(rag_session)["C003"].terms
    assert "zookeeper" in terms, "text from an unregistered source must still be mined"
    assert "rebalance" in terms


def test_a_new_column_on_a_raw_table_contributes_text(rag_session):
    """
    Raw rows are scanned by inspecting their columns, so a richer postmortem
    field starts feeding retrieval the moment someone adds it.
    """
    from backend.models.raw import RawIncident

    columns = {c.name for c in RawIncident.__table__.columns}
    assert {"summary", "root_cause"} <= columns

    from backend.rag.retrieval.vocabulary import _row_text
    from datetime import datetime, timezone

    row = RawIncident(
        incident_id="INC-1", reporter_id="E1", lead_responder_id="E1", participants=[],
        timestamp=datetime.now(timezone.utc), title="Outage", severity="SEV2",
        service="db", summary="Replication stalled.", root_cause="Disk exhaustion.",
    )
    text = _row_text(row, "incident_id")

    assert "Replication stalled." in text
    assert "Disk exhaustion." in text
    # Identifiers and bookkeeping must not pollute the vocabulary.
    assert "INC-1" not in text
    assert "SEV2" not in text


def test_no_evidence_at_all_still_produces_a_usable_query(rag_session):
    """A fresh deployment with no evidence yet must still retrieve."""
    from backend.models.core import EvidenceRecord

    rag_session.query(EvidenceRecord).delete()
    rag_session.commit()

    vocabulary = build_vocabularies(rag_session)["C003"]
    assert vocabulary.terms, "the taxonomy's own words must carry the query"
    assert "recovery" in vocabulary.terms

    run_sync(rag_session, client=FakeConfluenceClient())
    assert KnowledgeIndex(rag_session).retrieve_for_capability("C003").documents


# --- data-shape changes -----------------------------------------------------


def test_an_employee_with_no_scores_is_a_valid_absence(rag_session):
    rag_session.add(Employee(id="E099", name="New Joiner", role="Backend"))
    rag_session.commit()

    result = simulate_absence(rag_session, ["E099"])
    assert result.gaps == []  # nobody's coverage changed


def test_an_empty_score_table_reports_everything_as_a_gap(rag_session):
    """Before the engine has ever run, every capability is uncovered."""
    rag_session.query(CapabilityScore).delete()
    rag_session.commit()

    result = simulate_absence(rag_session, ["E003"])
    assert len(result.gaps) == len(result.capabilities)
    assert all(c.band_after == "NONE" for c in result.gaps)


def test_a_module_with_no_service_does_not_break_context(rag_session):
    capability = Capability(id="C009", name="Orphan Capability", description="No service.")
    module = Module(id="M009", service_id=None, name="Orphan Module", description="Detached.")
    module.capabilities.append(capability)
    rag_session.add_all([capability, module])
    rag_session.commit()

    contexts = build_gap_contexts(rag_session, ["E003"])
    orphan = next(c for c in contexts if c.capability_id == "C009")
    assert orphan.modules[0].service_name is None
