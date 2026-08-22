import json
from pathlib import Path
from backend.ingestion.github.review_extractor import extract_review_event, extract_review_events

DATA_RAW_REVIEW_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "github" / "reviews.json"


def test_valid_review_extraction():
    """Verify that a valid raw review record produces expected normalized event with Review provenance."""
    raw_review = {
        "review_id": "REV-201",
        "pr_id": "PR-101",
        "reviewer_id": "E002",
        "timestamp": "2026-05-02T11:15:00Z",
        "state": "APPROVED",
        "comments": [
            "Looks good. Code structure for intent routing is clean."
        ]
    }

    event = extract_review_event(raw_review)
    assert event is not None
    assert event["employee_id"] == "E002"
    assert event["source"] == "github"
    assert event["source_type"] == "review"
    assert event["source_record_id"] == "REV-201"
    assert event["action"] == "review_pull_request"
    assert event["timestamp"] == "2026-05-02T11:15:00Z"
    assert event["provenance_type"] == "Review"
    assert event["provenance_type"] != "Demonstrated"
    assert event["context"]["pr_id"] == "PR-101"
    assert event["context"]["state"] == "APPROVED"
    assert event["context"]["comments"] == ["Looks good. Code structure for intent routing is clean."]


def test_missing_author():
    """Verify that a review record with missing or empty reviewer_id returns None."""
    raw_review_none = {
        "review_id": "REV-202",
        "pr_id": "PR-101",
        "reviewer_id": None,
        "timestamp": "2026-05-02T11:40:00Z",
        "state": "APPROVED",
        "comments": []
    }
    raw_review_blank = {
        "review_id": "REV-203",
        "pr_id": "PR-101",
        "reviewer_id": "   ",
        "timestamp": "2026-05-02T11:40:00Z",
        "state": "APPROVED",
        "comments": []
    }

    assert extract_review_event(raw_review_none) is None
    assert extract_review_event(raw_review_blank) is None


def test_missing_review_id():
    """Verify that a review record with missing or empty review_id returns None."""
    raw_review_none = {
        "review_id": None,
        "pr_id": "PR-101",
        "reviewer_id": "E002",
        "timestamp": "2026-05-02T11:40:00Z",
        "state": "APPROVED",
        "comments": []
    }
    raw_review_empty = {
        "review_id": "",
        "pr_id": "PR-101",
        "reviewer_id": "E002",
        "timestamp": "2026-05-02T11:40:00Z",
        "state": "APPROVED",
        "comments": []
    }

    assert extract_review_event(raw_review_none) is None
    assert extract_review_event(raw_review_empty) is None


def test_source_id_preservation():
    """Verify that original review_id is preserved as source_record_id."""
    raw_review = {
        "review_id": "CUSTOM-REV-888",
        "pr_id": "PR-102",
        "reviewer_id": "E005",
        "timestamp": "2026-06-01T11:00:00Z",
        "state": "APPROVED",
        "comments": ["Multi-currency rate conversion handling looks robust."]
    }

    event = extract_review_event(raw_review)
    assert event is not None
    assert event["source_record_id"] == "CUSTOM-REV-888"


def test_batch_extraction_from_raw_json():
    """Verify batch extraction on existing data/raw/github/reviews.json dataset (16 reviews)."""
    with open(DATA_RAW_REVIEW_FILE, "r", encoding="utf-8") as f:
        raw_reviews = json.load(f)

    events = extract_review_events(raw_reviews)
    assert len(events) == 16

    for event in events:
        assert event["source"] == "github"
        assert event["source_type"] == "review"
        assert event["employee_id"] in {"E001", "E002", "E003", "E004", "E005"}
        assert event["provenance_type"] == "Review"
        assert event["action"] == "review_pull_request"
        assert event["source_record_id"].startswith("REV-")
        assert "pr_id" in event["context"]
        assert "state" in event["context"]
        assert "comments" in event["context"]
