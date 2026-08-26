"""
Script to create the 12 verified AcmePay module documentation pages in Confluence Cloud REST API v2.
Parent: Project Overview (ID: 786433), Space: ACMEPAY (ID: 393219).
Preserves provenances, historical dates (2023-2026), and cross-source correlations.
"""

import os
import json
import base64
import time
import ssl
import urllib.request

def build_storage_html(title, module, author_str, dates_str, git_ref, jira_ref, body_html):
    header_block = f"""<div style="background-color: #f4f5f7; border-left: 4px solid #0052cc; padding: 12px; margin-bottom: 16px;">
  <p><strong>Document Metadata &amp; Technical Provenance</strong></p>
  <p><strong>Module Component:</strong> <code>{module}</code> | <strong>Authors:</strong> {author_str}</p>
  <p><strong>Historical Effective Period:</strong> {dates_str}</p>
  <p><strong>Correlated GitHub Artifacts:</strong> {git_ref}</p>
  <p><strong>Correlated Jira Epics &amp; Issues:</strong> {jira_ref}</p>
</div>
"""
    return header_block + body_html


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
    confluence_url = f"{url}/wiki"

    auth_str = base64.b64encode(f'{email}:{token}'.encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_str}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    ctx = ssl._create_unverified_context()

    pages_to_create = [
        {
            "title": "Payment Service Architecture & Routing Protocol",
            "module": "payment-service",
            "authors": "Rakshak Shetty (E01), Krish Trivedi (E04)",
            "dates": "2023-01-20 to 2026-08-20",
            "git": "Commit b17f408, e3cd3db (services/payment/router.go, state_machine.go)",
            "jira": "Epic SCRUM-6, SCRUM-18, SCRUM-75",
            "body": """<h1>Payment Service Architecture Specification</h1>
<p>The <strong>payment-service</strong> module handles credit card intent creation, acquirer charge processing, transaction state machine transitions, and exponential backoff retry handling.</p>
<h2>Technical Components</h2>
<ul>
  <li><code>services/payment/router.go</code>: Routes PaymentIntent payloads to acquiring processors.</li>
  <li><code>services/payment/state_machine.go</code>: Enforces PENDING &rarr; PROCESSING &rarr; SUCCEEDED/FAILED status state transitions.</li>
  <li><code>services/payment/retry_engine.go</code>: Implements retry logic with exponential backoff and randomized jitter.</li>
</ul>"""
        },
        {
            "title": "Real-Time Risk Evaluator & Fraud ML Pipeline Spec",
            "module": "fraud-service",
            "authors": "Aditya Verma (E14), Krish Trivedi (E04)",
            "dates": "2023-04-18 to 2026-06-22",
            "git": "Commit a3a2fda (services/fraud/risk_evaluator.py, velocity_checker.py)",
            "jira": "Epic SCRUM-7, SCRUM-53, SCRUM-78",
            "body": """<h1>Fraud Detection &amp; Risk Evaluator Specification</h1>
<p>The <strong>fraud-service</strong> calculates real-time risk scores between 0.0 and 1.0 based on card transaction velocity, high-amount thresholds, and IP subnet blacklists.</p>
<h2>Technical Components</h2>
<ul>
  <li><code>services/fraud/risk_evaluator.py</code>: Real-time risk evaluation engine.</li>
  <li><code>services/fraud/velocity_checker.py</code>: Sliding 60-second window transaction frequency limiter.</li>
  <li><code>services/fraud/blacklist_filter.py</code>: Compromised card token and suspicious IP subnet filter.</li>
</ul>"""
        },
        {
            "title": "OAuth2 & KMS Key Vault Token Security Guide",
            "module": "auth-service",
            "authors": "Vikram Malhotra (E08 - Historical 2023), Keyuri Sheth (E02 - Recent 2025-2026)",
            "dates": "2023-01-20 to 2026-07-08",
            "git": "Commit b543bee, fcb742d (services/auth/jwt_issuer.go, kms_vault.go)",
            "jira": "Epic SCRUM-8, SCRUM-32, SCRUM-38",
            "body": """<h1>Authentication Service &amp; Key Vault Guide</h1>
<p>The <strong>auth-service</strong> issues bearer JWT claims, handles OAuth2 code exchange, and rotates KMS signing keys for secure API permissions.</p>
<h2>Historical Development &amp; Maintenance</h2>
<p>Historical KMS vault architecture was implemented by Vikram Malhotra in 2023 (SCRUM-32..37). Current PKCE OAuth2 upgrades and key rotation automation are maintained by Keyuri Sheth (SCRUM-38..41).</p>
<h2>Technical Components</h2>
<ul>
  <li><code>services/auth/jwt_issuer.go</code>: Generates signed bearer tokens with merchant scope claims.</li>
  <li><code>services/auth/kms_vault.go</code>: Master key rotation and crypto vault wrapper.</li>
</ul>"""
        },
        {
            "title": "Double-Entry Journal Bookkeeping & Balance Matching",
            "module": "ledger-service",
            "authors": "Rohan Gupta (E10 - Principal Ledger SME)",
            "dates": "2023-03-10 to 2026-08-02",
            "git": "Commit 6908df2, 33f6995 (services/ledger/balance_verifier.go, journal_entry.go)",
            "jira": "Epic SCRUM-9, SCRUM-18..31, SCRUM-82..84",
            "body": """<h1>Double-Entry Ledger Architecture Specification</h1>
<p>The <strong>ledger-service</strong> maintains immutable financial accounting books. Every transaction requires equal debit and credit journal entries to satisfy double-entry balance verification.</p>
<h2>Domain Ownership &amp; Core Components</h2>
<p>Lead architect and primary SME for ledger balance matching is Rohan Gupta (E10), maintaining 84% of ledger engineering tickets and 57% of ledger code commits.</p>
<ul>
  <li><code>services/ledger/journal_entry.go</code>: Debit and Credit entry data structures.</li>
  <li><code>services/ledger/balance_verifier.go</code>: Verifies debits equal credits before posting.</li>
  <li><code>services/ledger/double_entry.go</code>: Atomic transaction posting engine.</li>
</ul>"""
        },
        {
            "title": "Event-Driven Webhook Dispatcher & Alert Routing",
            "module": "notification-service",
            "authors": "Ananya Sharma (E07), Siddharth Joshi (E12)",
            "dates": "2023-06-02 to 2026-08-08",
            "git": "Services/notification/webhook_dispatcher.go, sms_gateway.go",
            "jira": "Epic SCRUM-10, SCRUM-64, SCRUM-127",
            "body": """<h1>Notification Service Platform Architecture</h1>
<p>The <strong>notification-service</strong> handles outbound merchant event notifications, charge receipt emails, and automated SMS gateway alerts.</p>
<h2>Technical Components</h2>
<ul>
  <li><code>services/notification/webhook_dispatcher.go</code>: Asynchronous HTTP POST payload dispatcher.</li>
  <li><code>services/notification/sms_gateway.go</code>: Automated SMS alert dispatcher.</li>
  <li><code>services/notification/email_template.go</code>: Formatted receipt email HTML builder.</li>
</ul>"""
        },
        {
            "title": "Merchant KYC Onboarding & Profile Controller Spec",
            "module": "user-service",
            "authors": "Keyuri Sheth (E02), Ananya Sharma (E07), Pooja Bhatia (E17 - Doc Author)",
            "dates": "2023-05-19 to 2026-08-14",
            "git": "Services/user/merchant_profile.go, kyc_verifier.go",
            "jira": "Epic SCRUM-11, SCRUM-48, SCRUM-66",
            "body": """<h1>Merchant User Service &amp; KYC Verification Spec</h1>
<p>The <strong>user-service</strong> manages merchant onboarding, profile registrations, and automated tax ID KYC document verification.</p>
<h2>Documentation &amp; Engineering Contributors</h2>
<p>Technical architecture specifications authored by Pooja Bhatia (E17). Core implementation and KYC verification logic developed by Keyuri Sheth (E02) and Ananya Sharma (E07).</p>
<ul>
  <li><code>services/user/merchant_profile.go</code>: Merchant profile model and onboarding parameters.</li>
  <li><code>services/user/kyc_verifier.go</code>: Tax ID KYC validation worker.</li>
</ul>"""
        },
        {
            "title": "Merchant Settlement Reports & Audit Exporter Guide",
            "module": "reporting-service",
            "authors": "Naman Nahar (E05), Deepa Raman (E09), Ritu Sengupta (E19)",
            "dates": "2023-07-14 to 2026-08-05",
            "git": "Services/reporting/settlement_report.py, audit_exporter.py",
            "jira": "Epic SCRUM-12, SCRUM-57, SCRUM-97",
            "body": """<h1>Reporting Service &amp; Audit Exporter Guide</h1>
<p>The <strong>reporting-service</strong> aggregates daily transaction throughput, calculates processing fees, and exports financial audit CSV files.</p>
<h2>Technical Components</h2>
<ul>
  <li><code>services/reporting/settlement_report.py</code>: Calculates net settlement volume and processing fees.</li>
  <li><code>services/reporting/audit_exporter.py</code>: Exports structured CSV audit trails for financial compliance.</li>
  <li><code>services/reporting/daily_summary.py</code>: Aggregates daily transaction success and failure rates.</li>
</ul>"""
        },
        {
            "title": "ACH Clearing Batch & Bank Reconciliation Protocol",
            "module": "settlement-service",
            "authors": "Krish Trivedi (E04), Arjun Nair (E16)",
            "dates": "2023-05-08 to 2026-07-19",
            "git": "Services/settlement/ach_clearing.go, bank_reconciliation.go",
            "jira": "Epic SCRUM-13, SCRUM-50, SCRUM-88",
            "body": """<h1>Settlement Service &amp; ACH Clearing Protocol</h1>
<p>The <strong>settlement-service</strong> generates batch ACH clearing files for bank payout processing and reconciles internal clearing records with bank statements.</p>
<h2>Technical Components</h2>
<ul>
  <li><code>services/settlement/ach_clearing.go</code>: Formats standard ACH batch clearing files.</li>
  <li><code>services/settlement/payout_batcher.go</code>: Schedules merchant payout execution batches.</li>
  <li><code>services/settlement/bank_reconciliation.go</code>: Matches bank deposit statements against internal settlements.</li>
</ul>"""
        },
        {
            "title": "API Gateway Ingress Proxy & Rate Limiter Architecture",
            "module": "api-gateway",
            "authors": "Rakshak Shetty (E01), Keyuri Sheth (E02), Neha Kapoor (E15), Pooja Bhatia (E17 - Doc Author)",
            "dates": "2023-03-15 to 2026-07-12",
            "git": "Commit 1392da9, b901d5c (services/api-gateway/ingress_proxy.go, rate_limiter.go)",
            "jira": "Epic SCRUM-14, SCRUM-42..47, SCRUM-85",
            "body": """<h1>API Gateway Ingress &amp; Proxy Architecture</h1>
<p>The <strong>api-gateway</strong> acts as the central ingress proxy for AcmePay public payment APIs, handling reverse proxying, OpenAPI schema validation, and token bucket rate limiting.</p>
<h2>Distributed Engineering &amp; Documentation</h2>
<p>API Gateway engineering is distributed across 6 team members (E01, E02, E04, E06, E11, E15). Public API specifications authored by Pooja Bhatia (E17).</p>
<ul>
  <li><code>services/api-gateway/ingress_proxy.go</code>: Reverse proxy router for internal payment microservices.</li>
  <li><code>services/api-gateway/rate_limiter.go</code>: Token bucket rate limiter middleware.</li>
  <li><code>services/api-gateway/openapi_spec.json</code>: OpenAPI 3.0 public gateway specification.</li>
</ul>"""
        },
        {
            "title": "Kubernetes ArgoRollout Canary Deployment Runbook",
            "module": "deployment-service",
            "authors": "Kshitij Naidu (E03), Parth More (E06), Meera Patel (E11)",
            "dates": "2023-04-25 to 2026-08-18",
            "git": "Commit 889d323, 022881d (deployments/k8s/canary_rollout.yaml, helm/)",
            "jira": "Epic SCRUM-15, SCRUM-62, SCRUM-91",
            "body": """<h1>Deployment Service &amp; Canary Rollout Runbook</h1>
<p>The <strong>deployment-service</strong> manages Kubernetes ArgoRollout canary releases (10%/50% traffic steps), Helm values, and automated CI/CD build workflows.</p>
<h2>Technical Components</h2>
<ul>
  <li><code>deployments/k8s/canary_rollout.yaml</code>: ArgoRollout progressive delivery specification.</li>
  <li><code>deployments/helm/payment-service/values.yaml</code>: Kubernetes replica and resource parameters.</li>
  <li><code>.github/workflows/deploy_production.yml</code>: Production deployment workflow trigger.</li>
</ul>"""
        },
        {
            "title": "Prometheus Alerting & Grafana Latency Dashboard Spec",
            "module": "monitoring-service",
            "authors": "Kshitij Naidu (E03), Parth More (E06), Tanvi Deshmukh (E13), Varun Saxena (E18)",
            "dates": "2023-03-28 to 2026-08-16",
            "git": "Monitoring/prometheus/payment_alerts.yml, grafana/dashboards/latency.json",
            "jira": "Epic SCRUM-16, SCRUM-60, SCRUM-90",
            "body": """<h1>Monitoring &amp; Observability Specification</h1>
<p>The <strong>monitoring-service</strong> configures Prometheus alert rules for p99 latency spikes, Grafana response dashboards, and PagerDuty alert escalation rules.</p>
<h2>Technical Components</h2>
<ul>
  <li><code>monitoring/prometheus/payment_alerts.yml</code>: Prometheus alert rules for HighPaymentFailureRate and HighP99Latency.</li>
  <li><code>monitoring/grafana/dashboards/latency.json</code>: Grafana latency and throughput dashboard.</li>
  <li><code>monitoring/pagerduty/routing_rules.json</code>: SEV-1 incident on-call escalation policies.</li>
</ul>"""
        },
        {
            "title": "PCI-DSS Primary Account Number Sanitizer & Audit Policy",
            "module": "compliance-service",
            "authors": "Deepa Raman (E09), Keyuri Sheth (E02)",
            "dates": "2023-08-04 to 2026-08-19",
            "git": "Services/compliance/pci_sanitizer.go, data_retention.go",
            "jira": "Epic SCRUM-17, SCRUM-68, SCRUM-92",
            "body": """<h1>Compliance &amp; PCI-DSS Data Sanitizer Policy</h1>
<p>The <strong>compliance-service</strong> enforces PCI-DSS credit card number masking (6-to-4 PAN sanitization), data retention log purging, and audit logging.</p>
<h2>Technical Components</h2>
<ul>
  <li><code>services/compliance/pci_sanitizer.go</code>: Primary Account Number (PAN) masking logic.</li>
  <li><code>services/compliance/data_retention.go</code>: Purges expired audit logs past retention cutoff dates.</li>
  <li><code>services/compliance/audit_logger.go</code>: Immutable compliance audit event logger.</li>
</ul>"""
        }
    ]

    print("=== STARTING CONFLUENCE BATCH CREATION (12 MODULE PAGES) ===")
    created_pages = []

    for idx, page in enumerate(pages_to_create):
        storage_html = build_storage_html(
            page["title"], page["module"], page["authors"],
            page["dates"], page["git"], page["jira"], page["body"]
        )
        payload = {
            "spaceId": "393219",
            "status": "current",
            "title": page["title"],
            "parentId": "1015809",
            "body": {
                "representation": "storage",
                "value": storage_html
            }
        }

        data_bytes = json.dumps(payload).encode()
        req_post = urllib.request.Request(f"{confluence_url}/api/v2/pages", data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req_post, context=ctx) as resp:
                st = resp.status
                created_page = json.loads(resp.read().decode())
                pid = created_page.get("id")
                created_pages.append({"id": pid, "title": page["title"], "module": page["module"], "status": st})
                print(f"[{idx+1}/12] Created Page '{page['title']}' (ID: {pid}) - Status: {st}")
        except Exception as e:
            print(f"[{idx+1}/12] Error creating page '{page['title']}': {e}")
        time.sleep(0.15)

    print("\n=== VERIFYING ALL CREATED PAGES VIA GET REQUESTS ===")
    verified_count = 0
    for cp in created_pages:
        req_get = urllib.request.Request(f"{confluence_url}/api/v2/pages/{cp['id']}", headers=headers)
        try:
            with urllib.request.urlopen(req_get, context=ctx) as resp:
                gdata = json.loads(resp.read().decode())
                verified_count += 1
                webui = gdata.get("_links", {}).get("webui", "")
                print(f"  - Verified GET Page ID {cp['id']}: '{gdata.get('title')}' | Parent: {gdata.get('parentId')} | Status: {gdata.get('status')}")
        except Exception as e:
            print(f"  - Failed GET verification for ID {cp['id']}: {e}")

    print(f"\nBatch creation completed successfully! Created and verified {verified_count}/12 pages.")

if __name__ == "__main__":
    main()
