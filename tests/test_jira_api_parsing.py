from dataclasses import dataclass
from backend.ingestion.jira.jira_extractor import (
    map_jira_issue,
    extract_jira_issue_event,
    extract_jira_issue_events,
)


@dataclass
class MockJiraRecord:
    source_native_id: str
    payload: dict


def test_map_jira_issue_synthetic_flat_format():
    """Verify mapping of flat format (data/raw/jira/issues.json)."""
    raw = {
        "jira_id": "PAY-101",
        "reporter_id": "E001",
        "assignee_id": "E002",
        "timestamp": "2026-05-01T08:30:00Z",
        "updated_at": "2026-05-05T17:00:00Z",
        "issue_type": "Story",
        "summary": "Gateway router",
        "description": "Router implementation",
        "status": "Done",
        "components": ["api-gateway"],
    }
    mapped = map_jira_issue(raw)
    assert mapped["jira_id"] == "PAY-101"
    assert mapped["reporter_id"] == "E001"
    assert mapped["assignee_id"] == "E002"
    assert mapped["summary"] == "Gateway router"
    assert mapped["status"] == "Done"
    assert mapped["components"] == ["api-gateway"]


def test_map_jira_issue_rest_api_format():
    """Verify mapping of live Jira Cloud / Server REST API response."""
    rest_payload = {
        "id": "10052",
        "key": "PAY-200",
        "fields": {
            "summary": "Implement Fraud Detection Service",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Build rule evaluation pipeline."},
                            {"type": "text", "text": "Include velocity checks."}
                        ]
                    }
                ]
            },
            "issuetype": {"name": "Task", "id": "3"},
            "status": {"name": "In Progress", "id": "10001"},
            "created": "2026-06-01T10:00:00.000+0000",
            "updated": "2026-06-02T14:30:00.000+0000",
            "reporter": {"displayName": "Alice Admin", "accountId": "acc-001"},
            "assignee": {"displayName": "Bob Builder", "accountId": "acc-002"},
            "components": [{"name": "fraud-detection", "id": "c1"}],
            "labels": ["security", "q2-initiative"],
        }
    }
    mapped = map_jira_issue(rest_payload)
    assert mapped["jira_id"] == "PAY-200"
    assert mapped["reporter_id"] == "Alice Admin"
    assert mapped["assignee_id"] == "Bob Builder"
    assert mapped["issue_type"] == "Task"
    assert mapped["summary"] == "Implement Fraud Detection Service"
    assert "Build rule evaluation pipeline" in mapped["description"]
    assert "velocity checks" in mapped["description"]
    assert mapped["status"] == "In Progress"
    assert mapped["components"] == ["fraud-detection"]
    assert mapped["labels"] == ["security", "q2-initiative"]

    event = extract_jira_issue_event(rest_payload)
    assert event is not None
    assert event["employee_id"] == "Bob Builder"
    assert event["source"] == "jira"
    assert event["source_type"] == "issue"
    assert event["source_record_id"] == "PAY-200"
    assert event["action"] == "manage_jira_issue"
    assert event["provenance_type"] == "Proposed"
    assert event["context"]["summary"] == "Implement Fraud Detection Service"
    assert event["context"]["status"] == "In Progress"
    assert event["context"]["components"] == ["fraud-detection"]


def test_map_jira_record_dataclass():
    """Verify mapping of JiraRecord dataclass produced by JiraAdapter."""
    record = MockJiraRecord(
        source_native_id="PAY-300",
        payload={
            "key": "PAY-300",
            "fields": {
                "summary": "Ledger reconciliation bug fix",
                "description": "Fixed balance calculation mismatch",
                "status": {"name": "Done"},
                "issuetype": {"name": "Bug"},
                "assignee": {"name": "E003"},
                "reporter": {"name": "E001"},
                "components": ["reconciliation-engine"],
            }
        }
    )
    event = extract_jira_issue_event(record)
    assert event is not None
    assert event["source_record_id"] == "PAY-300"
    assert event["employee_id"] == "E003"
    assert event["context"]["summary"] == "Ledger reconciliation bug fix"
    assert event["context"]["description"] == "Fixed balance calculation mismatch"
    assert event["context"]["status"] == "Done"
