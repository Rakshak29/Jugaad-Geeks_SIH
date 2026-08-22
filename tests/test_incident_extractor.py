import json
from pathlib import Path
from backend.ingestion.incidents.incident_extractor import (
    extract_incident_events,
    extract_batch_incident_events,
)

DATA_RAW_INCIDENT_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "incidents" / "incidents.json"


def test_single_incident_produces_multiple_events():
    """Verify that a single raw incident with multiple employee actions produces multiple normalized evidence events."""
    raw_incident = {
        "incident_id": "INC-401",
        "reporter_id": "E004",
        "lead_responder_id": "E003",
        "participants": [
            "E003",
            "E004"
        ],
        "timestamp": "2026-05-10T02:15:00Z",
        "resolved_at": "2026-05-10T03:30:00Z",
        "title": "PostgreSQL master node storage corruption and table lock",
        "severity": "SEV-1",
        "service": "acmepay-db",
        "summary": "Database disk array failure caused table corruption on transaction primary node.",
        "root_cause": "Hardware disk failure on primary DB node.",
        "action_items": [
            "Executed WAL restore script pitr_restore.go to point-in-time recovery",
            "Verified transaction table consistency",
            "Updated DB failover runbook"
        ]
    }

    events = extract_incident_events(raw_incident)
    # Asserts INC-401 produces 2 separate events (E003 lead responder + E004 participant)
    assert len(events) == 2

    # Event 1: Lead Responder E003
    lead_event = events[0]
    assert lead_event["employee_id"] == "E003"
    assert lead_event["source"] == "incidents"
    assert lead_event["source_type"] == "incident"
    assert lead_event["source_record_id"] == "INC-401"
    assert lead_event["action"] == "lead_incident_response"
    assert lead_event["timestamp"] == "2026-05-10T02:15:00Z"
    assert lead_event["provenance_type"] == "Demonstrated"
    assert lead_event["context"]["role"] == "lead_responder"
    assert lead_event["context"]["title"] == "PostgreSQL master node storage corruption and table lock"
    assert lead_event["context"]["severity"] == "SEV-1"
    assert lead_event["context"]["service"] == "acmepay-db"
    assert len(lead_event["context"]["action_items"]) == 3

    # Event 2: Participant E004
    part_event = events[1]
    assert part_event["employee_id"] == "E004"
    assert part_event["source"] == "incidents"
    assert part_event["source_type"] == "incident"
    assert part_event["source_record_id"] == "INC-401"
    assert part_event["action"] == "participate_incident_response"
    assert part_event["timestamp"] == "2026-05-10T02:15:00Z"
    assert part_event["provenance_type"] == "Demonstrated"
    assert part_event["context"]["role"] == "participant"


def test_reporter_only_event_creation():
    """Verify that a reporter who is neither lead nor participant gets a report_incident event."""
    raw_incident = {
        "incident_id": "INC-403",
        "reporter_id": "E002",
        "lead_responder_id": "E005",
        "participants": [
            "E005",
            "E004"
        ],
        "timestamp": "2026-06-03T19:00:00Z",
        "title": "Merchant payout webhook delivery failure backlog",
        "severity": "SEV-2",
        "service": "acmepay-api"
    }

    events = extract_incident_events(raw_incident)
    # E005 (lead), E004 (participant), E002 (reporter) -> 3 events
    assert len(events) == 3

    employees = [e["employee_id"] for e in events]
    assert employees == ["E005", "E004", "E002"]

    reporter_event = events[2]
    assert reporter_event["employee_id"] == "E002"
    assert reporter_event["action"] == "report_incident"
    assert reporter_event["provenance_type"] == "Observed"
    assert reporter_event["context"]["role"] == "reporter"


def test_missing_incident_id_returns_empty():
    """Verify that an incident record missing incident_id returns an empty list."""
    raw_incident_none = {
        "incident_id": None,
        "lead_responder_id": "E003",
        "participants": ["E003"]
    }
    raw_incident_empty = {
        "incident_id": "",
        "lead_responder_id": "E003",
        "participants": ["E003"]
    }

    assert extract_incident_events(raw_incident_none) == []
    assert extract_incident_events(raw_incident_empty) == []


def test_missing_employees_returns_empty():
    """Verify that an incident with no lead, participants, or reporter returns an empty list."""
    raw_incident = {
        "incident_id": "INC-999",
        "lead_responder_id": None,
        "participants": [],
        "reporter_id": "  "
    }
    assert extract_incident_events(raw_incident) == []


def test_source_id_preservation():
    """Verify that original incident_id is preserved in all created evidence events."""
    raw_incident = {
        "incident_id": "CUSTOM-INC-777",
        "lead_responder_id": "E003",
        "participants": ["E003", "E004"],
        "timestamp": "2026-05-10T02:15:00Z"
    }

    events = extract_incident_events(raw_incident)
    assert len(events) == 2
    for event in events:
        assert event["source_record_id"] == "CUSTOM-INC-777"


def test_batch_extraction_from_raw_json():
    """Verify batch extraction on existing data/raw/incidents/incidents.json dataset (9 raw incidents -> 19 events)."""
    with open(DATA_RAW_INCIDENT_FILE, "r", encoding="utf-8") as f:
        raw_incidents = json.load(f)

    events = extract_batch_incident_events(raw_incidents)
    # 9 incidents produce 19 normalized evidence events total
    assert len(events) == 19

    for event in events:
        assert event["source"] == "incidents"
        assert event["source_type"] == "incident"
        assert event["employee_id"] in {"E001", "E002", "E003", "E004", "E005"}
        assert event["provenance_type"] in {"Demonstrated", "Observed"}
        assert event["action"] in {"lead_incident_response", "participate_incident_response", "report_incident"}
        assert event["source_record_id"].startswith("INC-")
        assert "title" in event["context"]
        assert "service" in event["context"]
