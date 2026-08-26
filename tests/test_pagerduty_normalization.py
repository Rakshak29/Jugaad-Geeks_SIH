"""
Unit test suite for Step 5: Compact PagerDuty Incident Normalization & Internal E01-E20 Identity Resolution.

Verifies:
A. 15 raw incidents -> 15 normalized compact evidence event records
B. PagerDuty assignee (Rakshak Shetty / PN8AFPT) is NOT used as employee_id when internal lead_responder_id (E01-E20) is present
C. An incident with PagerDuty assignee Rakshak Shetty but lead_responder_id E03 resolves employee_id='E03' and employee_name='Kshitij Naidu'
D. Source, source_type, source_record_id, action, timestamp, provenance_type conform strictly to schema
E. Missing optional fields are handled safely
F. Malformed raw data is rejected safely
G. Successful normalization overwrites previous normalized dataset
H. Failed normalization does NOT overwrite previous valid normalized dataset
I. Raw PagerDuty data remains 100% unchanged
"""

import os
import json
import pytest

from backend.ingestion.pagerduty.normalizer import (
    normalize_pagerduty_incident,
    normalize_pagerduty_dataset,
    load_employee_mappings,
    resolve_canonical_identities,
    PagerDutyNormalizationError
)
from backend.ingestion.pagerduty.storage import save_raw_pagerduty_incidents

RAW_PAGERDUTY_FILE = "data/raw/pagerduty/incidents.json"
BLUEPRINT_PATH = "data/synthetic/blueprint.yaml"


@pytest.fixture
def temp_paths(tmp_path):
    """Fixture providing isolated temporary raw and normalized file paths."""
    raw_path = str(tmp_path / "raw" / "incidents.json")
    norm_path = str(tmp_path / "normalized" / "incidents.json")
    return raw_path, norm_path


def test_pd_assignee_vs_lead_responder_e03_resolution(temp_paths):
    """
    CRITICAL BUG CATCH TEST:
    A PagerDuty incident whose PagerDuty assignee is Rakshak Shetty (PN8AFPT)
    but whose lead_responder_id is E03 MUST NOT normalize its canonical employee
    identity to Rakshak Shetty. It must resolve employee_id='E03' and employee_name='Kshitij Naidu'.
    """
    raw_path, norm_path = temp_paths
    
    raw_incident = {
        "id": "Q0BR6INWL2DY4T",
        "incident_number": 12,
        "title": "Prometheus latency alert manager rule evaluation failure",
        "status": "triggered",
        "urgency": "high",
        "created_at": "2026-08-26T19:04:37Z",
        "service": {"id": "PK9U7OK", "name": "AcmePay"},
        "assignments": [
            {
                "at": "2026-08-26T19:04:37Z",
                "assignee": {
                    "id": "PN8AFPT",
                    "name": "Rakshak Shetty",
                    "email": "rakshak.s@somaiya.edu"
                }
            }
        ],
        "first_trigger_log_entry": {
            "channel": {
                "details": {
                    "incident_id": "INC-512",
                    "lead_responder": "E03",
                    "lead_responder_id": "E03",
                    "reporter": "E18",
                    "reporter_id": "E18",
                    "participants": ["E03", "E06", "E18"],
                    "service": "incident-response"
                }
            }
        }
    }
    
    save_raw_pagerduty_incidents("PK9U7OK", "https://example.com", [raw_incident], output_filepath=raw_path)
    normalize_pagerduty_dataset(raw_filepath=raw_path, output_filepath=norm_path)

    with open(norm_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    assert len(events) == 1
    event = events[0]

    # MUST NOT be Rakshak Shetty
    assert event["employee_id"] != "PN8AFPT"
    assert event["employee_id"] != "Rakshak Shetty"
    
    # MUST be E03 -> Kshitij Naidu
    assert event["employee_id"] == "E03"
    assert event["employee_name"] == "Kshitij Naidu"
    assert event["context"]["reporter_id"] == "E18"
    assert event["context"]["reporter_name"] == "Varun Saxena"
    assert "participants" not in event["context"]
    assert "participant_names" not in event["context"]


def test_15_raw_to_15_normalized_compact_schema(temp_paths):
    """Test 15 raw incidents produce 15 compact normalized evidence records with correct E01-E20 IDs."""
    raw_path, norm_path = temp_paths
    
    raw_incidents = [
        {
            "id": f"P10{idx:02d}",
            "incident_number": idx + 1,
            "title": f"Incident Title {idx+1}",
            "status": "triggered",
            "urgency": "high",
            "created_at": f"2026-08-26T19:0{idx:02d}:00Z",
            "service": {"id": "PK9U7OK", "name": "AcmePay"},
            "assignments": [
                {
                    "assignee": {
                        "id": "PN8AFPT",
                        "name": "Rakshak Shetty",
                        "email": "rakshak.s@somaiya.edu"
                    }
                }
            ],
            "first_trigger_log_entry": {
                "channel": {
                    "details": {
                        "lead_responder_id": "E08",
                        "reporter_id": "E01",
                        "participants": ["E08", "E02"]
                    }
                }
            }
        }
        for idx in range(15)
    ]
    url = "https://acmepay.pagerduty.com/service-directory/PK9U7OK/activity"
    save_raw_pagerduty_incidents("PK9U7OK", url, raw_incidents, output_filepath=raw_path)

    # Execute normalization
    result_path = normalize_pagerduty_dataset(raw_filepath=raw_path, output_filepath=norm_path)
    assert os.path.exists(norm_path)
    assert result_path == os.path.abspath(norm_path)

    with open(norm_path, "r", encoding="utf-8") as f:
        norm_events = json.load(f)

    assert isinstance(norm_events, list)
    assert len(norm_events) == 15

    for idx, event in enumerate(norm_events):
        assert event["employee_id"] == "E08"
        assert event["employee_name"] == "Vikram Malhotra"
        assert event["source"] == "pagerduty"
        assert event["source_type"] == "incident"
        assert event["source_record_id"] == f"P10{idx:02d}"
        assert event["action"] == "lead_incident_response"
        assert event["provenance_type"] == "Demonstrated"


def test_malformed_raw_data_rejected(temp_paths):
    """Test: Malformed raw data is safely rejected with PagerDutyNormalizationError."""
    raw_path, norm_path = temp_paths
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("{invalid_json: true")

    with pytest.raises(PagerDutyNormalizationError):
        normalize_pagerduty_dataset(raw_filepath=raw_path, output_filepath=norm_path)


def test_successful_normalization_overwrites_previous(temp_paths):
    """Test: Successful normalization overwrites previous normalized dataset completely (NO APPEND)."""
    raw_path, norm_path = temp_paths

    raw1 = [{"id": f"P10{i}", "title": f"Service 1 Inc {i}"} for i in range(2)]
    save_raw_pagerduty_incidents("SVC01", "https://example.com/SVC01", raw1, output_filepath=raw_path)
    normalize_pagerduty_dataset(raw_filepath=raw_path, output_filepath=norm_path)

    with open(norm_path, "r", encoding="utf-8") as f:
        norm1 = json.load(f)
    assert len(norm1) == 2

    raw2 = [{"id": f"P20{i}", "title": f"Service 2 Inc {i}"} for i in range(3)]
    save_raw_pagerduty_incidents("SVC02", "https://example.com/SVC02", raw2, output_filepath=raw_path)
    normalize_pagerduty_dataset(raw_filepath=raw_path, output_filepath=norm_path)

    with open(norm_path, "r", encoding="utf-8") as f:
        norm2 = json.load(f)
    assert len(norm2) == 3

    ids = [i["source_record_id"] for i in norm2]
    assert "P100" not in ids
    assert "P200" in ids


def test_failed_normalization_preserves_previous_file(temp_paths):
    """Test: Failed normalization does NOT overwrite previous valid normalized file."""
    raw_path, norm_path = temp_paths

    raw_valid = [{"id": "P500", "title": "Valid Inc"}]
    save_raw_pagerduty_incidents("SVC_VALID", "https://example.com/VALID", raw_valid, output_filepath=raw_path)
    normalize_pagerduty_dataset(raw_filepath=raw_path, output_filepath=norm_path)

    with open(raw_path, "w", encoding="utf-8") as f:
        f.write('{"source_url": "broken", "incidents": "not_a_list"}')

    with pytest.raises(PagerDutyNormalizationError):
        normalize_pagerduty_dataset(raw_filepath=raw_path, output_filepath=norm_path)

    with open(norm_path, "r", encoding="utf-8") as f:
        stored = json.load(f)
    assert len(stored) == 1
    assert stored[0]["source_record_id"] == "P500"


def test_raw_data_unmodified_by_normalization(temp_paths):
    """Test: Raw PagerDuty dataset file remains 100% unmodified during normalization."""
    raw_path, norm_path = temp_paths

    raw_data_content = {
        "source_url": "https://acmepay.pagerduty.com/service-directory/PK9U7OK/activity",
        "service_id": "PK9U7OK",
        "total_incidents": 1,
        "incidents": [{"id": "P888", "title": "Raw Integrity Check"}]
    }
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data_content, f, indent=2)

    with open(raw_path, "r", encoding="utf-8") as f:
        before_text = f.read()

    normalize_pagerduty_dataset(raw_filepath=raw_path, output_filepath=norm_path)

    with open(raw_path, "r", encoding="utf-8") as f:
        after_text = f.read()

    assert before_text == after_text
