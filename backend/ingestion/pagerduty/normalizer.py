"""
PagerDuty Incident Normalization Module.

Reads raw PagerDuty ingestion payload from data/raw/pagerduty/incidents.json,
extracts authoritative internal employee IDs (E01-E20) from trigger log details
and custom payloads, maps internal IDs to canonical full names using data/synthetic/blueprint.yaml,
and produces compact, flat evidence-event records conforming strictly to the evidence schema.

Saves output atomically to data/normalized/pagerduty/incidents.json.
"""

import os
import json
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

BLUEPRINT_PATH = "data/synthetic/blueprint.yaml"
RAW_PAGERDUTY_FILE = "data/raw/pagerduty/incidents.json"
NORMALIZED_PAGERDUTY_DIR = "data/normalized/pagerduty"
NORMALIZED_PAGERDUTY_FILE = os.path.join(NORMALIZED_PAGERDUTY_DIR, "incidents.json")


class PagerDutyNormalizationError(Exception):
    """Exception raised when PagerDuty incident normalization fails."""
    pass


def load_employee_mappings(blueprint_filepath: str = BLUEPRINT_PATH) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Dynamically load employee records from blueprint.yaml and build bidirectional lookup dictionaries.

    Returns:
      (id_to_name, handle_to_id)
      - id_to_name: {'E01': 'Rakshak Shetty', 'E02': 'Keyuri Sheth', ...}
      - handle_to_id: {'rakshak shetty': 'E01', 'rakshak.shetty': 'E01', ...}
    """
    id_to_name: Dict[str, str] = {}
    handle_to_id: Dict[str, str] = {}

    if not os.path.exists(blueprint_filepath):
        return id_to_name, handle_to_id

    # Parse blueprint.yaml using line inspection to avoid external dependencies
    try:
        current_emp: Dict[str, str] = {}
        with open(blueprint_filepath, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str.startswith("- id:") or line_str.startswith("employees:"):
                    if current_emp.get("id") and current_emp.get("full_name"):
                        emp_id = current_emp["id"].strip()
                        fn = current_emp["full_name"].strip()
                        id_to_name[emp_id] = fn
                        id_to_name[emp_id.lower()] = fn
                        handle_to_id[emp_id.lower()] = emp_id

                        for k in ("full_name", "email", "jira_username", "github_handle", "incident_alias", "deploy_actor"):
                            v = current_emp.get(k)
                            if v and isinstance(v, str) and v.strip():
                                cv = v.strip().lower()
                                handle_to_id[cv] = emp_id
                                if k == "email" and "@" in cv:
                                    handle_to_id[cv.split("@")[0]] = emp_id
                    current_emp = {}
                    if line_str.startswith("- id:"):
                        current_emp["id"] = line_str.split(":", 1)[1].strip()
                elif ":" in line_str and not line_str.startswith("#"):
                    parts = line_str.split(":", 1)
                    k_clean = parts[0].strip().lstrip("- ").strip()
                    v_clean = parts[1].strip().strip("\"'")
                    if k_clean and v_clean:
                        current_emp[k_clean] = v_clean

        if current_emp.get("id") and current_emp.get("full_name"):
            emp_id = current_emp["id"].strip()
            fn = current_emp["full_name"].strip()
            id_to_name[emp_id] = fn
            id_to_name[emp_id.lower()] = fn
            handle_to_id[emp_id.lower()] = emp_id

            for k in ("full_name", "email", "jira_username", "github_handle", "incident_alias", "deploy_actor"):
                v = current_emp.get(k)
                if v and isinstance(v, str) and v.strip():
                    cv = v.strip().lower()
                    handle_to_id[cv] = emp_id
                    if k == "email" and "@" in cv:
                        handle_to_id[cv.split("@")[0]] = emp_id
    except Exception:
        pass

    return id_to_name, handle_to_id


def extract_incident_internal_details(raw_inc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract internal telemetry details (lead_responder_id, reporter_id, participants, etc.)
    from first_trigger_log_entry or custom_details.
    """
    # 1. Check first_trigger_log_entry channel details
    log_entry = raw_inc.get("first_trigger_log_entry", {})
    if isinstance(log_entry, dict):
        channel = log_entry.get("channel", {})
        if isinstance(channel, dict):
            details = channel.get("details") or channel.get("cef_details", {}).get("details", {})
            if isinstance(details, dict) and details:
                return details

    # 2. Check first_trigger_log_entries array
    log_entries = raw_inc.get("first_trigger_log_entries", [])
    if isinstance(log_entries, list) and log_entries:
        first_entry = log_entries[0]
        if isinstance(first_entry, dict):
            channel = first_entry.get("channel", {})
            if isinstance(channel, dict):
                details = channel.get("details") or channel.get("cef_details", {}).get("details", {})
                if isinstance(details, dict) and details:
                    return details

    # 3. Check custom_details root
    custom_details = raw_inc.get("custom_details")
    if isinstance(custom_details, dict) and custom_details:
        return custom_details

    return {}


def resolve_canonical_identities(
    raw_inc: Dict[str, Any],
    id_to_name: Dict[str, str],
    handle_to_id: Dict[str, str]
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Resolve internal canonical employee identities for an incident.

    Returns:
      (lead_id, lead_name, reporter_id, reporter_name)
    """
    details = extract_incident_internal_details(raw_inc)

    # 1. Lead responder
    lead_id = details.get("lead_responder_id") or details.get("lead_responder")
    lead_name = id_to_name.get(str(lead_id).strip(), id_to_name.get(str(lead_id).strip().lower())) if lead_id else None

    # Fallback to PagerDuty assignee if lead_responder_id missing
    if not lead_id:
        assignments = raw_inc.get("assignments", [])
        if isinstance(assignments, list) and assignments:
            assignee = assignments[0].get("assignee", {}) if isinstance(assignments[0], dict) else {}
            if isinstance(assignee, dict):
                for cand in (assignee.get("email"), assignee.get("name"), assignee.get("id")):
                    if cand and str(cand).strip().lower() in handle_to_id:
                        lead_id = handle_to_id[str(cand).strip().lower()]
                        lead_name = id_to_name.get(lead_id)
                        break

    # 2. Reporter
    reporter_id = details.get("reporter_id") or details.get("reporter")
    reporter_name = id_to_name.get(str(reporter_id).strip(), id_to_name.get(str(reporter_id).strip().lower())) if reporter_id else None

    return (
        str(lead_id) if lead_id else None,
        lead_name,
        str(reporter_id) if reporter_id else None,
        reporter_name
    )


def normalize_pagerduty_incident(
    raw_inc: Dict[str, Any],
    source_url: str = "",
    service_id: str = "",
    id_to_name: Optional[Dict[str, str]] = None,
    handle_to_id: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Normalize a raw PagerDuty incident into a compact evidence-event record.

    Conforms strictly to evidence event schema:
    {
      "employee_id": "E03",
      "employee_name": "Kshitij Naidu",
      "source": "pagerduty",
      "source_type": "incident",
      "source_record_id": "Q0BR6INWL2DY4T",
      "action": "lead_incident_response",
      "timestamp": "2026-08-26T19:04:37Z",
      "provenance_type": "Demonstrated",
      "context": { ... }
    }
    """
    if not isinstance(raw_inc, dict):
        raise PagerDutyNormalizationError(f"Invalid incident object type: {type(raw_inc)}")

    if id_to_name is None or handle_to_id is None:
        id_to_name, handle_to_id = load_employee_mappings()

    # 1. Identifier resolution
    pd_id = raw_inc.get("id") or raw_inc.get("dedup_key") or "UNKNOWN"
    details = extract_incident_internal_details(raw_inc)

    # 2. Canonical Identity Resolution
    lead_id, lead_name, reporter_id, reporter_name = (
        resolve_canonical_identities(raw_inc, id_to_name, handle_to_id)
    )

    # 3. Title & Service resolution
    title = raw_inc.get("title") or raw_inc.get("summary") or details.get("summary") or "Untitled Incident"
    service_obj = raw_inc.get("service")
    if isinstance(service_obj, dict):
        service_name = service_obj.get("summary") or service_obj.get("name") or service_obj.get("id") or service_id
    else:
        service_name = str(service_obj) if service_obj else (details.get("service") or service_id)

    # 4. Severity & Status
    urgency = str(raw_inc.get("urgency") or "").lower()
    severity = details.get("severity") or raw_inc.get("severity") or ("SEV-1" if urgency == "high" else "SEV-2")
    status = raw_inc.get("status", "resolved")
    created_at = details.get("timestamps", {}).get("created_at") or raw_inc.get("created_at") or raw_inc.get("timestamp")

    # 5. Context
    context = {
        "title": str(title),
        "severity": str(severity),
        "service": str(service_name),
        "summary": str(details.get("summary") or raw_inc.get("description") or title),
        "status": str(status),
        "service_id": str(service_id),
        "source_url": str(source_url),
        "lead_responder_id": lead_id,
        "lead_responder_name": lead_name,
        "reporter_id": reporter_id,
        "reporter_name": reporter_name
    }

    if details.get("root_cause"):
        context["root_cause"] = details["root_cause"]
    if details.get("action_items"):
        context["action_items"] = details["action_items"]

    return {
        "employee_id": lead_id,
        "employee_name": lead_name,
        "source": "pagerduty",
        "source_type": "incident",
        "source_record_id": str(pd_id),
        "action": "lead_incident_response",
        "timestamp": str(created_at) if created_at else None,
        "provenance_type": "Demonstrated",
        "context": context
    }


def normalize_pagerduty_dataset(
    raw_filepath: str = RAW_PAGERDUTY_FILE,
    output_filepath: str = NORMALIZED_PAGERDUTY_FILE,
    blueprint_filepath: str = BLUEPRINT_PATH
) -> str:
    """
    Read raw PagerDuty ingestion JSON and write compact normalized dataset atomically.

    Overwrites destination data/normalized/pagerduty/incidents.json completely.
    Does NOT overwrite if raw data is missing, malformed, or normalization fails.
    """
    if not os.path.exists(raw_filepath):
        raise PagerDutyNormalizationError(f"Raw PagerDuty ingestion file not found: {raw_filepath}")

    try:
        with open(raw_filepath, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        raise PagerDutyNormalizationError(f"Failed to read/parse raw JSON file {raw_filepath}: {e}") from e

    if not isinstance(raw_data, dict):
        raise PagerDutyNormalizationError("Raw JSON payload must be a top-level dictionary")

    source_url = raw_data.get("source_url", "")
    service_id = raw_data.get("service_id", "")
    raw_incidents = raw_data.get("incidents")

    if raw_incidents is None or not isinstance(raw_incidents, list):
        raise PagerDutyNormalizationError("Raw JSON payload missing 'incidents' array")

    id_to_name, handle_to_id = load_employee_mappings(blueprint_filepath)

    normalized_events = []
    for idx, raw_inc in enumerate(raw_incidents):
        try:
            norm_event = normalize_pagerduty_incident(
                raw_inc,
                source_url=source_url,
                service_id=service_id,
                id_to_name=id_to_name,
                handle_to_id=handle_to_id
            )
            normalized_events.append(norm_event)
        except Exception as e:
            raise PagerDutyNormalizationError(f"Error normalizing raw incident at index {idx}: {e}") from e

    # 1-to-1 record count assertion
    if len(normalized_events) != len(raw_incidents):
        raise PagerDutyNormalizationError(
            f"Normalization count mismatch: {len(raw_incidents)} raw vs {len(normalized_events)} normalized"
        )

    # Atomic write to temp file then replace
    target_dir = os.path.dirname(output_filepath)
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix="pagerduty_norm_", suffix=".tmp")

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(normalized_events, f, indent=2)
        os.replace(tmp_path, output_filepath)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise PagerDutyNormalizationError(f"Failed to write normalized JSON file {output_filepath}: {e}") from e

    return os.path.abspath(output_filepath)
