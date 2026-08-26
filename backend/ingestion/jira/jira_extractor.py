from typing import Dict, Any, Optional, Union, List


def _extract_text_from_adf(node: Any) -> str:
    """Extract plain text recursively from an Atlassian Document Format (ADF) structure."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        text_parts = []
        if node.get("type") == "text" and "text" in node:
            text_parts.append(node["text"])
        if "content" in node and isinstance(node["content"], list):
            for child in node["content"]:
                child_text = _extract_text_from_adf(child)
                if child_text:
                    text_parts.append(child_text)
        return " ".join(text_parts).strip()
    if isinstance(node, list):
        return " ".join(_extract_text_from_adf(item) for item in node).strip()
    return str(node)


def _extract_user_id(user_val: Any) -> Optional[str]:
    """Extract a user identifier from a string or Jira user dictionary."""
    if user_val is None:
        return None
    if isinstance(user_val, str):
        val = user_val.strip()
        return val if val else None
    if isinstance(user_val, dict):
        for key in ("displayName", "name", "emailAddress", "accountId", "id"):
            cand = user_val.get(key)
            if cand and isinstance(cand, str) and cand.strip():
                return cand.strip()
    return None


def map_jira_issue(raw_jira: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    """
    Parse and map a raw Jira API payload, JiraRecord dataclass, or database model into a normalized dictionary.

    Supports:
    - Synthetic flat format (e.g. data/raw/jira/issues.json)
    - Live Jira REST API JSON (Cloud / Server / Data Center response with 'fields' and 'key')
    - JiraRecord dataclass instance (with source_native_id and payload)
    - SQLAlchemy RawJiraIssue model
    """
    # 1. Handle JiraRecord or wrapper objects with payload
    if hasattr(raw_jira, "payload") and isinstance(raw_jira.payload, dict):
        source_native_id = getattr(raw_jira, "source_native_id", None)
        payload = raw_jira.payload
    elif isinstance(raw_jira, dict) and "payload" in raw_jira and isinstance(raw_jira["payload"], dict):
        source_native_id = raw_jira.get("source_native_id")
        payload = raw_jira["payload"]
    elif isinstance(raw_jira, dict):
        source_native_id = raw_jira.get("source_native_id")
        payload = raw_jira
    else:
        source_native_id = getattr(raw_jira, "source_native_id", None)
        payload = None

    # 2. Extract from dictionary payload (REST API or flat format)
    if payload is not None:
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload

        # Issue identifier
        jira_id = (
            payload.get("jira_id")
            or payload.get("key")
            or source_native_id
            or payload.get("id")
            or fields.get("jira_id")
            or fields.get("key")
        )

        # Summary & Description
        summary = fields.get("summary")
        description_raw = fields.get("description")
        if isinstance(description_raw, (dict, list)):
            description = _extract_text_from_adf(description_raw)
        else:
            description = str(description_raw) if description_raw is not None else None

        # Users
        reporter_id = _extract_user_id(fields.get("reporter") or fields.get("reporter_id") or fields.get("creator"))
        assignee_id = _extract_user_id(fields.get("assignee") or fields.get("assignee_id"))

        if not assignee_id and description:
            import re
            m = re.search(r"Assigned to ([^(/]+)", description)
            if m:
                assignee_id = m.group(1).strip()
            else:
                m2 = re.search(r"Reported by ([^(/]+)", description)
                if m2:
                    assignee_id = m2.group(1).strip()

        # Timestamps
        timestamp = fields.get("created") or fields.get("created_at") or fields.get("timestamp")
        updated_at = fields.get("updated") or fields.get("updated_at")

        # Issue type
        issuetype_obj = fields.get("issuetype") or fields.get("issue_type")
        if isinstance(issuetype_obj, dict):
            issue_type = issuetype_obj.get("name")
        else:
            issue_type = issuetype_obj

        # Status
        status_obj = fields.get("status")
        if isinstance(status_obj, dict):
            status = status_obj.get("name")
        else:
            status = status_obj

        # Components
        comps_raw = fields.get("components", [])
        if isinstance(comps_raw, list):
            components = [
                c.get("name") if isinstance(c, dict) else str(c)
                for c in comps_raw
                if c
            ]
        elif isinstance(comps_raw, str):
            components = [comps_raw]
        else:
            components = []

        # Labels
        labels = fields.get("labels", [])
        if not isinstance(labels, list):
            labels = [labels] if labels else []

    else:
        # 3. Extract from SQLAlchemy model or custom object
        jira_id = getattr(raw_jira, "jira_id", getattr(raw_jira, "key", None))
        reporter_id = _extract_user_id(getattr(raw_jira, "reporter_id", getattr(raw_jira, "reporter", None)))
        assignee_id = _extract_user_id(getattr(raw_jira, "assignee_id", getattr(raw_jira, "assignee", None)))
        timestamp = getattr(raw_jira, "timestamp", getattr(raw_jira, "created", None))
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        updated_at = getattr(raw_jira, "updated_at", getattr(raw_jira, "updated", None))
        if hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()
        issue_type = getattr(raw_jira, "issue_type", getattr(raw_jira, "issuetype", None))
        if isinstance(issue_type, dict):
            issue_type = issue_type.get("name")
        summary = getattr(raw_jira, "summary", None)
        description_raw = getattr(raw_jira, "description", None)
        if isinstance(description_raw, (dict, list)):
            description = _extract_text_from_adf(description_raw)
        else:
            description = str(description_raw) if description_raw is not None else None
        status = getattr(raw_jira, "status", None)
        if isinstance(status, dict):
            status = status.get("name")
        comps_raw = getattr(raw_jira, "components", [])
        if isinstance(comps_raw, list):
            components = [
                c.get("name") if isinstance(c, dict) else str(c)
                for c in comps_raw
                if c
            ]
        elif isinstance(comps_raw, str):
            components = [comps_raw]
        else:
            components = []
        labels = getattr(raw_jira, "labels", [])
        if not isinstance(labels, list):
            labels = [labels] if labels else []

    return {
        "jira_id": str(jira_id).strip() if jira_id else None,
        "reporter_id": reporter_id,
        "assignee_id": assignee_id,
        "timestamp": str(timestamp) if timestamp else None,
        "updated_at": str(updated_at) if updated_at else None,
        "issue_type": issue_type,
        "summary": summary,
        "description": description,
        "status": status,
        "components": components,
        "labels": labels,
    }


def extract_jira_issue_event(raw_jira: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """
    Extract an intermediate normalized evidence event from a raw Jira issue record.

    Accepts raw_jira as a dictionary (flat JSON or live Jira REST API),
    a JiraRecord dataclass, or a SQLAlchemy RawJiraIssue model.

    Rules:
    - Produces the exact same normalized evidence event schema established by GitHub extractors.
    - Preserves original jira_id as source_record_id.
    - Maps employee from assignee_id (or reporter_id as fallback).
    - Preserves context (reporter_id, assignee_id, updated_at, issue_type, summary, description, status, components, labels).
    - Jira tickets produce provenance_type = "Proposed" and action = "manage_jira_issue".
    - Returns None if no employee ID or jira_id is present.
    """
    mapped = map_jira_issue(raw_jira)

    jira_id = mapped.get("jira_id")
    if not jira_id:
        return None

    # Map employee_id from assignee_id or reporter_id fallback
    assignee_id = mapped.get("assignee_id")
    reporter_id = mapped.get("reporter_id")

    employee_id = None
    if assignee_id and str(assignee_id).strip():
        employee_id = str(assignee_id).strip()
    elif reporter_id and str(reporter_id).strip():
        employee_id = str(reporter_id).strip()

    if not employee_id:
        return None

    context = {
        "reporter_id": reporter_id,
        "assignee_id": assignee_id,
        "updated_at": mapped.get("updated_at"),
        "issue_type": mapped.get("issue_type"),
        "summary": mapped.get("summary"),
        "description": mapped.get("description"),
        "status": mapped.get("status"),
        "components": mapped.get("components", []),
    }
    if mapped.get("labels"):
        context["labels"] = mapped["labels"]

    return {
        "employee_id": employee_id,
        "source": "jira",
        "source_type": "issue",
        "source_record_id": str(jira_id),
        "action": "manage_jira_issue",
        "timestamp": mapped.get("timestamp"),
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
