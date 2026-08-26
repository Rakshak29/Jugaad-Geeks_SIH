from typing import Dict, Any, Optional, Union, List


def extract_pr_event(raw_pr: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """
    Extract an intermediate normalized evidence event from a raw GitHub pull request record.

    Accepts raw_pr as a dictionary (e.g. from JSON) or a SQLAlchemy RawGitHubPullRequest model.

    Rules:
    - Merged PR authored by an employee produces provenance_type = "Demonstrated".
    - Unmerged PR (status != "MERGED") produces provenance_type = "Proposed" (not Demonstrated).
    - Preserves original pr_id as source_record_id.
    - Preserves context (title, description, status, files, target_branch).
    - Returns None if author_id is missing or empty.
    """
    if isinstance(raw_pr, dict):
        author_id = raw_pr.get("author_id")
        pr_id = raw_pr.get("pr_id")
        timestamp = raw_pr.get("timestamp")
        title = raw_pr.get("title")
        description = raw_pr.get("description")
        status = raw_pr.get("status")
        files = raw_pr.get("files", [])
        target_branch = raw_pr.get("target_branch")
    else:
        author_id = getattr(raw_pr, "author_id", None)
        pr_id = getattr(raw_pr, "pr_id", None)
        timestamp = getattr(raw_pr, "timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        title = getattr(raw_pr, "title", None)
        description = getattr(raw_pr, "description", None)
        status = getattr(raw_pr, "status", None)
        files = getattr(raw_pr, "files", [])
        target_branch = getattr(raw_pr, "target_branch", None)

    # Validate mandatory identifiers
    if not author_id or not str(author_id).strip() or not pr_id:
        return None

    # Determine status and provenance
    status_str = str(status).upper() if status else ""
    is_merged = status_str == "MERGED"

    provenance_type = "Demonstrated" if is_merged else "Proposed"
    action = "merge_pull_request" if is_merged else "create_pull_request"

    context = {
        "title": title,
        "description": description,
        "status": status,
        "files": files if isinstance(files, list) else [],
        "target_branch": target_branch,
    }

    return {
        "employee_id": str(author_id),
        "source": "github",
        "source_type": "pull_request",
        "source_record_id": str(pr_id),
        "action": action,
        "timestamp": str(timestamp) if timestamp else None,
        "context": context,
        "provenance_type": provenance_type,
    }


def extract_pr_events(raw_prs: List[Union[Dict[str, Any], Any]]) -> List[Dict[str, Any]]:
    """Batch extract normalized events from a list of raw GitHub pull request records."""
    events = []
    for raw_pr in raw_prs:
        event = extract_pr_event(raw_pr)
        if event:
            events.append(event)
    return events