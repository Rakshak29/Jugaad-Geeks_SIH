import json
from pathlib import Path
from backend.ingestion.deployments.deployment_extractor import (
    extract_deployment_event,
    extract_deployment_events,
)

DATA_RAW_DEPLOYMENT_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "deployments" / "deployments.json"


def test_valid_successful_deployment_extraction():
    """Verify that a valid raw deployment record produces expected normalized event."""
    raw_deployment = {
        "deployment_id": "DEP-501",
        "deployed_by": "E004",
        "timestamp": "2026-05-02T12:00:00Z",
        "environment": "production",
        "service": "acmepay-api",
        "action": "DEPLOY",
        "commit_hash": "c001a1",
        "status": "SUCCESS",
        "notes": "Deployed API v2 payment intent router."
    }

    event = extract_deployment_event(raw_deployment)
    assert event is not None
    assert event["employee_id"] == "E004"
    assert event["source"] == "deployments"
    assert event["source_type"] == "deployment"
    assert event["source_record_id"] == "DEP-501"
    assert event["action"] == "deploy_service"
    assert event["timestamp"] == "2026-05-02T12:00:00Z"
    assert event["provenance_type"] == "Demonstrated"
    assert event["context"]["service"] == "acmepay-api"
    assert event["context"]["environment"] == "production"
    assert event["context"]["action"] == "DEPLOY"
    assert event["context"]["commit_hash"] == "c001a1"
    assert event["context"]["status"] == "SUCCESS"
    assert event["context"]["notes"] == "Deployed API v2 payment intent router."
    assert event["context"]["reason"] == "Deployed API v2 payment intent router."


def test_rollback_extraction():
    """Verify that a rollback deployment record produces an evidence event with rollback action."""
    raw_deployment = {
        "deployment_id": "DEP-502",
        "deployed_by": "E004",
        "timestamp": "2026-05-22T14:25:00Z",
        "environment": "production",
        "service": "acmepay-api",
        "action": "ROLLBACK",
        "commit_hash": "c001a4",
        "status": "ROLLED_BACK",
        "notes": "Automated rollback triggered during INC-402 due to elevated 504 error rate."
    }

    event = extract_deployment_event(raw_deployment)
    assert event is not None
    assert event["employee_id"] == "E004"
    assert event["source"] == "deployments"
    assert event["source_type"] == "deployment"
    assert event["source_record_id"] == "DEP-502"
    assert event["action"] == "rollback_service"
    assert event["provenance_type"] == "Demonstrated"
    assert event["context"]["status"] == "ROLLED_BACK"
    assert event["context"]["action"] == "ROLLBACK"


def test_missing_deployment_id():
    """Verify that a deployment record missing deployment_id returns None."""
    raw_dep_none = {
        "deployment_id": None,
        "deployed_by": "E004",
        "timestamp": "2026-05-02T12:00:00Z",
        "service": "acmepay-api"
    }
    raw_dep_empty = {
        "deployment_id": "",
        "deployed_by": "E004",
        "timestamp": "2026-05-02T12:00:00Z",
        "service": "acmepay-api"
    }

    assert extract_deployment_event(raw_dep_none) is None
    assert extract_deployment_event(raw_dep_empty) is None


def test_missing_employee():
    """Verify that a deployment record missing deployed_by returns None."""
    raw_dep_none = {
        "deployment_id": "DEP-503",
        "deployed_by": None,
        "timestamp": "2026-05-02T12:00:00Z",
        "service": "acmepay-api"
    }
    raw_dep_blank = {
        "deployment_id": "DEP-504",
        "deployed_by": "   ",
        "timestamp": "2026-05-02T12:00:00Z",
        "service": "acmepay-api"
    }

    assert extract_deployment_event(raw_dep_none) is None
    assert extract_deployment_event(raw_dep_blank) is None


def test_source_id_preservation():
    """Verify that original deployment_id is preserved as source_record_id."""
    raw_deployment = {
        "deployment_id": "CUSTOM-DEP-999",
        "deployed_by": "E003",
        "timestamp": "2026-06-20T10:00:00Z",
        "environment": "staging",
        "service": "acmepay-db",
        "action": "DEPLOY",
        "status": "SUCCESS"
    }

    event = extract_deployment_event(raw_deployment)
    assert event is not None
    assert event["source_record_id"] == "CUSTOM-DEP-999"


def test_batch_extraction_from_raw_json():
    """Verify batch extraction on existing data/raw/deployments/deployments.json dataset (9 deployments)."""
    with open(DATA_RAW_DEPLOYMENT_FILE, "r", encoding="utf-8") as f:
        raw_deployments = json.load(f)

    events = extract_deployment_events(raw_deployments)
    assert len(events) == 9

    for event in events:
        assert event["source"] == "deployments"
        assert event["source_type"] == "deployment"
        assert event["employee_id"] in {"E002", "E003", "E004"}
        assert event["provenance_type"] == "Demonstrated"
        assert event["action"] in {"deploy_service", "rollback_service"}
        assert event["source_record_id"].startswith("DEP-")
        assert "service" in event["context"]
        assert "environment" in event["context"]
