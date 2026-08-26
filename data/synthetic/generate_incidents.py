"""
Script to generate data/synthetic/incidents.json containing the 15 AcmePay operational incidents (INC-501 through INC-515).
Does NOT modify data/raw/incidents/incidents.json or any source files.
"""

import os
import json

def generate_incidents():
    incidents = [
        {
            "incident_id": "INC-501",
            "reporter_id": "E01",
            "lead_responder_id": "E08",
            "participants": ["E08", "E02"],
            "timestamp": "2023-04-12T14:30:00Z",
            "resolved_at": "2023-04-12T15:45:00Z",
            "title": "OAuth2 Bearer token signing key vault lock contention",
            "severity": "SEV-1",
            "service": "auth-service",
            "summary": "KMS vault connection timeout caused 500 error spikes on merchant token validation endpoint.",
            "root_cause": "Unindexed key rotation lock check in KMS token vault worker.",
            "action_items": [
                "Rolled back KMS key rotation worker to release v1.4.2",
                "Added index on kms_key_id column",
                "Updated token vault timeout configuration to 5s"
            ]
        },
        {
            "incident_id": "INC-502",
            "reporter_id": "E03",
            "lead_responder_id": "E04",
            "participants": ["E04", "E01", "E12"],
            "timestamp": "2023-08-19T09:15:00Z",
            "resolved_at": "2023-08-19T10:30:00Z",
            "title": "Payment intent state machine retry deadlock during acquirer outage",
            "severity": "SEV-1",
            "service": "payment-service",
            "summary": "Acquirer timeout triggered concurrent state machine locks on charge authorization retry.",
            "root_cause": "Mutex deadlock between retry worker and charge status state machine transition.",
            "action_items": [
                "Applied hotfix patch to state_machine.go releasing mutex lock",
                "Configured exponential backoff jitter on acquirer retries"
            ]
        },
        {
            "incident_id": "INC-503",
            "reporter_id": "E07",
            "lead_responder_id": "E14",
            "participants": ["E14", "E04"],
            "timestamp": "2023-11-04T18:20:00Z",
            "resolved_at": "2023-11-04T19:10:00Z",
            "title": "Fraud risk evaluator score calculation latency breach",
            "severity": "SEV-2",
            "service": "fraud-service",
            "summary": "Sliding window velocity checker stalled transaction authorization requests past 500ms timeout.",
            "root_cause": "Uncached IP subnet blacklist lookups on high-volume card token requests.",
            "action_items": [
                "Cached card token velocity scores in Redis key store",
                "Optimized subnet matching algorithm in risk_evaluator.py"
            ]
        },
        {
            "incident_id": "INC-504",
            "reporter_id": "E05",
            "lead_responder_id": "E10",
            "participants": ["E10", "E16"],
            "timestamp": "2024-02-15T01:40:00Z",
            "resolved_at": "2024-02-15T02:55:00Z",
            "title": "Double-entry ledger journal debit/credit lock contention during midnight batch",
            "severity": "SEV-1",
            "service": "ledger-service",
            "summary": "Concurrent merchant debit and credit entries caused journal account row locks.",
            "root_cause": "Non-sequential account ID locking in double-entry balance verifier worker.",
            "action_items": [
                "Sorted journal account IDs before executing debit/credit lock acquisition",
                "Ran VerifyJournalBalance() sanity check"
            ]
        },
        {
            "incident_id": "INC-505",
            "reporter_id": "E02",
            "lead_responder_id": "E01",
            "participants": ["E01", "E11", "E15"],
            "timestamp": "2024-05-20T11:05:00Z",
            "resolved_at": "2024-05-20T11:50:00Z",
            "title": "API Gateway 504 Gateway Timeout on v2 payment intent proxy",
            "severity": "SEV-2",
            "service": "api-gateway",
            "summary": "Ingress reverse proxy connection pool exhaustion under sudden traffic surge.",
            "root_cause": "Token bucket rate limiter bucket capacity misconfiguration.",
            "action_items": [
                "Increased gateway proxy connection pool capacity to 500",
                "Reconfigured token bucket burst rate limiter parameters"
            ]
        },
        {
            "incident_id": "INC-506",
            "reporter_id": "E19",
            "lead_responder_id": "E04",
            "participants": ["E04", "E05", "E16"],
            "timestamp": "2024-09-10T16:30:00Z",
            "resolved_at": "2024-09-10T17:40:00Z",
            "title": "Partner bank ACH clearing file header formatting error",
            "severity": "SEV-2",
            "service": "settlement-service",
            "summary": "Partner clearing bank rejected daily batch payout file due to missing header column.",
            "root_cause": "Unannounced ACH file format specification change by partner bank.",
            "action_items": [
                "Updated ach_clearing.go batch file generator format",
                "Added automated pre-submission ACH header validator"
            ]
        },
        {
            "incident_id": "INC-507",
            "reporter_id": "E06",
            "lead_responder_id": "E03",
            "participants": ["E03", "E06", "E11"],
            "timestamp": "2024-11-18T08:00:00Z",
            "resolved_at": "2024-11-18T08:45:00Z",
            "title": "Kubernetes ArgoRollout canary traffic shifting stalled at 10% step",
            "severity": "SEV-2",
            "service": "deployment-service",
            "summary": "ArgoRollout controller failed to promote canary release automatically after metric evaluation.",
            "root_cause": "Prometheus metric query timeout during 10% canary step evaluation.",
            "action_items": [
                "Manually promoted release to 100% production step",
                "Adjusted canary metric query evaluation window"
            ]
        },
        {
            "incident_id": "INC-508",
            "reporter_id": "E17",
            "lead_responder_id": "E02",
            "participants": ["E02", "E07", "E20"],
            "timestamp": "2025-01-22T13:20:00Z",
            "resolved_at": "2025-01-22T14:05:00Z",
            "title": "Merchant KYC tax ID validation worker queue backpressure",
            "severity": "SEV-3",
            "service": "user-service",
            "summary": "KYC document validation requests stalled due to third-party verification API throttle.",
            "root_cause": "Missing asynchronous retry queue for tax ID verification worker.",
            "action_items": [
                "Flushed stalled KYC verification queue",
                "Implemented async exponential backoff for tax ID verifier worker"
            ]
        },
        {
            "incident_id": "INC-509",
            "reporter_id": "E12",
            "lead_responder_id": "E07",
            "participants": ["E07", "E12"],
            "timestamp": "2025-04-14T20:10:00Z",
            "resolved_at": "2025-04-14T21:00:00Z",
            "title": "Outbound merchant webhook dispatcher delivery queue stall",
            "severity": "SEV-2",
            "service": "notification-service",
            "summary": "Merchant payment webhook event notifications delayed by 45 minutes.",
            "root_cause": "Uncapped connection timeout on unresponsive merchant webhook endpoint.",
            "action_items": [
                "Enforced 5s timeout on outbound HTTP webhook client",
                "Flushed webhook dead-letter queue worker"
            ]
        },
        {
            "incident_id": "INC-510",
            "reporter_id": "E09",
            "lead_responder_id": "E10",
            "participants": ["E10", "E05", "E19"],
            "timestamp": "2025-07-09T03:15:00Z",
            "resolved_at": "2025-07-09T04:30:00Z",
            "title": "Merchant clearing account balance mismatch during month-end reconciliation",
            "severity": "SEV-1",
            "service": "ledger-service",
            "summary": "Ledger balance verification reported $12,450 debit/credit mismatch on high-volume merchant.",
            "root_cause": "Race condition in asynchronous settlement fee debit posting worker.",
            "action_items": [
                "Executed manual balance reconciliation script",
                "Applied atomic transaction block around balance_verifier.go"
            ]
        },
        {
            "incident_id": "INC-511",
            "reporter_id": "E15",
            "lead_responder_id": "E06",
            "participants": ["E06", "E01", "E13"],
            "timestamp": "2025-10-03T15:45:00Z",
            "resolved_at": "2025-10-03T16:25:00Z",
            "title": "API Gateway OpenAPI schema validation memory leak",
            "severity": "SEV-2",
            "service": "api-gateway",
            "summary": "Gateway proxy worker pods restarted due to OOM kill during JSON payload validation.",
            "root_cause": "Repeated JSON schema compilation on every HTTP request in ingress_proxy.go.",
            "action_items": [
                "Cached compiled OpenAPI 3.0 schema in gateway proxy memory",
                "Increased pod memory limit"
            ]
        },
        {
            "incident_id": "INC-512",
            "reporter_id": "E18",
            "lead_responder_id": "E03",
            "participants": ["E03", "E06", "E18"],
            "timestamp": "2025-12-11T22:00:00Z",
            "resolved_at": "2025-12-11T22:40:00Z",
            "title": "Prometheus latency alert manager rule evaluation failure",
            "severity": "SEV-2",
            "service": "monitoring-service",
            "summary": "P99 payment gateway latency alert failed to trigger PagerDuty on-call page.",
            "root_cause": "Syntax error in Prometheus payment_alerts.yml rule expression.",
            "action_items": [
                "Patched Prometheus alert rule syntax",
                "Triggered test alert to verify PagerDuty escalation route"
            ]
        },
        {
            "incident_id": "INC-513",
            "reporter_id": "E19",
            "lead_responder_id": "E05",
            "participants": ["E05", "E09", "E19"],
            "timestamp": "2026-02-17T17:10:00Z",
            "resolved_at": "2026-02-17T18:00:00Z",
            "title": "Merchant settlement report CSV exporter buffer overflow",
            "severity": "SEV-3",
            "service": "reporting-service",
            "summary": "Large monthly CSV audit log export failed for high-volume enterprise merchant.",
            "root_cause": "Buffering 1,000,000 transaction rows into memory before CSV stream output.",
            "action_items": [
                "Implemented streaming line-by-line CSV exporter in audit_exporter.py",
                "Added row pagination limiter"
            ]
        },
        {
            "incident_id": "INC-514",
            "reporter_id": "E02",
            "lead_responder_id": "E09",
            "participants": ["E09", "E02"],
            "timestamp": "2026-05-08T10:30:00Z",
            "resolved_at": "2026-05-08T11:45:00Z",
            "title": "PCI-DSS Primary Account Number (PAN) sanitizer regex bypass warning",
            "severity": "SEV-1",
            "service": "compliance-service",
            "summary": "Automated security scanner flagged unmasked 16-digit card number in audit log stdout.",
            "root_cause": "Regex pattern in pci_sanitizer.go failed to match hyphenated card format.",
            "action_items": [
                "Updated PCI PAN masking regex in pci_sanitizer.go",
                "Purged unmasked log entries from compliance archive"
            ]
        },
        {
            "incident_id": "INC-515",
            "reporter_id": "E12",
            "lead_responder_id": "E01",
            "participants": ["E01", "E04", "E13"],
            "timestamp": "2026-08-11T14:15:00Z",
            "resolved_at": "2026-08-11T15:00:00Z",
            "title": "Acquirer authorization retry exponential backoff queue stall",
            "severity": "SEV-2",
            "service": "payment-service",
            "summary": "PaymentIntent retries stalled during acquirer network maintenance window.",
            "root_cause": "Acquirer error code 503 treated as non-retryable terminal status.",
            "action_items": [
                "Updated retry_engine.go error code classification mapping",
                "Flushed payment intent retry queue"
            ]
        }
    ]

    out_path = 'data/synthetic/incidents.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(incidents, f, indent=2)

    print(f"Successfully generated {len(incidents)} synthetic AcmePay incidents to {out_path}")

if __name__ == "__main__":
    generate_incidents()
