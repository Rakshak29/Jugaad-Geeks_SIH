# tests/test_rag_api.py
"""HTTP surface for the Capability Gap RAG, driven through the real app."""

import pytest
from fastapi.testclient import TestClient

from backend.database import get_db
from backend.main import app
from backend.rag.confluence.sync import run_sync
from tests.test_rag_retrieval import FakeConfluenceClient


@pytest.fixture
def client(rag_session):
    """The real app, with only the database dependency pointed at the fixture."""
    app.dependency_overrides[get_db] = lambda: rag_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def synced_client(client, rag_session):
    run_sync(rag_session, client=FakeConfluenceClient())
    return client


# --- the RAG must not disturb the existing API ------------------------------


def test_existing_endpoints_still_work(client):
    assert client.get("/").json() == {"status": "healthy"}
    assert client.get("/api/graph/knowledge").json()["success"] is True
    assert client.get("/api/graph/technical").json()["success"] is True


# --- status -----------------------------------------------------------------


def test_status_reports_configuration_and_index_state(client):
    body = client.get("/api/rag/confluence/status").json()
    assert body["indexed_pages"] == 0
    assert "configured" in body
    assert "unresolved_spaces" in body


def test_status_reflects_a_completed_sync(synced_client):
    body = synced_client.get("/api/rag/confluence/status").json()
    assert body["indexed_pages"] == 3
    assert body["indexed_sections"] > 0
    assert body["resolved_spaces"].get("DBOPS") == "S002"


def test_sync_without_credentials_returns_503(client, monkeypatch):
    """A missing token is a configuration problem, not a server fault."""
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_BASE_URL", "")
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_EMAIL", "")
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_API_TOKEN", "")

    response = client.post("/api/rag/confluence/sync", json={"force": False})
    assert response.status_code == 503
    assert "CONFLUENCE_BASE_URL" in response.json()["detail"]


# --- simulation -------------------------------------------------------------


def test_simulate_returns_bands_and_gaps(client):
    body = client.post("/api/rag/simulate", json={"employee_ids": ["E003"]}).json()
    assert body["gap_count"] == 2

    by_id = {c["capability_id"]: c for c in body["capabilities"]}
    assert by_id["C003"]["band_after"] == "NONE"
    assert by_id["C005"]["band_after"] == "LOW"
    assert by_id["C001"]["is_gap"] is False


def test_simulate_rejects_an_unknown_employee(client):
    response = client.post("/api/rag/simulate", json={"employee_ids": ["E999"]})
    assert response.status_code == 404


def test_simulate_requires_at_least_one_employee(client):
    assert client.post("/api/rag/simulate", json={"employee_ids": []}).status_code == 422


# --- retrieval --------------------------------------------------------------


def test_retrieve_returns_documents_with_reasons(synced_client):
    body = synced_client.post("/api/rag/retrieve", json={"capability_id": "C003"}).json()
    assert body["documents"]
    assert all(doc["match_evidence"] for doc in body["documents"])
    assert body["query_terms"]


def test_retrieve_before_any_sync_returns_409(client):
    response = client.post("/api/rag/retrieve", json={"capability_id": "C003"})
    assert response.status_code == 409
    assert "sync" in response.json()["detail"]


# --- transfer package -------------------------------------------------------


def test_transfer_package_generates_and_lists_files(synced_client):
    response = synced_client.post(
        "/api/rag/transfer-package",
        json={"employee_ids": ["E003"], "formats": ["md"], "include_markdown": True},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["package"]["gap_count"] == 2
    assert "md" in body["export"]["files"]
    assert "# Knowledge Transfer Package" in body["markdown"]

    listed = synced_client.get("/api/rag/packages").json()["packages"]
    assert body["export"]["slug"] in [p["slug"] for p in listed]


def test_generated_package_is_downloadable(synced_client):
    body = synced_client.post(
        "/api/rag/transfer-package", json={"employee_ids": ["E003"], "formats": ["md"]}
    ).json()

    response = synced_client.get(
        "/api/rag/transfer-package/%s/download" % body["export"]["slug"], params={"format": "md"}
    )
    assert response.status_code == 200
    assert "Knowledge Transfer Package" in response.text


def test_downloading_a_format_that_was_not_generated_returns_404(synced_client):
    body = synced_client.post(
        "/api/rag/transfer-package", json={"employee_ids": ["E003"], "formats": ["md"]}
    ).json()

    response = synced_client.get(
        "/api/rag/transfer-package/%s/download" % body["export"]["slug"], params={"format": "docx"}
    )
    assert response.status_code == 404


def test_package_generation_survives_an_empty_index(client):
    """Coverage analysis must still be delivered when no wiki has been synced."""
    body = client.post(
        "/api/rag/transfer-package",
        json={"employee_ids": ["E003"], "formats": ["md"], "include_markdown": True},
    ).json()

    assert body["package"]["gap_count"] == 2
    assert body["package"]["index"]["empty"] is True
    assert "No Confluence content has been synced" in body["markdown"]


@pytest.mark.parametrize("slug", ["../secrets", "..\\secrets", "a/b", "a\\b"])
def test_download_rejects_path_traversal(synced_client, slug):
    response = synced_client.get(
        "/api/rag/transfer-package/%s/download" % slug, params={"format": "md"}
    )
    assert response.status_code in (400, 404)


def test_download_rejects_an_unknown_format(synced_client):
    response = synced_client.get(
        "/api/rag/transfer-package/anything/download", params={"format": "exe"}
    )
    assert response.status_code == 422


# --- manual mapping ---------------------------------------------------------


def test_a_space_mapping_can_be_resolved_by_hand(client):
    response = client.post(
        "/api/rag/mapping/space", json={"space_key": "PLAT", "service_id": "S003"}
    )
    assert response.status_code == 200
    assert response.json()["entry"]["status"] == "manual"

    status = client.get("/api/rag/confluence/status").json()
    assert status["resolved_spaces"]["PLAT"] == "S003"


# --- gap context ------------------------------------------------------------


def test_gap_context_returns_gaps_with_their_search_context(client):
    body = client.post("/api/rag/gap-context", json={"employee_ids": ["E003"]}).json()

    assert body["count"] == 2
    assert {c["capability_id"] for c in body["contexts"]} == {"C003", "C005"}

    c003 = next(c for c in body["contexts"] if c["capability_id"] == "C003")
    assert c003["coverage"]["band_after"] == "NONE"
    assert c003["modules"][0]["module_id"] == "M003"
    assert c003["retrieval_context"]["query_terms"]


def test_gap_context_works_before_any_sync(client):
    """Steps 1 and 2 must not require step 3 to have run."""
    body = client.post("/api/rag/gap-context", json={"employee_ids": ["E003"]}).json()
    assert body["count"] == 2


def test_gap_context_can_target_a_single_capability(client):
    body = client.post(
        "/api/rag/gap-context", json={"employee_ids": ["E003"], "capability_id": "C001"}
    ).json()
    assert body["count"] == 1
    assert body["contexts"][0]["coverage"]["band_after"] == "HIGH"


def test_gap_context_rejects_unknown_ids(client):
    assert client.post(
        "/api/rag/gap-context", json={"employee_ids": ["E999"]}
    ).status_code == 404
    assert client.post(
        "/api/rag/gap-context", json={"employee_ids": ["E003"], "capability_id": "C999"}
    ).status_code == 404


# --- configuration diagnostics ----------------------------------------------


def test_placeholder_credentials_are_reported_as_unconfigured(client, monkeypatch):
    """
    An unedited .env is the most likely first-run mistake.

    Placeholder values look configured, so without this check the sync makes a
    real request and returns HTTP 401 -- which reads as "bad token" and sends
    the reader hunting in the wrong place.
    """
    monkeypatch.setattr(
        "backend.rag.config.CONFLUENCE_BASE_URL", "https://your-site.atlassian.net/wiki"
    )
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_EMAIL", "you@example.com")
    monkeypatch.setattr(
        "backend.rag.config.CONFLUENCE_API_TOKEN", "your_confluence_api_token_here"
    )

    body = client.get("/api/rag/confluence/status").json()
    assert body["configured"] is False
    assert set(body["placeholder_settings"]) == {
        "CONFLUENCE_BASE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN",
    }
    assert body["unset_settings"] == []
    assert "example value" in body["config_problem"]


def test_sync_with_placeholder_credentials_fails_before_any_request(client, monkeypatch):
    monkeypatch.setattr(
        "backend.rag.config.CONFLUENCE_BASE_URL", "https://your-site.atlassian.net/wiki"
    )
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_EMAIL", "you@example.com")
    monkeypatch.setattr(
        "backend.rag.config.CONFLUENCE_API_TOKEN", "your_confluence_api_token_here"
    )

    response = client.post("/api/rag/confluence/sync", json={"force": False})
    assert response.status_code == 503

    detail = response.json()["detail"]
    assert "example value" in detail
    assert ".env" in detail
    # It must name the settings rather than blaming the token generically.
    assert "CONFLUENCE_BASE_URL" in detail


def test_real_looking_credentials_are_accepted_as_configured(client, monkeypatch):
    """The placeholder check must not reject a genuine configuration."""
    monkeypatch.setattr(
        "backend.rag.config.CONFLUENCE_BASE_URL", "https://acme-engineering.atlassian.net/wiki"
    )
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_EMAIL", "sre@acme-engineering.com")
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_API_TOKEN", "ATATT" + "x" * 40)

    body = client.get("/api/rag/confluence/status").json()
    assert body["configured"] is True
    assert body["config_problem"] is None
    assert body["placeholder_settings"] == []


def test_real_credentials_are_not_rejected_when_env_example_holds_real_values(client, monkeypatch, tmp_path):
    """
    Regression: a working configuration was reported as unconfigured.

    The placeholder check compares .env against .env.example. Someone pasted
    real credentials into .env.example, so the two matched and valid settings
    were flagged as unedited -- the sync then refused to run at all.

    Matching the example file now only counts when the example value is itself
    visibly a stand-in.
    """
    example = tmp_path / ".env.example"
    example.write_text(
        "CONFLUENCE_BASE_URL=https://acme-engineering.atlassian.net/wiki\n"
        "CONFLUENCE_EMAIL=someone@acme-engineering.edu\n"
        "CONFLUENCE_API_TOKEN=ATATT" + "z" * 40 + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.rag.config.BASE_DIR", tmp_path)
    monkeypatch.setattr(
        "backend.rag.config.CONFLUENCE_BASE_URL", "https://acme-engineering.atlassian.net/wiki"
    )
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_EMAIL", "someone@acme-engineering.edu")
    monkeypatch.setattr("backend.rag.config.CONFLUENCE_API_TOKEN", "ATATT" + "z" * 40)

    body = client.get("/api/rag/confluence/status").json()
    assert body["configured"] is True
    assert body["placeholder_settings"] == []
    assert body["config_problem"] is None
