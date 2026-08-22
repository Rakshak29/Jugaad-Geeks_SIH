from typing import Dict, Any, Optional, Union, List


def extract_jira_issue_event(raw_jira: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """
    Extract an intermediate normalized evidence event from a raw Jira issue record.

    Accepts raw_jira as a dictionary (e.g. from JSON) or a SQLAlchemy RawJiraIssue model.

    Rules:
    - Produces the exact same normalized evidence event schema established by GitHub extractors.
    - Preserves original jira_id as source_record_id.
    - Maps employee from assignee_id (or reporter_id as fallback).
    - Preserves context (reporter_id, assignee_id, updated_at, issue_type, summary, description, status, components).
    - Jira tickets produce provenance_type = "Proposed" and action = "manage_jira_issue".
    - Returns None if no employee ID or jira_id is present.
    """
    if isinstance(raw_jira, dict):
        jira_id = raw_jira.get("jira_id")
        reporter_id = raw_jira.get("reporter_id")
        assignee_id = raw_jira.get("assignee_id")
        timestamp = raw_jira.get("timestamp")
        updated_at = raw_jira.get("updated_at")
        issue_type = raw_jira.get("issue_type")
        summary = raw_jira.get("summary")
        description = raw_jira.get("description")
        status = raw_jira.get("status")
        components = raw_jira.get("components", [])
    else:
        jira_id = getattr(raw_jira, "jira_id", None)
        reporter_id = getattr(raw_jira, "reporter_id", None)
        assignee_id = getattr(raw_jira, "assignee_id", None)
        timestamp = getattr(raw_jira, "timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        updated_at = getattr(raw_jira, "updated_at", None)
        if hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()
        issue_type = getattr(raw_jira, "issue_type", None)
        summary = getattr(raw_jira, "summary", None)
        description = getattr(raw_jira, "description", None)
        status = getattr(raw_jira, "status", None)
        components = getattr(raw_jira, "components", [])

    # Validate mandatory identifiers
    if not jira_id or not str(jira_id).strip():
        return None

    # Map employee_id from assignee_id or reporter_id fallback
    employee_id = None
    if assignee_id and str(assignee_id).strip():
        employee_id = str(assignee_id).strip()
    elif reporter_id and str(reporter_id).strip():
        employee_id = str(reporter_id).strip()

    if not employee_id:
        return None

    context = {
        "reporter_id": str(reporter_id) if reporter_id else None,
        "assignee_id": str(assignee_id) if assignee_id else None,
        "updated_at": str(updated_at) if updated_at else None,
        "issue_type": issue_type,
        "summary": summary,
        "description": description,
        "status": status,
        "components": components if isinstance(components, list) else [],
    }

    return {
        "employee_id": employee_id,
        "source": "jira",
        "source_type": "issue",
        "source_record_id": str(jira_id),
        "action": "manage_jira_issue",
        "timestamp": str(timestamp) if timestamp else None,
        "context": context,
        "provenance_type": "Proposed",
    }


def extract_jira_issue_events(raw_jiras: List[Union[Dict[str, Any], Any]]) -> List[Dict[str, Any]]:
    """Batch extract normalized events from a list of raw Jira issue records."""
    events = []
    for raw_jira in raw_jiras:
        event = extract_jira_issue_event(raw_jira)
        if event:
            events.append(event)
    return events
