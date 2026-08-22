# backend/process_evidence.py
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

# Adjust imports to match your project structure
from backend.mapper import resolve_modules_from_files, resolve_modules_from_labels
from backend.models.core import Module, EvidenceRecord  

def process_event_to_evidence(db_session: Session, normalized_event: dict) -> list:
    """
    Converts a normalized GitHub/Jira event into EvidenceRecords in the database.
    Now supports both file-based mapping (Commits/PRs) and label-based mapping (Issues).
    """
    if not normalized_event or not normalized_event.get("employee_id"):
        return []

    # 1. Extract core data and context
    employee_id = normalized_event["employee_id"]
    source = normalized_event["source_type"]         
    source_ref = normalized_event["source_record_id"] 
    
    context = normalized_event.get("context", {})
    files = context.get("files", [])
    labels = context.get("labels", [])

    # 2. Parse the timestamp safely
    raw_time = normalized_event.get("timestamp")
    try:
        if raw_time:
            # Handles ISO format like "2026-05-02T10:00:00Z"
            event_date = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        else:
            event_date = datetime.now(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        event_date = datetime.now(timezone.utc)

    # 3. Determine base weight based on provenance
    weight = 1.0 if normalized_event.get("provenance_type") == "Demonstrated" else 0.5

    # 4. Resolve Module IDs using BOTH files and labels
    touched_module_ids = resolve_modules_from_files(files)
    touched_module_ids.update(resolve_modules_from_labels(labels))
    
    new_records = []
    
    # 5. Create EvidenceRecords for every capability attached to the resolved modules
    for module_id in touched_module_ids:
        
        # Query the database for the module
        module = db_session.query(Module).filter(Module.id == module_id).first()
        
        if not module:
            continue  # Skip if module doesn't exist in DB
            
        # Loop through capabilities linked via `module_capabilities`
        for capability in module.capabilities:
            
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

    # 6. Commit all new evidence records
    db_session.commit()
    return new_records