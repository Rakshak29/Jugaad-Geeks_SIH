from typing import Dict, Any, Optional, Union, List


def extract_issue_event(raw_issue: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """
    Extract an intermediate normalized evidence event from a raw GitHub issue record.

    Accepts raw_issue as a dictionary (e.g. from JSON) or a SQLAlchemy RawGitHubIssue model.

    Rules:
    - Produces the exact same normalized evidence event schema used by PR, Commit, and Review extractors.
    - Preserves original issue_id as source_record_id.
    - Preserves author_id as employee_id.
    - Preserves context (assignee_id, title, description, status, labels).
    - Filing an issue produces provenance_type = "Proposed" and action = "create_issue".
    - Returns None if author_id or issue_id is missing or empty.
    """
    if isinstance(raw_issue, dict):
        author_id = raw_issue.get("author_id")
        issue_id = raw_issue.get("issue_id")
        assignee_id = raw_issue.get("assignee_id")
        timestamp = raw_issue.get("timestamp")
        title = raw_issue.get("title")
        description = raw_issue.get("description")
        status = raw_issue.get("status")
        labels = raw_issue.get("labels", [])
    else:
        author_id = getattr(raw_issue, "author_id", None)
        issue_id = getattr(raw_issue, "issue_id", None)
        assignee_id = getattr(raw_issue, "assignee_id", None)
        timestamp = getattr(raw_issue, "timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        title = getattr(raw_issue, "title", None)
        description = getattr(raw_issue, "description", None)
        status = getattr(raw_issue, "status", None)
        labels = getattr(raw_issue, "labels", [])

    # Validate mandatory identifiers
    if not author_id or not str(author_id).strip() or not issue_id or not str(issue_id).strip():
        return None

    context = {
        "assignee_id": str(assignee_id) if assignee_id else None,
        "title": title,
        "description": description,
        "status": status,
        "labels": labels if isinstance(labels, list) else [],
    }

    return {
        "employee_id": str(author_id),
        "source": "github",
        "source_type": "issue",
        "source_record_id": str(issue_id),
        "action": "create_issue",
        "timestamp": str(timestamp) if timestamp else None,
        "context": context,
        "provenance_type": "Proposed",
    }


def extract_issue_events(raw_issues: List[Union[Dict[str, Any], Any]]) -> List[Dict[str, Any]]:
    """Batch extract normalized events from a list of raw GitHub issue records."""
    events = []
    for raw_issue in raw_issues:
        event = extract_issue_event(raw_issue)
        if event:
            events.append(event)
    return events
