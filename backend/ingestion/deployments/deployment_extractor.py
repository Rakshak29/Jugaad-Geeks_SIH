from typing import Dict, Any, Optional, Union, List


def extract_deployment_event(raw_deployment: Union[Dict[str, Any], Any]) -> Optional[Dict[str, Any]]:
    """
    Extract an intermediate normalized evidence event from a raw deployment record.

    Accepts raw_deployment as a dictionary (e.g. from JSON) or a SQLAlchemy RawDeployment model.

    Rules:
    - Produces the exact same normalized evidence event schema used by existing extractors.
    - Preserves original deployment_id as source_record_id.
    - Maps employee from deployed_by.
    - DEPLOY action maps to action = "deploy_service", ROLLBACK maps to action = "rollback_service".
    - Both successful deployments and rollbacks produce provenance_type = "Demonstrated".
    - Preserves context (service, environment, action, commit_hash, status, notes, reason).
    - Returns None if deployed_by or deployment_id is missing or empty.
    """
    if isinstance(raw_deployment, dict):
        deployment_id = raw_deployment.get("deployment_id")
        deployed_by = raw_deployment.get("deployed_by")
        timestamp = raw_deployment.get("timestamp")
        environment = raw_deployment.get("environment")
        service = raw_deployment.get("service")
        raw_action = raw_deployment.get("action")
        commit_hash = raw_deployment.get("commit_hash")
        status = raw_deployment.get("status")
        notes = raw_deployment.get("notes")
    else:
        deployment_id = getattr(raw_deployment, "deployment_id", None)
        deployed_by = getattr(raw_deployment, "deployed_by", None)
        timestamp = getattr(raw_deployment, "timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        environment = getattr(raw_deployment, "environment", None)
        service = getattr(raw_deployment, "service", None)
        raw_action = getattr(raw_deployment, "action", None)
        commit_hash = getattr(raw_deployment, "commit_hash", None)
        status = getattr(raw_deployment, "status", None)
        notes = getattr(raw_deployment, "notes", None)

    # Validate mandatory identifiers
    if not deployment_id or not str(deployment_id).strip() or not deployed_by or not str(deployed_by).strip():
        return None

    # Map action type
    action_str = str(raw_action).upper() if raw_action else ""
    if action_str == "ROLLBACK":
        action_type = "rollback_service"
    else:
        action_type = "deploy_service"

    context = {
        "service": service,
        "environment": environment,
        "action": raw_action,
        "commit_hash": commit_hash,
        "status": status,
        "notes": notes,
        "reason": notes,
    }

    return {
        "employee_id": str(deployed_by).strip(),
        "source": "deployments",
        "source_type": "deployment",
        "source_record_id": str(deployment_id),
        "action": action_type,
        "timestamp": str(timestamp) if timestamp else None,
        "context": context,
        "provenance_type": "Demonstrated",
    }


def extract_deployment_events(raw_deployments: List[Union[Dict[str, Any], Any]]) -> List[Dict[str, Any]]:
    """Batch extract normalized events from a list of raw deployment records."""
    events = []
    for raw_deployment in raw_deployments:
        event = extract_deployment_event(raw_deployment)
        if event:
            events.append(event)
    return events
