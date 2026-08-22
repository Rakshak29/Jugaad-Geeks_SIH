from typing import Dict, Any, Optional, Union, List


def extract_review_event(raw_review: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """
    Extract an intermediate normalized evidence event from a raw GitHub review record.

    Accepts raw_review as a dictionary (e.g. from JSON) or a SQLAlchemy RawGitHubReview model.

    Rules:
    - Produces the exact same normalized evidence event schema used by PR and Commit extractors.
    - A GitHub review produces Review provenance ("Review") and is NOT treated as Demonstrated implementation evidence.
    - Preserves original review_id as source_record_id.
    - Preserves context (pr_id, state, comments).
    - Returns None if reviewer_id or review_id is missing or empty.
    """
    if isinstance(raw_review, dict):
        reviewer_id = raw_review.get("reviewer_id")
        review_id = raw_review.get("review_id")
        pr_id = raw_review.get("pr_id")
        timestamp = raw_review.get("timestamp")
        state = raw_review.get("state")
        comments = raw_review.get("comments", [])
    else:
        reviewer_id = getattr(raw_review, "reviewer_id", None)
        review_id = getattr(raw_review, "review_id", None)
        pr_id = getattr(raw_review, "pr_id", None)
        timestamp = getattr(raw_review, "timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        state = getattr(raw_review, "state", None)
        comments = getattr(raw_review, "comments", [])

    # Validate mandatory identifiers
    if not reviewer_id or not str(reviewer_id).strip() or not review_id or not str(review_id).strip():
        return None

    context = {
        "pr_id": str(pr_id) if pr_id else None,
        "state": state,
        "comments": comments if isinstance(comments, list) else [],
    }

    return {
        "employee_id": str(reviewer_id),
        "source": "github",
        "source_type": "review",
        "source_record_id": str(review_id),
        "action": "review_pull_request",
        "timestamp": str(timestamp) if timestamp else None,
        "context": context,
        "provenance_type": "Review",
    }


def extract_review_events(raw_reviews: List[Union[Dict[str, Any], Any]]) -> List[Dict[str, Any]]:
    """Batch extract normalized events from a list of raw GitHub review records."""
    events = []
    for raw_review in raw_reviews:
        event = extract_review_event(raw_review)
        if event:
            events.append(event)
    return events
