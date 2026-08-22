import json
from pathlib import Path
from backend.ingestion.documentation.documentation_extractor import (
    extract_documentation_event,
    extract_documentation_events,
)

DATA_RAW_DOCS_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "documentation" / "docs.json"


def test_valid_runbook_extraction():
    """Verify that a valid raw runbook document produces expected normalized evidence event."""
    raw_doc = {
        "doc_id": "DOC-601",
        "author_id": "E003",
        "last_modified_by": "E003",
        "created_at": "2026-04-16T10:00:00Z",
        "updated_at": "2026-05-11T09:00:00Z",
        "doc_type": "Runbook",
        "title": "PostgreSQL Database Point-In-Time Recovery (PITR) & Disaster Recovery Runbook",
        "service": "acmepay-db",
        "content_summary": "Step-by-step operational instructions for restoring PostgreSQL primary DB.",
        "filepath": "docs/runbooks/db_disaster_recovery.md"
    }

    event = extract_documentation_event(raw_doc)
    assert event is not None
    assert event["employee_id"] == "E003"
    assert event["source"] == "documentation"
    assert event["source_type"] == "document"
    assert event["source_record_id"] == "DOC-601"
    assert event["action"] == "author_documentation"
    assert event["timestamp"] == "2026-05-11T09:00:00Z"
    assert event["provenance_type"] == "Demonstrated"
    assert event["context"]["title"] == "PostgreSQL Database Point-In-Time Recovery (PITR) & Disaster Recovery Runbook"
    assert event["context"]["doc_type"] == "Runbook"
    assert event["context"]["document_type"] == "Runbook"
    assert event["context"]["service"] == "acmepay-db"
    assert event["context"]["filepath"] == "docs/runbooks/db_disaster_recovery.md"
    assert event["context"]["content"] == "Step-by-step operational instructions for restoring PostgreSQL primary DB."


def test_valid_architecture_doc_extraction():
    """Verify that an Architecture RFC document produces a valid normalized evidence event."""
    raw_doc = {
        "doc_id": "DOC-603",
        "author_id": "E001",
        "created_at": "2026-04-28T09:00:00Z",
        "updated_at": "2026-05-03T16:00:00Z",
        "doc_type": "Architecture RFC",
        "title": "AcmePay High-Throughput API Gateway Architecture v2",
        "service": "acmepay-api",
        "content_summary": "Architecture RFC defining v2 intent routing.",
        "filepath": "docs/architecture/api_gateway_v2_design.md"
    }

    event = extract_documentation_event(raw_doc)
    assert event is not None
    assert event["employee_id"] == "E001"
    assert event["provenance_type"] == "Demonstrated"
    assert event["context"]["doc_type"] == "Architecture RFC"
    assert event["context"]["document_type"] == "Architecture RFC"


def test_valid_design_decision_extraction():
    """Verify that a Design Doc produces a valid normalized evidence event."""
    raw_doc = {
        "doc_id": "DOC-606",
        "author_id": "E005",
        "created_at": "2026-05-26T13:00:00Z",
        "updated_at": "2026-06-07T10:00:00Z",
        "doc_type": "Design Doc",
        "title": "Merchant Chargeback & Dispute Settlement Design",
        "service": "acmepay-reconciliation",
        "content_summary": "Technical design doc for matching dispute transaction events.",
        "filepath": "docs/architecture/dispute_settlement_design.md"
    }

    event = extract_documentation_event(raw_doc)
    assert event is not None
    assert event["employee_id"] == "E005"
    assert event["provenance_type"] == "Demonstrated"
    assert event["context"]["doc_type"] == "Design Doc"


def test_missing_doc_id():
    """Verify that a document record missing doc_id returns None."""
    raw_doc_none = {
        "doc_id": None,
        "author_id": "E003",
        "title": "Untitled"
    }
    raw_doc_empty = {
        "doc_id": "",
        "author_id": "E003",
        "title": "Untitled"
    }

    assert extract_documentation_event(raw_doc_none) is None
    assert extract_documentation_event(raw_doc_empty) is None


def test_missing_author():
    """Verify that a document record missing author_id returns None."""
    raw_doc_none = {
        "doc_id": "DOC-601",
        "author_id": None,
        "title": "Orphaned Document"
    }
    raw_doc_blank = {
        "doc_id": "DOC-602",
        "author_id": "   ",
        "title": "Blank Author Document"
    }

    assert extract_documentation_event(raw_doc_none) is None
    assert extract_documentation_event(raw_doc_blank) is None


def test_source_id_preservation():
    """Verify that original doc_id is preserved as source_record_id."""
    raw_doc = {
        "doc_id": "CUSTOM-DOC-888",
        "author_id": "E004",
        "title": "Custom Runbook",
        "created_at": "2026-05-05T14:00:00Z"
    }

    event = extract_documentation_event(raw_doc)
    assert event is not None
    assert event["source_record_id"] == "CUSTOM-DOC-888"


def test_timestamp_preservation():
    """Verify that timestamp prefers updated_at and falls back to created_at."""
    raw_doc_updated = {
        "doc_id": "DOC-101",
        "author_id": "E001",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z"
    }
    raw_doc_created_only = {
        "doc_id": "DOC-102",
        "author_id": "E001",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": None
    }

    assert extract_documentation_event(raw_doc_updated)["timestamp"] == "2026-02-01T00:00:00Z"
    assert extract_documentation_event(raw_doc_created_only)["timestamp"] == "2026-01-01T00:00:00Z"


def test_provenance_type_demonstrated():
    """Explicitly verify that authored documentation produces Demonstrated provenance_type."""
    raw_doc = {
        "doc_id": "DOC-601",
        "author_id": "E003",
        "title": "PostgreSQL DR Runbook"
    }

    event = extract_documentation_event(raw_doc)
    assert event is not None
    assert event["provenance_type"] == "Demonstrated"


def test_batch_extraction_from_raw_json():
    """Verify batch extraction on existing data/raw/documentation/docs.json dataset (6 documents)."""
    with open(DATA_RAW_DOCS_FILE, "r", encoding="utf-8") as f:
        raw_docs = json.load(f)

    events = extract_documentation_events(raw_docs)
    assert len(events) == 6

    for event in events:
        assert event["source"] == "documentation"
        assert event["source_type"] == "document"
        assert event["employee_id"] in {"E001", "E002", "E003", "E004", "E005"}
        assert event["provenance_type"] == "Demonstrated"
        assert event["action"] == "author_documentation"
        assert event["source_record_id"].startswith("DOC-")
        assert "title" in event["context"]
        assert "doc_type" in event["context"]
