"""
Unit tests for Step 4: Raw PagerDuty Ingestion Storage & Overwrite Behavior.

Verifies:
A. First ingestion writes the raw JSON file.
B. Second ingestion with a different service/source replaces the previous dataset rather than appending.
C. Failed ingestion does not destroy the previous valid raw file.
D. Resulting stored JSON remains valid.
E. Existing Step 3 endpoint behavior remains intact.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.ingestion.pagerduty.storage import (
    save_raw_pagerduty_incidents,
    get_raw_pagerduty_incidents,
    RAW_PAGERDUTY_FILE
)
from backend.ingestion.pagerduty.client import PagerDutyClientError

client = TestClient(app)


@pytest.fixture
def temp_raw_file(tmp_path):
    """Fixture providing a temporary file path for raw PagerDuty JSON storage."""
    return str(tmp_path / "data" / "raw" / "pagerduty" / "incidents.json")


def test_first_ingestion_writes_raw_json(temp_raw_file):
    """Test A: First ingestion writes raw JSON file with metadata wrapper."""
    incidents_data = [
        {"id": "P1001", "summary": "First incident", "service": {"id": "SVC01"}}
    ]
    url = "https://acmepay.pagerduty.com/service-directory/SVC01/activity"
    
    written_path = save_raw_pagerduty_incidents("SVC01", url, incidents_data, output_filepath=temp_raw_file)
    assert os.path.exists(temp_raw_file)
    assert written_path == os.path.abspath(temp_raw_file)

    stored = get_raw_pagerduty_incidents(temp_raw_file)
    assert stored is not None
    assert stored["service_id"] == "SVC01"
    assert stored["source_url"] == url
    assert stored["total_incidents"] == 1
    assert len(stored["incidents"]) == 1
    assert stored["incidents"][0]["id"] == "P1001"


def test_second_ingestion_replaces_dataset(temp_raw_file):
    """Test B: Second ingestion with a different service replaces previous dataset (NO APPEND)."""
    # 1. First Ingestion (SVC01)
    incidents_svc1 = [
        {"id": "P1001", "summary": "First incident", "service": {"id": "SVC01"}}
    ]
    url1 = "https://acmepay.pagerduty.com/service-directory/SVC01/activity"
    save_raw_pagerduty_incidents("SVC01", url1, incidents_svc1, output_filepath=temp_raw_file)

    stored_first = get_raw_pagerduty_incidents(temp_raw_file)
    assert stored_first["service_id"] == "SVC01"
    assert stored_first["total_incidents"] == 1

    # 2. Second Ingestion with different service (SVC02)
    incidents_svc2 = [
        {"id": "P2001", "summary": "Second service incident A", "service": {"id": "SVC02"}},
        {"id": "P2002", "summary": "Second service incident B", "service": {"id": "SVC02"}}
    ]
    url2 = "https://acmepay.pagerduty.com/service-directory/SVC02/activity"
    save_raw_pagerduty_incidents("SVC02", url2, incidents_svc2, output_filepath=temp_raw_file)

    stored_second = get_raw_pagerduty_incidents(temp_raw_file)
    assert stored_second["service_id"] == "SVC02"
    assert stored_second["source_url"] == url2
    assert stored_second["total_incidents"] == 2
    assert len(stored_second["incidents"]) == 2
    
    # Confirm NO residual data from SVC01 remains
    all_ids = [i["id"] for i in stored_second["incidents"]]
    assert "P1001" not in all_ids
    assert "P2001" in all_ids
    assert "P2002" in all_ids


def test_failed_ingestion_preserves_previous_file(temp_raw_file):
    """Test C: Failed API ingestion preserves the previous valid raw file intact."""
    # 1. First valid save
    valid_incidents = [{"id": "P9999", "summary": "Existing valid incident"}]
    save_raw_pagerduty_incidents("SVC_VALID", "https://acmepay.pagerduty.com/service-directory/SVC_VALID/activity", valid_incidents, output_filepath=temp_raw_file)

    # 2. Simulate API endpoint failure
    with patch("backend.main.PagerDutyClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.get_incidents.side_effect = PagerDutyClientError("HTTP 401: Unauthorized API token")
        MockClient.return_value = mock_instance

        with patch("backend.main.save_raw_pagerduty_incidents") as mock_save:
            response = client.post(
                "/api/ingestion/pagerduty",
                json={
                    "pagerduty_url": "https://acmepay.pagerduty.com/service-directory/SVC_FAIL/activity",
                    "api_token": "invalid_token"
                }
            )
            assert response.status_code == 401
            # Verify save_raw_pagerduty_incidents was NEVER called
            mock_save.assert_not_called()

    # Confirm original file remains untouched
    stored = get_raw_pagerduty_incidents(temp_raw_file)
    assert stored["service_id"] == "SVC_VALID"
    assert stored["total_incidents"] == 1
    assert stored["incidents"][0]["id"] == "P9999"


def test_stored_json_validity(temp_raw_file):
    """Test D: The stored JSON remains valid and parses cleanly."""
    incidents = [{"id": "P555", "summary": "JSON Validity Test"}]
    save_raw_pagerduty_incidents("SVC_JSON", "https://acmepay.pagerduty.com/service-directory/SVC_JSON/activity", incidents, output_filepath=temp_raw_file)

    with open(temp_raw_file, "r") as f:
        parsed = json.load(f)
    assert isinstance(parsed, dict)
    assert "source_url" in parsed
    assert "service_id" in parsed
    assert "ingested_at" in parsed
    assert "incidents" in parsed


def test_endpoint_raw_storage_integration(tmp_path):
    """Test E: FastAPI endpoint behavior and raw storage integration."""
    target_raw_file = str(tmp_path / "incidents.json")

    mock_incidents = [
        {"id": "P777", "summary": "Endpoint Mock Incident", "service": {"id": "PK9U7OK"}}
    ]

    with patch("backend.main.PagerDutyClient") as MockClient, \
         patch("backend.main.save_raw_pagerduty_incidents", side_effect=lambda service_id, pagerduty_url, incidents: save_raw_pagerduty_incidents(service_id, pagerduty_url, incidents, output_filepath=target_raw_file)), \
         patch("backend.main.normalize_pagerduty_dataset") as mock_norm:

        
        MockClient.extract_service_id_from_url.return_value = "PK9U7OK"
        mock_instance = MagicMock()
        mock_instance.get_incidents.return_value = mock_incidents
        MockClient.return_value = mock_instance


        response = client.post(
            "/api/ingestion/pagerduty",
            json={
                "pagerduty_url": "https://acmepay.pagerduty.com/service-directory/PK9U7OK/activity",
                "api_token": "valid_token"
            }
        )

        assert response.status_code == 200
        res_data = response.json()
        assert res_data["success"] is True
        assert res_data["service_id"] == "PK9U7OK"
        assert res_data["total_incidents_fetched"] == 1

    # Verify raw file was written
    stored = get_raw_pagerduty_incidents(target_raw_file)
    assert stored is not None
    assert stored["service_id"] == "PK9U7OK"
    assert stored["total_incidents"] == 1
    assert stored["incidents"][0]["id"] == "P777"
