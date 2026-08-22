import json
from pathlib import Path
from backend.ingestion.github.issue_extractor import extract_issue_event, extract_issue_events

DATA_RAW_ISSUE_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "github" / "issues.json"


def test_valid_issue_extraction():
    """Verify that a valid raw GitHub issue record produces expected normalized event."""
    raw_issue = {
        "issue_id": "GH-ISSUE-301",
        "author_id": "E001",
        "assignee_id": "E002",
        "timestamp": "2026-05-01T09:00:00Z",
        "title": "Investigate idempotency key collisions under high concurrency",
        "description": "Redis lock timeout might cause intermittent 409 responses.",
        "status": "CLOSED",
        "labels": ["bug", "api"]
    }

    event = extract_issue_event(raw_issue)
    assert event is not None
    assert event["employee_id"] == "E001"
    assert event["source"] == "github"
    assert event["source_type"] == "issue"
    assert event["source_record_id"] == "GH-ISSUE-301"
    assert event["action"] == "create_issue"
    assert event["timestamp"] == "2026-05-01T09:00:00Z"
    assert event["provenance_type"] == "Proposed"
    assert event["context"]["assignee_id"] == "E002"
    assert event["context"]["title"] == "Investigate idempotency key collisions under high concurrency"
    assert event["context"]["status"] == "CLOSED"
    assert event["context"]["labels"] == ["bug", "api"]


def test_missing_author():
    """Verify that an issue record with missing or empty author_id returns None."""
    raw_issue_none = {
        "issue_id": "GH-ISSUE-302",
        "author_id": None,
        "timestamp": "2026-05-15T10:30:00Z",
        "title": "Issue without author",
        "status": "OPEN",
        "labels": []
    }
    raw_issue_blank = {
        "issue_id": "GH-ISSUE-303",
        "author_id": "   ",
        "timestamp": "2026-05-15T10:30:00Z",
        "title": "Issue with blank author",
        "status": "OPEN",
        "labels": []
    }

    assert extract_issue_event(raw_issue_none) is None
    assert extract_issue_event(raw_issue_blank) is None


def test_missing_issue_id():
    """Verify that an issue record with missing or empty issue_id returns None."""
    raw_issue_none = {
        "issue_id": None,
        "author_id": "E001",
        "timestamp": "2026-05-15T10:30:00Z",
        "title": "Issue without ID",
        "status": "OPEN",
        "labels": []
    }
    raw_issue_empty = {
        "issue_id": "",
        "author_id": "E001",
        "timestamp": "2026-05-15T10:30:00Z",
        "title": "Issue with empty ID",
        "status": "OPEN",
        "labels": []
    }

    assert extract_issue_event(raw_issue_none) is None
    assert extract_issue_event(raw_issue_empty) is None


def test_source_id_preservation():
    """Verify that original issue_id is preserved as source_record_id."""
    raw_issue = {
        "issue_id": "CUSTOM-GH-ISSUE-999",
        "author_id": "E003",
        "timestamp": "2026-04-10T14:00:00Z",
        "title": "Custom issue test",
        "status": "CLOSED",
        "labels": ["database"]
    }

    event = extract_issue_event(raw_issue)
    assert event is not None
    assert event["source_record_id"] == "CUSTOM-GH-ISSUE-999"


def test_batch_extraction_from_raw_json():
    """Verify batch extraction on existing data/raw/github/issues.json dataset (12 issues)."""
    with open(DATA_RAW_ISSUE_FILE, "r", encoding="utf-8") as f:
        raw_issues = json.load(f)

    events = extract_issue_events(raw_issues)
    assert len(events) == 12

    for event in events:
        assert event["source"] == "github"
        assert event["source_type"] == "issue"
        assert event["employee_id"] in {"E001", "E002", "E003", "E004", "E005"}
        assert event["provenance_type"] == "Proposed"
        assert event["action"] == "create_issue"
        assert event["source_record_id"].startswith("GH-ISSUE-")
        assert "title" in event["context"]
        assert "status" in event["context"]
