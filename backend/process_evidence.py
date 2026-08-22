import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from backend.mapper import resolve_modules_from_files
from backend.models.core import Module, EvidenceRecord  # adjust import based on your folder structure

def process_event_to_evidence(db_session: Session, normalized_event: dict):
    """
    Converts a normalized GitHub/Jira event into EvidenceRecords in the database.
    """
    if not normalized_event:
        return []

    # 1. Extract core data from the event
    employee_id = normalized_event["employee_id"]
    files = normalized_event.get("context", {}).get("files", [])
    
    # Map extractor names to your DB schema names
    source = normalized_event["source_type"]         # e.g., "pull_request"
    source_ref = normalized_event["source_record_id"] # e.g., "PR-101"
    
    # 2. Parse the timestamp
    raw_time = normalized_event.get("timestamp")
    try:
        # Handles ISO format like "2026-05-02T10:00:00Z"
        event_date = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        event_date = datetime.utcnow()

    # 3. Determine weight based on provenance
    # "Demonstrated" (merged PR) gets full weight. "Proposed" (unmerged) gets less.
    weight = 1.0 if normalized_event.get("provenance_type") == "Demonstrated" else 0.5

    # 4. Resolve file paths to Module IDs
    touched_module_ids = resolve_modules_from_files(files)
    
    new_records = []
    
    # 5. Create EvidenceRecords for every capability attached to the touched modules
    for module_id in touched_module_ids:
        
        # Query the database for the module (SQLAlchemy handles the relationship!)
        module = db_session.query(Module).filter(Module.id == module_id).first()
        
        if not module:
            continue  # Skip if module doesn't exist in DB
            
        # Loop through capabilities linked via `module_capabilities` table
        for capability in module.capabilities:
            
            # Generate a unique ID for the evidence record (e.g., "EV-a1b2c3d4")
            record_id = f"EV-{uuid.uuid4().hex[:8]}"
            
            evidence = EvidenceRecord(
                id=record_id,
                employee_id=employee_id,
                capability_id=capability.id,
                module_id=module.id,
                source=source,
                source_ref=source_ref,
                event_date=event_date,
                weight=weight
            )
            
            db_session.add(evidence)
            new_records.append(evidence)

    # 6. Commit all new evidence records to the database
    db_session.commit()
    return new_records