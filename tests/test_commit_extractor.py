import json
from pathlib import Path
from backend.ingestion.github.commit_extractor import extract_commit_event, extract_commit_events

DATA_RAW_COMMIT_FILE = Path(__file__).resolve().parent.parent / "data" / "raw" / "github" / "commits.json"


def test_valid_commit_extraction():
    """Verify that a valid raw commit record produces the expected normalized evidence event."""
    raw_commit = {
        "commit_id": "c001a1",
        "author_id": "E001",
        "timestamp": "2026-05-02T09:15:00Z",
        "message": "feat(api): add v2 payment intent routing endpoint",
        "files_changed": [
            "services/api/router.go",
            "services/api/intent_handler.go"
        ],
        "lines_added": 120,
        "lines_deleted": 15,
        "branch": "main"
    }

    event = extract_commit_event(raw_commit)
    assert event is not None
    assert event["employee_id"] == "E001"
    assert event["source"] == "github"
    assert event["source_type"] == "commit"
    assert event["source_record_id"] == "c001a1"
    assert event["action"] == "commit_code"
    assert event["timestamp"] == "2026-05-02T09:15:00Z"
    assert event["provenance_type"] == "Demonstrated"
    assert event["context"]["message"] == "feat(api): add v2 payment intent routing endpoint"
    assert event["context"]["files_changed"] == ["services/api/router.go", "services/api/intent_handler.go"]
    assert event["context"]["lines_added"] == 120
    assert event["context"]["lines_deleted"] == 15
    assert event["context"]["branch"] == "main"


def test_missing_author():
    """Verify that a commit record with missing or empty author_id returns None."""
    raw_commit_none = {
        "commit_id": "c001a2",
        "author_id": None,
        "timestamp": "2026-05-05T11:30:00Z",
        "message": "fix bug",
        "files_changed": ["main.go"],
        "lines_added": 5,
        "lines_deleted": 2,
        "branch": "main"
    }
    raw_commit_blank = {
        "commit_id": "c001a3",
        "author_id": "   ",
        "timestamp": "2026-05-05T11:30:00Z",
        "message": "fix bug",
        "files_changed": [],
        "lines_added": 0,
        "lines_deleted": 0,
        "branch": "main"
    }

    assert extract_commit_event(raw_commit_none) is None
    assert extract_commit_event(raw_commit_blank) is None


def test_missing_commit_id():
    """Verify that a commit record with missing or empty commit_id returns None."""
    raw_commit_none = {
        "commit_id": None,
        "author_id": "E001",
        "timestamp": "2026-05-05T11:30:00Z",
        "message": "fix bug",
        "files_changed": [],
        "lines_added": 0,
        "lines_deleted": 0,
        "branch": "main"
    }
    raw_commit_empty = {
        "commit_id": "",
        "author_id": "E001",
        "timestamp": "2026-05-05T11:30:00Z",
        "message": "fix bug",
        "files_changed": [],
        "lines_added": 0,
        "lines_deleted": 0,
        "branch": "main"
    }

    assert extract_commit_event(raw_commit_none) is None
    assert extract_commit_event(raw_commit_empty) is None


def test_source_id_preservation():
    """Verify that original commit_id is preserved as source_record_id."""
    raw_commit = {
        "commit_id": "CUSTOM-HASH-999",
        "author_id": "E003",
        "timestamp": "2026-04-15T08:20:00Z",
        "message": "feat(db): write automated WAL archiver script",
        "files_changed": ["db/recovery/wal_archiver.sh"],
        "lines_added": 280,
        "lines_deleted": 15,
        "branch": "main"
    }

    event = extract_commit_event(raw_commit)
    assert event is not None
    assert event["source_record_id"] == "CUSTOM-HASH-999"


def test_batch_extraction_from_raw_json():
    """Verify batch extraction on existing data/raw/github/commits.json dataset (35 commits)."""
    with open(DATA_RAW_COMMIT_FILE, "r", encoding="utf-8") as f:
        raw_commits = json.load(f)

    events = extract_commit_events(raw_commits)
    assert len(events) == len(raw_commits)


    for event in events:
        assert event["source"] == "github"
        assert event["source_type"] == "commit"
        assert bool(event["employee_id"])

        assert event["provenance_type"] == "Demonstrated"
        assert event["action"] == "commit_code"
        assert len(event["source_record_id"]) > 0
        assert "message" in event["context"]
        assert "files_changed" in event["context"]
