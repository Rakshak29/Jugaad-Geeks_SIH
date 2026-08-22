from typing import Dict, Any, Optional, Union, List


def extract_documentation_event(raw_document: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """
    Extract an intermediate normalized evidence event from a raw documentation record.

    Accepts raw_document as a dictionary (e.g. from JSON) or a SQLAlchemy RawDocument model.

    Rules:
    - Produces the exact same normalized evidence event schema used by previous extractors.
    - Maps doc_id -> source_record_id.
    - Maps author_id -> employee_id.
    - Maps title, content_summary, doc_type, service, filepath, timestamps into context.
    - Authored documentation produces provenance_type = "Demonstrated" and action = "author_documentation".
    - Returns None if author_id or doc_id is missing or empty.
    """
    if isinstance(raw_document, dict):
        doc_id = raw_document.get("doc_id")
        author_id = raw_document.get("author_id")
        last_modified_by = raw_document.get("last_modified_by")
        created_at = raw_document.get("created_at")
        updated_at = raw_document.get("updated_at")
        doc_type = raw_document.get("doc_type")
        title = raw_document.get("title")
        service = raw_document.get("service")
        content_summary = raw_document.get("content_summary")
        filepath = raw_document.get("filepath")
    else:
        doc_id = getattr(raw_document, "doc_id", None)
        author_id = getattr(raw_document, "author_id", None)
        last_modified_by = getattr(raw_document, "last_modified_by", None)
        created_at = getattr(raw_document, "created_at", None)
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        updated_at = getattr(raw_document, "updated_at", None)
        if hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()
        doc_type = getattr(raw_document, "doc_type", None)
        title = getattr(raw_document, "title", None)
        service = getattr(raw_document, "service", None)
        content_summary = getattr(raw_document, "content_summary", None)
        filepath = getattr(raw_document, "filepath", None)

    # Validate mandatory identifiers
    if not doc_id or not str(doc_id).strip() or not author_id or not str(author_id).strip():
        return None

    # Timestamp selection (prefer updated_at, fallback to created_at)
    timestamp = str(updated_at) if updated_at else (str(created_at) if created_at else None)

    context = {
        "title": title,
        "content": content_summary,
        "content_summary": content_summary,
        "doc_type": doc_type,
        "document_type": doc_type,
        "service": service,
        "filepath": filepath,
        "created_at": str(created_at) if created_at else None,
        "updated_at": str(updated_at) if updated_at else None,
        "last_modified_by": str(last_modified_by) if last_modified_by else None,
    }

    return {
        "employee_id": str(author_id).strip(),
        "source": "documentation",
        "source_type": "document",
        "source_record_id": str(doc_id),
        "action": "author_documentation",
        "timestamp": timestamp,
        "context": context,
        "provenance_type": "Demonstrated",
    }


def extract_documentation_events(raw_documents: List[Union[Dict[str, Any], Any]]) -> List[Dict[str, Any]]:
    """Batch extract normalized events from a list of raw documentation records."""
    events = []
    for raw_doc in raw_documents:
        event = extract_documentation_event(raw_doc)
        if event:
            events.append(event)
    return events
