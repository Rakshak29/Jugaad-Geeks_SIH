import json
from pathlib import Path
from backend.ingestion.github.pr_extractor import extract_pr_event, extract_pr_events

DATA_RAW_PR_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "github" / "pull_requests.json"


def test_merged_pr():
    """Verify that a merged PR authored by an employee produces Demonstrated evidence."""
    raw_pr = {
        "pr_id": "PR-101",
        "author_id": "E001",
        "timestamp": "2026-05-02T10:00:00Z",
        "title": "Add v2 payment intent routing endpoint",
        "description": "Introduces new router handler for v2 payment intents.",
        "status": "MERGED",
        "files": ["services/api/router.go", "services/api/intent_handler.go"],
        "target_branch": "main"
    }

    event = extract_pr_event(raw_pr)
    assert event is not None
    assert event["employee_id"] == "E001"
    assert event["source"] == "github"
    assert event["source_type"] == "pull_request"
    assert event["source_record_id"] == "PR-101"
    assert event["action"] == "merge_pull_request"
    assert event["timestamp"] == "2026-05-02T10:00:00Z"
    assert event["provenance_type"] == "Demonstrated"
    assert event["context"]["title"] == "Add v2 payment intent routing endpoint"
    assert event["context"]["status"] == "MERGED"
    assert event["context"]["files"] == ["services/api/router.go", "services/api/intent_handler.go"]
    assert event["context"]["target_branch"] == "main"


def test_unmerged_pr():
    """Verify that an unmerged PR does NOT produce Demonstrated evidence."""
    raw_pr = {
        "pr_id": "PR-999",
        "author_id": "E002",
        "timestamp": "2026-06-01T12:00:00Z",
        "title": "WIP: Experimental feature flag",
        "description": "Work in progress PR for testing.",
        "status": "OPEN",
        "files": ["services/api/experimental.go"],
        "target_branch": "main"
    }

    event = extract_pr_event(raw_pr)
    assert event is not None
    assert event["employee_id"] == "E002"
    assert event["provenance_type"] == "Proposed"
    assert event["provenance_type"] != "Demonstrated"
    assert event["action"] == "create_pull_request"
    assert event["context"]["status"] == "OPEN"


def test_missing_author():
    """Verify that a PR record with a missing or empty author returns None."""
    raw_pr_none_author = {
        "pr_id": "PR-102",
        "author_id": None,
        "timestamp": "2026-05-02T10:00:00Z",
        "title": "PR with missing author",
        "status": "MERGED",
        "files": []
    }
    raw_pr_empty_author = {
        "pr_id": "PR-103",
        "author_id": "   ",
        "timestamp": "2026-05-02T10:00:00Z",
        "title": "PR with whitespace author",
        "status": "MERGED",
        "files": []
    }

    assert extract_pr_event(raw_pr_none_author) is None
    assert extract_pr_event(raw_pr_empty_author) is None


def test_source_id_preservation():
    """Verify that original pr_id is preserved exactly in source_record_id."""
    raw_pr = {
        "pr_id": "CUSTOM-PR-777",
        "author_id": "E003",
        "timestamp": "2026-04-15T09:00:00Z",
        "title": "Custom PR test",
        "status": "MERGED",
        "files": ["db/recovery/wal_archiver.sh"],
        "target_branch": "main"
    }

    event = extract_pr_event(raw_pr)
    assert event is not None
    assert event["source_record_id"] == "CUSTOM-PR-777"


def test_batch_extraction_from_raw_json():
    """Verify batch extraction on existing data/raw/github/pull_requests.json dataset."""
    with open(DATA_RAW_PR_FILE, "r", encoding="utf-8") as f:
        raw_prs = json.load(f)

    events = extract_pr_events(raw_prs)
    assert len(events) == 12

    for event in events:
        assert event["source"] == "github"
        assert event["source_type"] == "pull_request"
        assert event["employee_id"] in {"E001", "E002", "E003", "E004", "E005"}
        assert event["provenance_type"] == "Demonstrated"  # All 12 PRs in synthetic raw data are MERGED
        assert event["source_record_id"].startswith("PR-")
