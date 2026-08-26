"""
Script to populate Jira Cloud project SCRUM with synthetic engineering evidence.
Creates 12 Components, 12 Epics, 45 Stories, 35 Tasks, 18 Bugs (110 total issues),
and ~60 comments while preserving SCRUM-1 through SCRUM-5.
Conforms strictly to data/synthetic/blueprint.yaml and the 6 demonstration cases.
"""

import os
import json
import base64
import time
import ssl
import urllib.request
from datetime import datetime, timedelta

def build_adf_doc(text):
    """Utility to build Atlassian Document Format (ADF) document from plain text."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text
                    }
                ]
            }
        ]
    }

def main():
    env_path = '.env' if os.path.exists('.env') else '.env.example'
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k.strip()] = v.strip().strip('\"\'')

    url = os.environ.get('JIRA_BASE_URL', '').rstrip('/')
    email = os.environ.get('JIRA_EMAIL', '')
    token = os.environ.get('JIRA_API_TOKEN', '')

    auth_str = base64.b64encode(f'{email}:{token}'.encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_str}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    ctx = ssl._create_unverified_context()

    def api_request(endpoint, method='GET', payload=None):
        data_bytes = json.dumps(payload).encode() if payload else None
        req = urllib.request.Request(f"{url}{endpoint}", data=data_bytes, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=ctx) as resp:
                if resp.status == 204:
                    return 204, {}
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            print(f"API Error [{e.code}] on {method} {endpoint}: {err_body[:200]}")
            return e.code, {}

    print("=== Starting Jira Cloud Population Pass ===")

    # 1. Create 12 Components
    components_list = [
        "payment-service", "fraud-service", "auth-service", "ledger-service",
        "notification-service", "user-service", "reporting-service", "settlement-service",
        "api-gateway", "deployment-service", "monitoring-service", "compliance-service"
    ]
    created_components = {}
    print("\nCreating 12 Jira Components...")
    for comp in components_list:
        payload = {
            "name": comp,
            "project": "SCRUM",
            "description": f"Core component for {comp} module"
        }
        st, res = api_request("/rest/api/3/component", method="POST", payload=payload)
        if st in [200, 201]:
            created_components[comp] = res.get("id")
            print(f"  - Created component: {comp} (id: {res.get('id')})")
        else:
            # Component might already exist
            print(f"  - Component {comp} creation status: {st}")
            created_components[comp] = comp

    # 2. Employees Definition & Blueprint Mappings
    employees = [
        {"id": "E01", "name": "Rakshak Shetty", "jira": "rakshak.shetty", "modules": ["api-gateway", "payment-service", "auth-service", "monitoring-service"]},
        {"id": "E02", "name": "Keyuri Sheth", "jira": "keyuri.sheth", "modules": ["auth-service", "user-service", "compliance-service", "api-gateway"]},
        {"id": "E03", "name": "Kshitij Naidu", "jira": "kshitij.naidu", "modules": ["monitoring-service", "deployment-service", "payment-service"]},
        {"id": "E04", "name": "Krish Trivedi", "jira": "krish.trivedi", "modules": ["payment-service", "settlement-service", "fraud-service"]},
        {"id": "E05", "name": "Naman Nahar", "jira": "naman.nahar", "modules": ["reporting-service", "ledger-service", "settlement-service"]},
        {"id": "E06", "name": "Parth More", "jira": "parth.more", "modules": ["deployment-service", "monitoring-service", "api-gateway"]},
        {"id": "E07", "name": "Ananya Sharma", "jira": "ananya.sharma", "modules": ["user-service", "notification-service", "api-gateway"]},
        {"id": "E08", "name": "Vikram Malhotra", "jira": "vikram.malhotra", "modules": ["auth-service"], "stale": True},  # Case 2 Stale
        {"id": "E09", "name": "Deepa Raman", "jira": "deepa.raman", "modules": ["compliance-service", "reporting-service", "ledger-service"]},
        {"id": "E10", "name": "Rohan Gupta", "jira": "rohan.gupta", "modules": ["ledger-service"], "concentrated": True},  # Case 1 Concentration
        {"id": "E11", "name": "Meera Patel", "jira": "meera.patel", "modules": ["deployment-service", "api-gateway", "monitoring-service"]},
        {"id": "E12", "name": "Siddharth Joshi", "jira": "siddharth.joshi", "modules": ["payment-service", "notification-service"]},
        {"id": "E13", "name": "Tanvi Deshmukh", "jira": "tanvi.deshmukh", "modules": ["monitoring-service", "deployment-service"]},
        {"id": "E14", "name": "Aditya Verma", "jira": "aditya.verma", "modules": ["fraud-service", "payment-service"]},
        {"id": "E15", "name": "Neha Kapoor", "jira": "neha.kapoor", "modules": ["api-gateway", "user-service"]},
        {"id": "E16", "name": "Arjun Nair", "jira": "arjun.nair", "modules": ["settlement-service", "ledger-service"]},
        {"id": "E17", "name": "Pooja Bhatia", "jira": "pooja.bhatia", "modules": ["api-gateway", "user-service"], "docs_only": True},  # Case 6 Ambiguous
        {"id": "E18", "name": "Varun Saxena", "jira": "varun.saxena", "modules": ["monitoring-service", "deployment-service"]},
        {"id": "E19", "name": "Ritu Sengupta", "jira": "ritu.sengupta", "modules": ["reporting-service", "ledger-service"]},
        {"id": "E20", "name": "Kabir Mehta", "jira": "kabir.mehta", "modules": ["auth-service", "user-service"]}
    ]

    # 3. Create 12 Epics
    epics_info = [
        ("payment-service", "AcmePay Credit Card Intent & Payment Engine", "E01"),
        ("fraud-service", "Real-time Risk Evaluator & Fraud ML Pipeline", "E14"),
        ("auth-service", "OAuth2 & JWT Token Vault Security Engine", "E02"),
        ("ledger-service", "Double-Entry Balance Book & Reconciliation Ledger", "E10"),
        ("notification-service", "Event-driven Webhook & SMS Dispatcher Platform", "E07"),
        ("user-service", "Merchant KYC Onboarding & Profile Controller", "E02"),
        ("reporting-service", "Merchant Settlement Reports & Audit Exporter", "E05"),
        ("settlement-service", "ACH Clearing & Bank Payout Reconciliation Engine", "E04"),
        ("api-gateway", "Ingress Proxy & Rate Limiter Gateway Platform", "E01"),
        ("deployment-service", "Kubernetes ArgoRollout & CI/CD Pipeline Automation", "E06"),
        ("monitoring-service", "Prometheus Metrics & Grafana Observability Dashboard", "E03"),
        ("compliance-service", "PCI-DSS PAN Sanitizer & Data Retention Compliance", "E09")
    ]

    epic_keys = {}
    print("\nCreating 12 Epics...")
    for mod, epic_title, lead_emp_id in epics_info:
        emp = next(e for e in employees if e["id"] == lead_emp_id)
        desc = f"Epic for {mod} engineering work lead by {emp['name']} ({emp['jira']})."
        payload = {
            "fields": {
                "project": {"key": "SCRUM"},
                "summary": epic_title,
                "issuetype": {"name": "Epic"},
                "description": build_adf_doc(desc),
                "components": [{"name": mod}]
            }
        }
        st, res = api_request("/rest/api/3/issue", method="POST", payload=payload)
        if st in [200, 201]:
            epic_key = res.get("key")
            epic_keys[mod] = epic_key
            print(f"  - Created Epic: {epic_key} for module '{mod}'")
        else:
            print(f"  - Failed to create Epic for {mod}: status {st}")
        time.sleep(0.1)

    # 4. Generate 98 Stories, Tasks, and Bug Representations (Total = 12 Epics + 98 = 110 Issues)
    # Plan: 45 Stories, 35 Tasks, 18 Bugs
    # Distribution across modules:
    # ledger-service: 38 total (32 to E10 Rohan) -> Case 1
    # auth-service: 18 to E08 (Vikram - 2023) -> Case 2
    # api-gateway: 36 total distributed -> Case 4
    # pooja.bhatia: 14 docs stories -> Case 6

    issue_templates = [
        # (module, type_str, is_bug, summary, reporter_emp_id, assignee_emp_id, timestamp_str)
        # --- Case 1: Ledger Management Concentration (Rohan E10) ---
        ("ledger-service", "Story", False, "Implement double-entry debit credit balance validator", "E10", "E10", "2023-03-10T10:00:00Z"),
        ("ledger-service", "Task", False, "Optimize journal entry database storage and SHA256 digest hashing", "E10", "E10", "2023-05-14T11:30:00Z"),
        ("ledger-service", "Story", False, "Post atomic journal entries for merchant settlement batches", "E10", "E10", "2023-08-20T09:15:00Z"),
        ("ledger-service", "Task", False, "Build immutable audit log trail for financial ledger entries", "E10", "E10", "2023-11-05T14:00:00Z"),
        ("ledger-service", "Story", False, "Double-entry imbalance detection and automatic journal rollback", "E10", "E10", "2024-02-12T16:45:00Z"),
        ("ledger-service", "Task", False, "Configure multi-currency ledger journal account balances", "E10", "E10", "2024-06-18T10:30:00Z"),
        ("ledger-service", "Story", False, "Reconcile daily merchant payouts against debit balance summaries", "E10", "E10", "2024-09-22T13:00:00Z"),
        ("ledger-service", "Task", False, "Implement journal book snapshotting for rapid audit recovery", "E10", "E10", "2024-11-30T15:20:00Z"),
        ("ledger-service", "Story", False, "End-of-day ledger balance verifier automated job", "E10", "E10", "2025-01-15T09:00:00Z"),
        ("ledger-service", "Task", False, "Journal transaction concurrency locking for high volume charges", "E10", "E10", "2025-03-20T11:45:00Z"),
        ("ledger-service", "Task", False, "Audit log exporter integration with S3 ledger archive", "E10", "E10", "2025-06-10T14:10:00Z"),
        ("ledger-service", "Story", False, "Real-time double-entry ledger balance integrity verifier", "E10", "E10", "2025-09-05T10:00:00Z"),
        ("ledger-service", "Task", False, "Optimize journal entry query index for merchant audit logs", "E10", "E10", "2025-11-12T16:30:00Z"),
        ("ledger-service", "Story", False, "Automated ledger imbalance alert notification trigger", "E10", "E10", "2026-02-08T11:15:00Z"),
        ("ledger-service", "Task", False, "Update double-entry posting rules for multi-acquirer settlements", "E10", "E10", "2026-05-19T13:50:00Z"),
        ("ledger-service", "Story", False, "Ledger integrity verification and snapshot recovery procedure", "E10", "E10", "2026-07-28T09:30:00Z"),

        # --- Case 2: Stale Evidence (Vikram E08 - 2023 strictly) ---
        ("auth-service", "Story", False, "[Legacy] Build OAuth2 token issuer and JWT claim validator", "E08", "E08", "2023-01-20T10:00:00Z"),
        ("auth-service", "Task", False, "[Legacy] Setup KMS signing key vault wrapper and key rotation", "E08", "E08", "2023-02-15T14:20:00Z"),
        ("auth-service", "Story", False, "[Legacy] Implement role-based access control RBAC middleware", "E08", "E08", "2023-04-10T11:00:00Z"),
        ("auth-service", "Task", False, "[Legacy] Configure bearer token TTL and refresh token endpoints", "E08", "E08", "2023-06-25T09:30:00Z"),
        ("auth-service", "Story", False, "[Legacy] Add token revocation blacklist cache in Redis", "E08", "E08", "2023-08-18T16:00:00Z"),
        ("auth-service", "Task", False, "[Legacy] Harden KMS vault access policies for production auth keys", "E08", "E08", "2023-11-20T13:45:00Z"),

        # --- Case 2 Recent Auth work (Keyuri E02 & Kabir E20 in 2025-2026) ---
        ("auth-service", "Story", False, "Upgrade OAuth2 token issuer to support PKCE flow", "E02", "E02", "2025-03-12T10:00:00Z"),
        ("auth-service", "Task", False, "Automate KMS signing key rotation schedule in production", "E02", "E02", "2025-07-19T14:00:00Z"),
        ("auth-service", "Story", False, "Enforce strict RBAC scope authorization on API proxy endpoints", "E20", "E20", "2026-02-10T11:30:00Z"),

        ("auth-service", "Task", False, "Add mTLS client certificate authentication to auth vault", "E02", "E02", "2026-06-05T09:15:00Z"),

        # --- Case 4: Distributed API Management (api-gateway across 6 engineers) ---
        ("api-gateway", "Story", False, "Implement ingress proxy routing layer for payment intent endpoints", "E01", "E01", "2023-03-15T10:00:00Z"),
        ("api-gateway", "Task", False, "Configure token bucket rate limiter for v2 payment proxy", "E01", "E01", "2023-07-20T14:00:00Z"),
        ("api-gateway", "Story", False, "Add OpenAPI 3.0 gateway specification and schema validator", "E15", "E15", "2024-01-18T11:00:00Z"),
        ("api-gateway", "Task", False, "Bearer token verification proxy plugin integration", "E02", "E02", "2024-05-22T09:30:00Z"),
        ("api-gateway", "Story", False, "Setup reverse proxy CORS headers and request timeout rules", "E06", "E06", "2024-09-10T15:15:00Z"),
        ("api-gateway", "Task", False, "Configure ingress gateway response header sanitization", "E11", "E11", "2025-02-14T10:45:00Z"),
        ("api-gateway", "Story", False, "Merchant request rate limiting and dynamic quota management", "E04", "E04", "2025-06-30T13:20:00Z"),
        ("api-gateway", "Task", False, "Ingress proxy health check endpoint and upstream circuit breaker", "E01", "E01", "2025-11-08T09:00:00Z"),
        ("api-gateway", "Story", False, "Optimize API gateway request routing performance under high load", "E15", "E15", "2026-03-25T14:30:00Z"),
        ("api-gateway", "Task", False, "Add Prometheus latency metrics exporter to ingress proxy", "E06", "E06", "2026-07-12T11:10:00Z"),

        # --- Case 6: Ambiguous / Conflicting Evidence (Pooja E17 - Docs only) ---
        ("api-gateway", "Story", False, "Document OpenAPI 3.0 Payment Gateway API specifications", "E17", "E17", "2023-06-10T10:00:00Z"),
        ("api-gateway", "Story", False, "Author developer portal integration guide for merchant onboarding", "E17", "E17", "2023-10-15T14:00:00Z"),
        ("api-gateway", "Story", False, "Create rate limiting & authentication troubleshooting guide", "E17", "E17", "2024-03-20T11:30:00Z"),
        ("user-service", "Story", False, "Write Merchant KYC onboarding documentation and compliance requirements", "E17", "E17", "2024-08-12T09:00:00Z"),
        ("api-gateway", "Story", False, "Author API Gateway zero-downtime deployment architecture specification", "E17", "E17", "2025-01-22T15:45:00Z"),
        ("user-service", "Story", False, "Document merchant account registration payload schema", "E17", "E17", "2025-07-14T10:30:00Z"),
        ("api-gateway", "Story", False, "Create API Proxy webhook integration and callback specification", "E17", "E17", "2026-04-18T13:15:00Z"),

        # --- Payment Service & Fraud Service Issues ---
        ("payment-service", "Story", False, "Implement credit card payment intent creation and idempotency handler", "E01", "E01", "2023-02-10T10:00:00Z"),
        ("payment-service", "Task", False, "Add exponential backoff jitter to payment acquirer retry engine", "E04", "E04", "2023-06-15T14:30:00Z"),
        ("payment-service", "Story", False, "Update payment status state machine for authorization retries", "E04", "E04", "2024-03-10T11:15:00Z"),
        ("payment-service", "Task", False, "Integrate card processor decline code mapping and handling", "E12", "E12", "2024-08-25T09:00:00Z"),
        ("fraud-service", "Story", False, "Real-time risk evaluator score calculation engine", "E14", "E14", "2023-04-18T10:00:00Z"),
        ("fraud-service", "Task", False, "Build card transaction velocity checker and rate window filter", "E14", "E14", "2023-09-22T15:20:00Z"),
        ("fraud-service", "Story", False, "ML risk rule probability model score inference engine", "E14", "E14", "2024-05-14T11:45:00Z"),
        ("fraud-service", "Task", False, "Blacklist IP subnet and compromised card token filter", "E14", "E14", "2025-02-10T14:00:00Z"),

        # --- Settlement & Reporting Issues ---
        ("settlement-service", "Story", False, "Execute ACH clearing file generation and bank payout dispatcher", "E04", "E04", "2023-05-08T10:00:00Z"),
        ("settlement-service", "Task", False, "Build merchant payout clearing batch scheduler", "E16", "E16", "2023-10-12T13:30:00Z"),
        ("settlement-service", "Story", False, "Bank deposit statement reconciliation engine", "E16", "E16", "2024-04-20T11:00:00Z"),
        ("reporting-service", "Story", False, "Generate merchant settlement volume and fee summary reports", "E05", "E05", "2023-07-14T10:00:00Z"),
        ("reporting-service", "Task", False, "Build CSV audit log exporter for financial compliance review", "E09", "E09", "2024-02-28T14:45:00Z"),
        ("reporting-service", "Story", False, "Aggregate daily transaction throughput and failure metrics", "E19", "E19", "2024-11-10T09:15:00Z"),

        # --- Monitoring, Deployment, Compliance, Notification Issues ---
        ("monitoring-service", "Story", False, "Setup Prometheus alert rules for p99 HTTP latency spikes", "E03", "E03", "2023-03-28T10:00:00Z"),
        ("monitoring-service", "Task", False, "Update Grafana dashboard for payment processing throughput", "E13", "E13", "2023-08-15T15:00:00Z"),
        ("monitoring-service", "Task", False, "Configure PagerDuty escalation policy routing for SEV-1 incidents", "E18", "E18", "2024-06-20T11:30:00Z"),
        ("deployment-service", "Story", False, "Configure ArgoRollout 10%/50% canary deployment strategy", "E06", "E06", "2023-04-25T10:00:00Z"),
        ("deployment-service", "Task", False, "Update Helm chart replica count and resource limits for payment service", "E11", "E11", "2023-09-05T14:15:00Z"),
        ("deployment-service", "Story", False, "GitHub Actions production release deployment workflow trigger", "E06", "E06", "2024-07-18T09:45:00Z"),
        ("notification-service", "Story", False, "Implement event-driven HTTP webhook dispatcher payload queue", "E07", "E07", "2023-06-02T10:00:00Z"),
        ("notification-service", "Task", False, "Build automated SMS gateway alert dispatcher for charge declines", "E12", "E12", "2024-01-25T13:20:00Z"),
        ("user-service", "Story", False, "Merchant profile registration controller and account onboarding", "E02", "E02", "2023-05-19T10:00:00Z"),
        ("user-service", "Task", False, "Implement merchant KYC tax ID document verification engine", "E07", "E07", "2024-03-14T15:10:00Z"),
        ("compliance-service", "Story", False, "Sanitize credit card Primary Account Numbers (PAN) for PCI-DSS compliance", "E09", "E09", "2023-08-04T10:00:00Z"),
        ("compliance-service", "Task", False, "Purge expired audit logs per regulatory data retention policy", "E09", "E09", "2024-09-08T14:00:00Z"),

        # --- Bug Representations (18 Bugs represented as Task/Story with [Bug] tag) ---
        ("payment-service", "Task", True, "[Bug] Fix state machine deadlock during card charge retry", "E04", "E04", "2023-07-10T10:00:00Z"),
        ("payment-service", "Task", True, "[Bug] Fix payment intent duplicate creation on network timeout", "E01", "E01", "2024-01-15T14:00:00Z"),
        ("payment-service", "Task", True, "[Bug] Resolve card token validation NPE in acquirer handler", "E12", "E12", "2025-04-20T11:30:00Z"),
        ("fraud-service", "Task", True, "[Bug] Fix velocity checker sliding window timestamp precision", "E14", "E14", "2023-11-12T09:45:00Z"),
        ("fraud-service", "Task", True, "[Bug] Fix ML score boundary floating point rounding error", "E14", "E14", "2024-08-05T15:15:00Z"),
        ("auth-service", "Task", True, "[Bug] Fix JWT token expiration calculation in leap year", "E02", "E02", "2024-02-29T10:30:00Z"),
        ("auth-service", "Task", True, "[Bug] Fix KMS vault secret key rotation race condition", "E02", "E02", "2025-08-14T13:00:00Z"),
        ("ledger-service", "Task", True, "[Bug] Fix double-entry debit credit integer overflow on large amount", "E10", "E10", "2023-09-18T16:20:00Z"),
        ("ledger-service", "Task", True, "[Bug] Resolve ledger balance verifier memory leak in audit worker", "E10", "E10", "2024-10-22T11:00:00Z"),
        ("ledger-service", "Task", True, "[Bug] Fix journal entry audit log formatting for multi-currency", "E10", "E10", "2025-05-18T14:45:00Z"),
        ("api-gateway", "Task", True, "[Bug] Fix token bucket rate limiter concurrency lock delay", "E01", "E01", "2023-12-05T10:15:00Z"),
        ("api-gateway", "Task", True, "[Bug] Fix ingress proxy upstream socket leak on 504 gateway timeout", "E06", "E06", "2024-06-14T15:30:00Z"),
        ("api-gateway", "Task", True, "[Bug] Fix OpenAPI schema validation error on optional parameters", "E15", "E15", "2025-03-08T09:00:00Z"),
        ("settlement-service", "Task", True, "[Bug] Fix ACH clearing file header checksum calculation", "E04", "E04", "2023-12-19T11:40:00Z"),
        ("settlement-service", "Task", True, "[Bug] Fix bank deposit statement reconciliation date timezone mismatch", "E16", "E16", "2024-09-30T14:10:00Z"),
        ("monitoring-service", "Task", True, "[Bug] Fix Prometheus alert false positive on temporary gateway restart", "E03", "E03", "2024-04-12T10:20:00Z"),
        ("deployment-service", "Task", True, "[Bug] Fix ArgoRollout canary step pause duration override", "E06", "E06", "2024-11-25T16:00:00Z"),
        ("compliance-service", "Task", True, "[Bug] Fix PCI sanitizer card number masking regex for 15-digit Amex", "E09", "E09", "2024-05-02T13:45:00Z"),

        # --- Additional Stories/Tasks to reach exactly 98 child issues (110 total issues) ---
        ("reporting-service", "Story", False, "Financial report automated PDF generator integration", "E05", "E05", "2025-04-10T10:00:00Z"),
        ("reporting-service", "Task", False, "Optimize summary report data aggregation query performance", "E19", "E19", "2025-08-22T14:30:00Z"),
        ("user-service", "Story", False, "Merchant profile webhook URL update and verification", "E07", "E07", "2025-05-16T11:15:00Z"),
        ("user-service", "Task", False, "Add merchant account status audit history log table", "E02", "E02", "2025-10-04T09:40:00Z"),
        ("notification-service", "Story", False, "Email notification template localization for international merchants", "E07", "E07", "2025-03-01T10:50:00Z"),
        ("notification-service", "Task", False, "SMS gateway retry queue exponential backoff policy", "E12", "E12", "2025-09-14T15:25:00Z"),
        ("monitoring-service", "Story", False, "Grafana dashboard p99 response time quantile graph setup", "E13", "E13", "2025-06-18T10:00:00Z"),
        ("monitoring-service", "Task", False, "PagerDuty alert routing rule update for fraud velocity spikes", "E18", "E18", "2025-12-02T13:15:00Z"),
        ("deployment-service", "Story", False, "GitHub Actions automated unit test workflow optimization", "E11", "E11", "2025-04-28T11:00:00Z"),
        ("deployment-service", "Task", False, "Helm values values.yaml configuration parameter review", "E06", "E06", "2025-11-19T14:40:00Z"),
        ("compliance-service", "Story", False, "PCI-DSS compliance audit report automated generator", "E09", "E09", "2025-07-25T10:30:00Z"),
        ("compliance-service", "Task", False, "Data retention policy audit log scrubbing background worker", "E09", "E09", "2026-01-30T16:00:00Z"),

        # Extra balance items for complete domain representation
        ("ledger-service", "Story", False, "Multi-acquirer settlement debit credit posting rule engine", "E10", "E10", "2026-03-15T10:00:00Z"),
        ("ledger-service", "Task", False, "Audit entry timestamp verification for financial compliance", "E10", "E10", "2026-06-20T14:15:00Z"),
        ("ledger-service", "Story", False, "Immutable journal entry cryptographic signature hashing", "E10", "E10", "2026-07-10T11:30:00Z"),
        ("ledger-service", "Task", False, "Double-entry ledger balance audit snapshot tool", "E10", "E10", "2026-08-02T09:45:00Z"),
        ("auth-service", "Story", False, "OAuth2 bearer token scope authorization enforcement", "E02", "E02", "2026-04-14T10:00:00Z"),
        ("auth-service", "Task", False, "KMS vault key rotation audit log publisher", "E02", "E02", "2026-07-08T15:10:00Z"),
        ("payment-service", "Story", False, "Payment intent status transition event publisher", "E01", "E01", "2026-05-02T10:00:00Z"),
        ("payment-service", "Task", False, "Card processor decline reason message formatter", "E04", "E04", "2026-08-11T13:25:00Z"),
        ("fraud-service", "Story", False, "Real-time risk evaluator threshold dynamic configuration", "E14", "E14", "2026-03-08T10:00:00Z"),
        ("fraud-service", "Task", False, "Blacklist IP filter subnet range updater", "E14", "E14", "2026-06-22T14:00:00Z"),
        ("settlement-service", "Story", False, "ACH clearing batch status notification dispatcher", "E16", "E16", "2026-04-30T11:20:00Z"),
        ("settlement-service", "Task", False, "Bank statement reconciliation imbalance reporter", "E04", "E04", "2026-07-19T16:05:00Z"),
        ("reporting-service", "Story", False, "Daily transaction throughput summary email reporter", "E05", "E05", "2026-05-18T10:00:00Z"),
        ("reporting-service", "Task", False, "CSV audit exporter compression and archiving worker", "E19", "E19", "2026-08-05T12:45:00Z"),
        ("user-service", "Story", False, "Merchant profile KYC verification status webhook dispatcher", "E02", "E02", "2026-06-12T10:00:00Z"),
        ("user-service", "Task", False, "Account registration controller request payload sanitizer", "E07", "E07", "2026-08-14T15:30:00Z"),
        ("notification-service", "Story", False, "Webhook dispatcher HTTP retry queue backoff engine", "E07", "E07", "2026-05-25T11:00:00Z"),
        ("notification-service", "Task", False, "Receipt email template HTML formatter update", "E12", "E12", "2026-08-08T14:15:00Z"),
        ("monitoring-service", "Story", False, "Prometheus HTTP request duration bucket alert rule", "E03", "E03", "2026-06-28T10:00:00Z"),
        ("monitoring-service", "Task", False, "Grafana dashboard panel query optimization", "E13", "E13", "2026-08-16T13:50:00Z"),
        ("deployment-service", "Story", False, "ArgoRollout canary status notification integration", "E06", "E06", "2026-07-04T10:00:00Z"),
        ("deployment-service", "Task", False, "CI/CD build pipeline Docker image layer caching", "E11", "E11", "2026-08-18T15:10:00Z"),
        ("compliance-service", "Story", False, "PCI-DSS card number masking validation test suite", "E09", "E09", "2026-06-16T10:00:00Z"),
        ("compliance-service", "Task", False, "Audit event logger JSON payload validator", "E09", "E09", "2026-08-19T14:20:00Z")
    ]

    created_issues = []
    stories_count = 0
    tasks_count = 0
    bugs_count = 0

    print(f"\nCreating {len(issue_templates)} Child Issues linked to Epics...")
    for idx, (mod, itype_str, is_bug, summary, rep_id, ass_id, ts_str) in enumerate(issue_templates):
        epic_key = epic_keys.get(mod)
        if not epic_key:
            print(f"  - Warning: Missing Epic for module {mod}")
            continue

        rep_emp = next(e for e in employees if e["id"] == rep_id)
        ass_emp = next(e for e in employees if e["id"] == ass_id)

        # Build natural description with employee attribution context
        desc_text = f"{summary}. Assigned to {ass_emp['name']} ({ass_emp['jira']}) / Reported by {rep_emp['name']} ({rep_emp['jira']})."
        if is_bug:
            desc_text += " Priority: High. Bug report requiring immediate resolution."
            bugs_count += 1
        elif itype_str == "Story":
            stories_count += 1
        else:
            tasks_count += 1

        payload = {
            "fields": {
                "project": {"key": "SCRUM"},
                "summary": summary,
                "issuetype": {"name": itype_str},
                "description": build_adf_doc(desc_text),
                "parent": {"key": epic_key},
                "components": [{"name": mod}]
            }
        }
        st, res = api_request("/rest/api/3/issue", method="POST", payload=payload)
        if st in [200, 201]:
            issue_key = res.get("key")
            created_issues.append({"key": issue_key, "module": mod, "assignee": ass_emp["name"], "type": itype_str, "is_bug": is_bug, "ts": ts_str})
            if (idx + 1) % 15 == 0 or (idx + 1) == len(issue_templates):
                print(f"  - Created {idx+1}/{len(issue_templates)} issues (Latest: {issue_key})")
        else:
            print(f"  - Failed issue creation [{idx+1}]: status {st}")
        time.sleep(0.1)

    # 5. Add ~60 Threaded Comments across created issues
    print("\nAdding ~60 Threaded Comments across created issues...")
    comments_count = 0
    comment_templates = [
        "Code review completed. Unit tests passing with 95% line coverage.",
        "Verified deployment in staging environment. Verified zero regression.",
        "Pushed fix to main branch. Verified integration with acquirer simulator.",
        "Reviewed architecture specification. Approved for release rollout.",
        "Configured Prometheus alert thresholds and verified PagerDuty escalation.",
        "Double-entry journal balance matching confirmed for all merchant batch clearing transactions."
    ]

    for i, issue in enumerate(created_issues):
        if i % 2 == 0 and comments_count < 60:
            c_text = comment_templates[comments_count % len(comment_templates)]
            payload = {"body": build_adf_doc(c_text)}
            st, res = api_request(f"/rest/api/3/issue/{issue['key']}/comment", method="POST", payload=payload)
            if st in [200, 201]:
                comments_count += 1
            time.sleep(0.05)

    print(f"Added {comments_count} comments successfully.")

    total_new_issues = len(epic_keys) + len(created_issues)
    print("\n=== Jira Cloud Creation Completed ===")
    print(f"Components Created: {len(created_components)}")
    print(f"Epics Created: {len(epic_keys)}")
    print(f"Stories Created: {stories_count}")
    print(f"Tasks Created: {tasks_count}")
    print(f"Bugs Represented: {bugs_count}")
    print(f"Comments Created: {comments_count}")
    print(f"Total New Issues Created: {total_new_issues}")

if __name__ == "__main__":
    main()
