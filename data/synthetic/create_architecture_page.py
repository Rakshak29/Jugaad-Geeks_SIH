"""
Script to create the 'Architecture' Confluence page via REST API v2
as a child of 'Project Overview' (ID: 786433) in space ACMEPAY (393219).
Documentation strictly reflects repository evidence.
"""

import os
import json
import base64
import ssl
import urllib.request

def build_architecture_html():
    return """<h1>AcmePay Financial Architecture Specification</h1>
<p>This page documents the verified system architecture, core microservices, data models, and component interactions for the AcmePay Financial monorepo.</p>

<h2>1. System Overview</h2>
<p>AcmePay Financial operates an enterprise payment processing, risk scoring, double-entry ledgering, and merchant settlement platform built as a polyglot monorepo (Go, Python, YAML, JSON).</p>

<h2>2. Major Monorepo Components (12 Modules)</h2>
<table>
  <thead>
    <tr>
      <th>Module</th>
      <th>Location</th>
      <th>Primary Technical Responsibilities</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>payment-service</strong></td>
      <td><code>services/payment/</code></td>
      <td>PaymentIntent routing, acquirer charge processing, state machine transitions, exponential backoff retries.</td>
    </tr>
    <tr>
      <td><strong>fraud-service</strong></td>
      <td><code>services/fraud/</code></td>
      <td>Real-time risk scoring evaluator, transaction velocity limiters, ML probability rules, IP blacklist filtering.</td>
    </tr>
    <tr>
      <td><strong>auth-service</strong></td>
      <td><code>services/auth/</code></td>
      <td>Bearer JWT issuance, OAuth2 token exchange, KMS key vault rotation, RBAC authorization middleware.</td>
    </tr>
    <tr>
      <td><strong>ledger-service</strong></td>
      <td><code>services/ledger/</code></td>
      <td>Double-entry debit/credit journal bookkeeping, balance verification, immutable audit trail logging.</td>
    </tr>
    <tr>
      <td><strong>notification-service</strong></td>
      <td><code>services/notification/</code></td>
      <td>Event-driven HTTP webhook dispatcher, automated SMS gateway alerts, merchant receipt email templates.</td>
    </tr>
    <tr>
      <td><strong>user-service</strong></td>
      <td><code>services/user/</code></td>
      <td>Merchant account profile management, KYC tax ID document verification, registration controllers.</td>
    </tr>
    <tr>
      <td><strong>reporting-service</strong></td>
      <td><code>services/reporting/</code></td>
      <td>Merchant settlement volume reports, CSV audit log exporter, daily throughput metrics aggregator.</td>
    </tr>
    <tr>
      <td><strong>settlement-service</strong></td>
      <td><code>services/settlement/</code></td>
      <td>ACH clearing file generation, merchant payout batch scheduling, bank statement reconciliation.</td>
    </tr>
    <tr>
      <td><strong>api-gateway</strong></td>
      <td><code>services/api-gateway/</code></td>
      <td>Ingress reverse proxy routing, token bucket request rate limiting, OpenAPI 3.0 proxy specifications.</td>
    </tr>
    <tr>
      <td><strong>deployment-service</strong></td>
      <td><code>deployments/</code></td>
      <td>Kubernetes ArgoRollout canary configurations, Helm chart values, GitHub Actions deployment workflows.</td>
    </tr>
    <tr>
      <td><strong>monitoring-service</strong></td>
      <td><code>monitoring/</code></td>
      <td>Prometheus latency/error alert rules, Grafana response dashboards, PagerDuty escalation policies.</td>
    </tr>
    <tr>
      <td><strong>compliance-service</strong></td>
      <td><code>services/compliance/</code></td>
      <td>PCI-DSS Primary Account Number (PAN) sanitizer, audit log data retention scrubbing, compliance logging.</td>
    </tr>
  </tbody>
</table>

<h2>3. Data & Storage Layer</h2>
<ul>
  <li><strong>PostgreSQL Database:</strong> Stores Engineering Continuity Engine models, metadata, and ingestion records.</li>
  <li><strong>Ledger Journal Books:</strong> Immutable double-entry transaction debit/credit records.</li>
  <li><strong>Redis Token Cache:</strong> In-memory token bucket rate limiting and token revocation blacklists.</li>
</ul>

<h2>4. Component Interaction Flow</h2>
<p>Incoming Payment Request &rarr; <strong>API Gateway</strong> (Rate Limiting) &rarr; <strong>Auth Service</strong> (JWT &amp; RBAC Validation) &rarr; <strong>Fraud Service</strong> (Velocity &amp; Risk Scoring) &rarr; <strong>Payment Service</strong> (Intent Routing) &rarr; <strong>Ledger Service</strong> (Double-Entry Balance Verification) &rarr; <strong>Settlement Service</strong> (ACH Clearing Batch) &rarr; <strong>Notification Service</strong> (Webhook Event Dispatch).</p>
"""

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

    # Verify parent page
    req_parent = urllib.request.Request(f"{confluence_url}/api/v2/pages/786433", headers=headers)
    with urllib.request.urlopen(req_parent, context=ctx) as resp:
        parent_data = json.loads(resp.read().decode())
        print(f"Verified Parent Page: '{parent_data.get('title')}' (ID: {parent_data.get('id')})")

    # POST payload
    html_content = build_architecture_html()
    payload = {
        "spaceId": "393219",
        "status": "current",
        "title": "Architecture",
        "parentId": "786433",
        "body": {
            "representation": "storage",
            "value": html_content
        }
    }

    print("\n=== INTENDED POST PAYLOAD (Summary) ===")
    print(f"Title: {payload['title']}")
    print(f"Parent ID: {payload['parentId']}")
    print(f"Space ID: {payload['spaceId']}")

    # Execute POST
    data_bytes = json.dumps(payload).encode()
    req_post = urllib.request.Request(f"{confluence_url}/api/v2/pages", data=data_bytes, headers=headers, method="POST")
    with urllib.request.urlopen(req_post, context=ctx) as resp:
        st = resp.status
        created_page = json.loads(resp.read().decode())
        print(f"\nPOST Status: {st}")

    new_page_id = created_page.get("id")
    print(f"Created Architecture Page ID: {new_page_id}")

    # GET verification
    req_get = urllib.request.Request(f"{confluence_url}/api/v2/pages/{new_page_id}", headers=headers)
    with urllib.request.urlopen(req_get, context=ctx) as resp:
        get_page = json.loads(resp.read().decode())
        print("\n=== GET VERIFICATION ===")
        print(f"Page ID: {get_page.get('id')}")
        print(f"Title: {get_page.get('title')}")
        print(f"Parent ID: {get_page.get('parentId')}")
        print(f"Status: {get_page.get('status')}")
        webui_link = get_page.get('_links', {}).get('webui')
        if webui_link:
            print(f"Web UI URL: {url}/wiki{webui_link}")

if __name__ == "__main__":
    main()
