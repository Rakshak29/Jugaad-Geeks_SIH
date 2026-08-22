from typing import Dict, Any, Optional, Union, List


def extract_commit_event(raw_commit: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """
    Extract an intermediate normalized evidence event from a raw GitHub commit record.

    Accepts raw_commit as a dictionary (e.g. from JSON) or a SQLAlchemy RawGitHubCommit model.

    Rules:
    - Produces the exact same normalized evidence event schema established by the GitHub PR extractor.
    - Directly authored commit produces provenance_type = "Demonstrated" and action = "commit_code".
    - Preserves original commit_id as source_record_id.
    - Preserves context (message, files_changed, lines_added, lines_deleted, branch).
    - Returns None if author_id or commit_id is missing or empty.
    """
    if isinstance(raw_commit, dict):
        author_id = raw_commit.get("author_id")
        commit_id = raw_commit.get("commit_id")
        timestamp = raw_commit.get("timestamp")
        message = raw_commit.get("message")
        files_changed = raw_commit.get("files_changed", [])
        lines_added = raw_commit.get("lines_added", 0)
        lines_deleted = raw_commit.get("lines_deleted", 0)
        branch = raw_commit.get("branch")
    else:
        author_id = getattr(raw_commit, "author_id", None)
        commit_id = getattr(raw_commit, "commit_id", None)
        timestamp = getattr(raw_commit, "timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        message = getattr(raw_commit, "message", None)
        files_changed = getattr(raw_commit, "files_changed", [])
        lines_added = getattr(raw_commit, "lines_added", 0)
        lines_deleted = getattr(raw_commit, "lines_deleted", 0)
        branch = getattr(raw_commit, "branch", None)

    # Validate mandatory identifiers
    if not author_id or not str(author_id).strip() or not commit_id or not str(commit_id).strip():
        return None

    context = {
        "message": message,
        "files_changed": files_changed if isinstance(files_changed, list) else [],
        "lines_added": lines_added if isinstance(lines_added, int) else 0,
        "lines_deleted": lines_deleted if isinstance(lines_deleted, int) else 0,
        "branch": branch,
    }

    return {
        "employee_id": str(author_id),
        "source": "github",
        "source_type": "commit",
        "source_record_id": str(commit_id),
        "action": "commit_code",
        "timestamp": str(timestamp) if timestamp else None,
        "context": context,
        "provenance_type": "Demonstrated",
    }


def extract_commit_events(raw_commits: List[Union[Dict[str, Any], Any]]) -> List[Dict[str, Any]]:
    """Batch extract normalized events from a list of raw GitHub commit records."""
    events = []
    for raw_commit in raw_commits:
        event = extract_commit_event(raw_commit)
        if event:
            events.append(event)
    return events
