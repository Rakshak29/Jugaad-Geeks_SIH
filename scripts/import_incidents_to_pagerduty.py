"""
AcmePay Incident Importer for PagerDuty Events API V2.

Reads synthetic AcmePay incident records from data/synthetic/incidents.json,
maps them to PagerDuty Events API V2 payload schema, and supports a DRY RUN mode.
"""

import os
import sys
import json
import base64
import ssl
import argparse
import urllib.request

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

SEVERITY_MAP = {
    "SEV-1": "critical",
    "SEV-2": "error",
    "SEV-3": "warning",
}

def load_env_vars():
    """Load environment variables from .env if present."""
    env_path = '.env' if os.path.exists('.env') else '.env.example'
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip().strip('\"\'')

def map_incident_to_pagerduty_payload(incident: dict, routing_key: str) -> dict:
    """
    Map a synthetic AcmePay incident JSON record to PagerDuty Events API V2 schema.
    """
    incident_id = incident.get("incident_id")
    title = incident.get("title", "")
    service = incident.get("service", "acmepay-service")
    severity_raw = incident.get("severity", "SEV-2")
    pd_severity = SEVERITY_MAP.get(severity_raw.upper(), "error")
    
    reporter_id = incident.get("reporter_id")
    lead_responder_id = incident.get("lead_responder_id")
    participants = incident.get("participants", [])
    summary = incident.get("summary", "")
    root_cause = incident.get("root_cause", "")
    action_items = incident.get("action_items", [])
    timestamp = incident.get("timestamp")
    resolved_at = incident.get("resolved_at")

    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": incident_id,
        "payload": {
            "summary": title,
            "source": service,
            "severity": pd_severity,
            "timestamp": timestamp,
            "custom_details": {
                "incident_id": incident_id,
                "reporter": reporter_id,
                "reporter_id": reporter_id,
                "lead_responder": lead_responder_id,
                "lead_responder_id": lead_responder_id,
                "participants": participants,
                "service": service,
                "module": service,
                "summary": summary,
                "root_cause": root_cause,
                "action_items": action_items,
                "timestamps": {
                    "created_at": timestamp,
                    "resolved_at": resolved_at
                }
            }
        }
    }
    return payload

def send_pagerduty_event(payload: dict) -> dict:
    """Send payload to PagerDuty Events API V2 via HTTPS with certificate verification."""
    url = "https://events.pagerduty.com/v2/enqueue"
    data_bytes = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, context=SSL_CONTEXT) as response:
        return {
            "status_code": response.status,
            "body": json.loads(response.read().decode('utf-8'))
        }

def main():
    parser = argparse.ArgumentParser(description="AcmePay PagerDuty Incident Importer")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Run in dry-run mode without sending events to PagerDuty")
    parser.add_argument("--send", action="store_true", help="Explicitly send events to PagerDuty (disables dry-run)")
    parser.add_argument("--incident-id", type=str, help="Specific incident ID to process (e.g. INC-501)")
    parser.add_argument("--exclude-id", type=str, help="Exclude specific incident ID (e.g. INC-501)")
    args = parser.parse_args()

    load_env_vars()

    routing_key = os.environ.get("PAGERDUTY_INTEGRATION_KEY")
    if not routing_key:
        print("ERROR: PAGERDUTY_INTEGRATION_KEY is not set in environment or .env file.")
        sys.exit(1)

    incidents_path = "data/synthetic/incidents.json"
    if not os.path.exists(incidents_path):
        print(f"ERROR: Incident file not found at {incidents_path}")
        sys.exit(1)

    with open(incidents_path) as f:
        incidents = json.load(f)

    if args.incident_id:
        incidents = [i for i in incidents if i.get("incident_id") == args.incident_id]
        if not incidents:
            print(f"ERROR: Incident {args.incident_id} not found in {incidents_path}")
            sys.exit(1)

    if args.exclude_id:
        incidents = [i for i in incidents if i.get("incident_id") != args.exclude_id]


    is_dry_run = not args.send

    print(f"=== ACMEPAY PAGERDUTY IMPORTER ===")
    print(f"Total Incidents Selected: {len(incidents)}")
    print(f"Execution Mode: {'DRY RUN (No events sent)' if is_dry_run else 'LIVE SEND'}")

    for idx, incident in enumerate(incidents):
        payload = map_incident_to_pagerduty_payload(incident, routing_key)
        
        print(f"\n--- Incident [{idx+1}/{len(incidents)}]: {incident.get('incident_id')} ---")
        if is_dry_run:
            print("Generated PagerDuty Event Payload:")
            # Redact raw routing key for display safety
            display_payload = json.loads(json.dumps(payload))
            display_payload["routing_key"] = "[REDACTED_PAGERDUTY_INTEGRATION_KEY]"
            print(json.dumps(display_payload, indent=2))
        else:
            print(f"Sending event {incident.get('incident_id')} to PagerDuty Events API V2...")
            res = send_pagerduty_event(payload)
            print(f"Response Status: {res['status_code']}")
            print(f"Response Body: {json.dumps(res['body'], indent=2)}")

if __name__ == "__main__":
    main()
