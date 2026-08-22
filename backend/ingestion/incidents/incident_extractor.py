from typing import Dict, Any, Optional, Union, List


def extract_incident_events(raw_incident: Union[Dict[str, Any], Any]) -> List[Dict[str, Any]]:
    """
    Extract normalized evidence events from a raw incident record.

    One raw incident can produce MULTIPLE normalized evidence events (one per employee action/role).

    Rules:
    - Produces the exact same normalized evidence event schema used by existing extractors.
    - Lead responder produces action = "lead_incident_response", provenance_type = "Demonstrated".
    - Participants produce action = "participate_incident_response", provenance_type = "Demonstrated".
    - Reporter (if not responder/participant) produces action = "report_incident", provenance_type = "Observed".
    - Preserves original incident_id as source_record_id.
    - Preserves context (role, title, severity, service, summary, root_cause, action_items, resolved_at).
    - Returns [] if incident_id is missing or empty.
    """
    if isinstance(raw_incident, dict):
        incident_id = raw_incident.get("incident_id")
        reporter_id = raw_incident.get("reporter_id")
        lead_responder_id = raw_incident.get("lead_responder_id")
        participants = raw_incident.get("participants", [])
        timestamp = raw_incident.get("timestamp")
        resolved_at = raw_incident.get("resolved_at")
        title = raw_incident.get("title")
        severity = raw_incident.get("severity")
        service = raw_incident.get("service")
        summary = raw_incident.get("summary")
        root_cause = raw_incident.get("root_cause")
        action_items = raw_incident.get("action_items", [])
    else:
        incident_id = getattr(raw_incident, "incident_id", None)
        reporter_id = getattr(raw_incident, "reporter_id", None)
        lead_responder_id = getattr(raw_incident, "lead_responder_id", None)
        participants = getattr(raw_incident, "participants", [])
        timestamp = getattr(raw_incident, "timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        resolved_at = getattr(raw_incident, "resolved_at", None)
        if hasattr(resolved_at, "isoformat"):
            resolved_at = resolved_at.isoformat()
        title = getattr(raw_incident, "title", None)
        severity = getattr(raw_incident, "severity", None)
        service = getattr(raw_incident, "service", None)
        summary = getattr(raw_incident, "summary", None)
        root_cause = getattr(raw_incident, "root_cause", None)
        action_items = getattr(raw_incident, "action_items", [])

    # Validate mandatory incident_id
    if not incident_id or not str(incident_id).strip():
        return []

    events = []
    processed_employees = set()

    base_context = {
        "title": title,
        "severity": severity,
        "service": service,
        "summary": summary,
        "root_cause": root_cause,
        "action_items": action_items if isinstance(action_items, list) else [],
        "resolved_at": str(resolved_at) if resolved_at else None,
        "reporter_id": str(reporter_id) if reporter_id else None,
        "lead_responder_id": str(lead_responder_id) if lead_responder_id else None,
        "participants": [str(p) for p in participants] if isinstance(participants, list) else [],
    }

    # 1. Lead Responder Event
    if lead_responder_id and str(lead_responder_id).strip():
        lead_emp = str(lead_responder_id).strip()
        lead_context = dict(base_context)
        lead_context["role"] = "lead_responder"
        events.append({
            "employee_id": lead_emp,
            "source": "incidents",
            "source_type": "incident",
            "source_record_id": str(incident_id),
            "action": "lead_incident_response",
            "timestamp": str(timestamp) if timestamp else None,
            "context": lead_context,
            "provenance_type": "Demonstrated",
        })
        processed_employees.add(lead_emp)

    # 2. Participant Events
    if isinstance(participants, list):
        for part in participants:
            if part and str(part).strip():
                part_emp = str(part).strip()
                if part_emp not in processed_employees:
                    part_context = dict(base_context)
                    part_context["role"] = "participant"
                    events.append({
                        "employee_id": part_emp,
                        "source": "incidents",
                        "source_type": "incident",
                        "source_record_id": str(incident_id),
                        "action": "participate_incident_response",
                        "timestamp": str(timestamp) if timestamp else None,
                        "context": part_context,
                        "provenance_type": "Demonstrated",
                    })
                    processed_employees.add(part_emp)

    # 3. Reporter Event (if not already processed as responder or participant)
    if reporter_id and str(reporter_id).strip():
        rep_emp = str(reporter_id).strip()
        if rep_emp not in processed_employees:
            rep_context = dict(base_context)
            rep_context["role"] = "reporter"
            events.append({
                "employee_id": rep_emp,
                "source": "incidents",
                "source_type": "incident",
                "source_record_id": str(incident_id),
                "action": "report_incident",
                "timestamp": str(timestamp) if timestamp else None,
                "context": rep_context,
                "provenance_type": "Observed",
            })
            processed_employees.add(rep_emp)

    return events


def extract_batch_incident_events(raw_incidents: List[Union[Dict[str, Any], Any]]) -> List[Dict[str, Any]]:
    """Batch extract normalized events from a list of raw incident records."""
    all_events = []
    for raw_incident in raw_incidents:
        events = extract_incident_events(raw_incident)
        all_events.extend(events)
    return all_events
