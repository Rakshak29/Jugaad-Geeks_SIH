import json
from pathlib import Path
from backend.ingestion.jira.jira_extractor import extract_jira_issue_event, extract_jira_issue_events

DATA_RAW_JIRA_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "jira" / "issues.json"


def test_valid_jira_issue_extraction():
    """Verify that a valid raw Jira issue record produces expected normalized event."""
    raw_jira = {
        "jira_id": "PAY-101",
        "reporter_id": "E001",
        "assignee_id": "E001",
        "timestamp": "2026-05-01T08:30:00Z",
        "updated_at": "2026-05-05T17:00:00Z",
        "issue_type": "Story",
        "summary": "Implement AcmePay API Gateway v2 routing layer",
        "description": "Design and implement API router for handling high throughput payment intents.",
        "status": "Done",
        "components": ["api-gateway"]
    }

    event = extract_jira_issue_event(raw_jira)
    assert event is not None
    assert event["employee_id"] == "E001"
    assert event["source"] == "jira"
    assert event["source_type"] == "issue"
    assert event["source_record_id"] == "PAY-101"
    assert event["action"] == "manage_jira_issue"
    assert event["timestamp"] == "2026-05-01T08:30:00Z"
    assert event["provenance_type"] == "Proposed"
    assert event["context"]["reporter_id"] == "E001"
    assert event["context"]["assignee_id"] == "E001"
    assert event["context"]["summary"] == "Implement AcmePay API Gateway v2 routing layer"
    assert event["context"]["status"] == "Done"
    assert event["context"]["components"] == ["api-gateway"]


def test_missing_employee():
    """Verify that a Jira issue record with missing assignee and reporter returns None."""
    raw_jira_none = {
        "jira_id": "PAY-999",
        "reporter_id": None,
        "assignee_id": None,
        "timestamp": "2026-05-01T08:30:00Z",
        "summary": "Unowned issue",
        "status": "To Do"
    }
    raw_jira_blank = {
        "jira_id": "PAY-998",
        "reporter_id": "   ",
        "assignee_id": "",
        "timestamp": "2026-05-01T08:30:00Z",
        "summary": "Blank owner issue",
        "status": "To Do"
    }

    assert extract_jira_issue_event(raw_jira_none) is None
    assert extract_jira_issue_event(raw_jira_blank) is None


def test_missing_jira_id():
    """Verify that a Jira issue record with missing or empty jira_id returns None."""
    raw_jira_none = {
        "jira_id": None,
        "reporter_id": "E001",
        "assignee_id": "E001",
        "timestamp": "2026-05-01T08:30:00Z",
        "summary": "Issue without ID",
        "status": "Done"
    }
    raw_jira_empty = {
        "jira_id": "",
        "reporter_id": "E001",
        "assignee_id": "E001",
        "timestamp": "2026-05-01T08:30:00Z",
        "summary": "Issue with empty ID",
        "status": "Done"
    }

    assert extract_jira_issue_event(raw_jira_none) is None
    assert extract_jira_issue_event(raw_jira_empty) is None


def test_source_id_preservation():
    """Verify that original jira_id is preserved as source_record_id."""
    raw_jira = {
        "jira_id": "CUSTOM-JIRA-555",
        "reporter_id": "E003",
        "assignee_id": "E003",
        "timestamp": "2026-04-05T09:30:00Z",
        "summary": "Custom Jira test",
        "status": "Done",
        "components": ["database-recovery"]
    }

    event = extract_jira_issue_event(raw_jira)
    assert event is not None
    assert event["source_record_id"] == "CUSTOM-JIRA-555"


def test_batch_extraction_from_raw_json():
    """Verify batch extraction on existing data/raw/jira/issues.json dataset (16 issues)."""
    with open(DATA_RAW_JIRA_FILE, "r", encoding="utf-8") as f:
        raw_jiras = json.load(f)

    events = extract_jira_issue_events(raw_jiras)
    assert len(events) == 16

    for event in events:
        assert event["source"] == "jira"
        assert event["source_type"] == "issue"
        assert event["employee_id"] in {"E001", "E002", "E003", "E004", "E005"}
        assert event["provenance_type"] == "Proposed"
        assert event["action"] == "manage_jira_issue"
        assert event["source_record_id"].startswith("PAY-")
        assert "summary" in event["context"]
        assert "status" in event["context"]
