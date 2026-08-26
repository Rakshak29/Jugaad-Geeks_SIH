import hashlib
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

# Adjust imports to match your project structure
from backend.mapper import resolve_modules_from_files, resolve_modules_from_labels
from backend.models.core import Module, EvidenceRecord, Capability, Employee

def process_event_to_evidence(db_session: Session, normalized_event: dict) -> list:
    """
    Converts a normalized GitHub/Jira event into EvidenceRecords in the database.
    Now supports both file-based mapping (Commits/PRs) and label-based mapping (Issues).
    """
    if not normalized_event or not normalized_event.get("employee_id"):
        return []

    # 1. Extract core data and context
    employee_id = normalized_event["employee_id"]
    source = normalized_event.get("source") or normalized_event.get("source_type", "unknown")         
    source_ref = normalized_event["source_record_id"] 

    # Auto-create employee in database if not present
    emp = db_session.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        emp = Employee(id=employee_id, name=employee_id, role="Engineering")
        db_session.add(emp)
        db_session.commit() 
    
    context = normalized_event.get("context", {})
    files = list(context.get("files", []))
    if context.get("filepath") and context.get("filepath") not in files:
        files.append(context.get("filepath"))

    labels = list(context.get("labels", []))
    if context.get("components"):
        comps = context.get("components")
        if isinstance(comps, list):
            labels.extend(comps)
        elif isinstance(comps, str):
            labels.append(comps)
    if context.get("service"):
        labels.append(str(context.get("service")))

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

    if not touched_module_ids:
        text_content = f"{context.get('message', '')} {context.get('title', '')} {context.get('summary', '')}".lower()
        if any(w in text_content for w in ("recon", "reconcil", "settle", "report", "ledger", "payout", "audit")):
            touched_module_ids.add("M002")
        elif any(w in text_content for w in ("db", "database", "sql", "recovery", "backup", "postgres")):
            touched_module_ids.add("M003")
        elif any(w in text_content for w in ("deploy", "k8s", "docker", "ci", "workflow", "release", "infra", "argo")):
            touched_module_ids.add("M004")
        elif any(w in text_content for w in ("incident", "outage", "alert", "pager", "monitor", "grafana", "metric", "latency", "ops")):
            touched_module_ids.add("M005")
        elif any(w in text_content for w in ("crypto", "vault", "pci", "fraud", "security", "sanitiz", "kms", "blacklist")):
            touched_module_ids.add("M006")
        elif any(w in text_content for w in ("api", "gateway", "pay", "auth", "route", "ingress", "oauth", "token", "receipt", "intent")):
            touched_module_ids.add("M001")
        else:
            # Fallback to M001 so no commit, PR, or ticket is ever dropped
            default_mod = db_session.query(Module).first()
            if default_mod:
                touched_module_ids.add(default_mod.id)
            else:
                touched_module_ids.add("M001")
    
    new_records = []
    
    # 5. Create EvidenceRecords for every capability attached to the resolved modules
    for module_id in touched_module_ids:
        
        # Query the database for the module
        module = db_session.query(Module).filter(Module.id == module_id).first()
        
        if not module:
            continue  # Skip if module doesn't exist in DB
            
        caps = list(module.capabilities)
        if not caps:
            fallback_cap = db_session.query(Capability).first()
            if fallback_cap:
                caps = [fallback_cap]

        # Loop through capabilities linked via `module_capabilities`
        for capability in caps:
            
            # Idempotency check: Skip if matching record already exists
            existing_record = db_session.query(EvidenceRecord).filter_by(
                employee_id=employee_id,
                capability_id=capability.id,
                module_id=module.id,
                source=source,
                source_ref=source_ref
            ).first()

            if existing_record:
                continue

            raw_key = f"{employee_id}:{capability.id}:{module.id}:{source}:{source_ref}"
            record_id = f"EV-{hashlib.sha256(raw_key.encode()).hexdigest()[:8]}"
            
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
    if new_records:
        db_session.commit()
    return new_records