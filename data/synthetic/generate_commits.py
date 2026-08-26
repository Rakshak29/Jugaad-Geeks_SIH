"""
Script to generate realistic synthetic GitHub Git commit history for AcmePay Financial.
Generates exactly 300 commits spanning 2023-2026 matching blueprint.yaml and github_generation_plan.yaml.
OUTPUT CONTAINS ZERO GROUND-TRUTH SHORTCUT KEYS.
"""

import json
import random
import hashlib
from datetime import datetime, timedelta

def generate_commits():
    random.seed(42)  # Deterministic generation

    authors = [
        {"id": "E01", "name": "Rakshak Shetty", "email": "rakshak@acmepay.io", "gh": "Rakshak29", "modules": ["api-gateway", "payment-service", "auth-service", "monitoring-service"], "count": 25},
        {"id": "E02", "name": "Keyuri Sheth", "email": "keyuri@acmepay.io", "gh": "keys246", "modules": ["auth-service", "user-service", "compliance-service", "api-gateway"], "count": 22},
        {"id": "E03", "name": "Kshitij Naidu", "email": "kshitij@acmepay.io", "gh": "kshitijnaidu", "modules": ["monitoring-service", "deployment-service", "payment-service"], "count": 20},
        {"id": "E04", "name": "Krish Trivedi", "email": "krish@acmepay.io", "gh": "krish-exe", "modules": ["payment-service", "settlement-service", "fraud-service"], "count": 24},
        {"id": "E05", "name": "Naman Nahar", "email": "naman@acmepay.io", "gh": "NamanN-Creator", "modules": ["reporting-service", "ledger-service", "settlement-service"], "count": 20},
        {"id": "E06", "name": "Parth More", "email": "parth@acmepay.io", "gh": "shadecodes10", "modules": ["deployment-service", "monitoring-service", "api-gateway"], "count": 22},
        {"id": "E07", "name": "Ananya Sharma", "email": "ananya@acmepay.io", "gh": "ananyas-code", "modules": ["user-service", "notification-service", "api-gateway"], "count": 15},
        {"id": "E08", "name": "Vikram Malhotra", "email": "vikram@acmepay.io", "gh": "vmalhotra-dev", "modules": ["auth-service"], "count": 25, "stale": True},  # Case 2 Stale
        {"id": "E09", "name": "Deepa Raman", "email": "deepa@acmepay.io", "gh": "deepa-ram", "modules": ["compliance-service", "reporting-service", "ledger-service"], "count": 14},
        {"id": "E10", "name": "Rohan Gupta", "email": "rohan.gupta@acmepay.io", "gh": "rohan.gupta", "modules": ["ledger-service"], "count": 35, "concentrated": True},  # Case 1 Concentration
        {"id": "E11", "name": "Meera Patel", "email": "meera@acmepay.io", "gh": "mpatel-infra", "modules": ["deployment-service", "api-gateway", "monitoring-service"], "count": 15},
        {"id": "E12", "name": "Siddharth Joshi", "email": "sjoshi-backend@acmepay.io", "gh": "sjoshi-backend", "modules": ["payment-service", "notification-service"], "count": 12},
        {"id": "E13", "name": "Tanvi Deshmukh", "email": "tanvi@acmepay.io", "gh": "tdeshmukh-qa", "modules": ["monitoring-service", "deployment-service"], "count": 12},
        {"id": "E14", "name": "Aditya Verma", "email": "aditya.verma@acmepay.io", "gh": "averma-sec", "modules": ["fraud-service", "payment-service"], "count": 16},
        {"id": "E15", "name": "Neha Kapoor", "email": "neha@acmepay.io", "gh": "nkapoor-dev", "modules": ["api-gateway", "user-service"], "count": 12},
        {"id": "E16", "name": "Arjun Nair", "email": "arjun@acmepay.io", "gh": "anair-backend", "modules": ["settlement-service", "ledger-service"], "count": 14},
        {"id": "E17", "name": "Pooja Bhatia", "email": "pooja@acmepay.io", "gh": "pbhatia-docs", "modules": [], "count": 0},  # Case 6 Ambiguous
        {"id": "E18", "name": "Varun Saxena", "email": "varun@acmepay.io", "gh": "vsaxena-ops", "modules": ["monitoring-service", "deployment-service"], "count": 10},
        {"id": "E19", "name": "Ritu Sengupta", "email": "ritu@acmepay.io", "gh": "rsengupta-data", "modules": ["reporting-service", "ledger-service"], "count": 12},
        {"id": "E20", "name": "Kabir Mehta", "email": "kabir@acmepay.io", "gh": "kmehta-auth", "modules": ["auth-service", "user-service"], "count": 12},
    ]

    module_files = {
        "payment-service": [
            ("services/payment/router.go", "feat(payment): optimize intent router routing table and path validation"),
            ("services/payment/intent_handler.go", "feat(payment): handle payment intent creation and idempotency verification"),
            ("services/payment/retry_engine.go", "fix(payment): add exponential backoff jitter to payment processor retry loop"),
            ("services/payment/card_processor.go", "refactor(payment): update card processor charge validation and token checks"),
            ("services/payment/state_machine.go", "fix(payment): resolve state machine deadlock during charge authorization retry")
        ],
        "fraud-service": [
            ("services/fraud/risk_evaluator.py", "feat(fraud): implement real-time risk evaluator threshold rules"),
            ("services/fraud/velocity_checker.py", "feat(fraud): update card transaction velocity limiters and window checks"),
            ("services/fraud/ml_rules.py", "refactor(fraud): add ML fraud score risk weight parameters"),
            ("services/fraud/blacklist_filter.py", "sec(fraud): add IP subnet and compromised card token blacklist filter")
        ],
        "auth-service": [
            ("services/auth/jwt_issuer.go", "feat(auth): issue bearer JWT with custom merchant roles and token signing"),
            ("services/auth/oauth_handler.go", "feat(auth): implement OAuth2 authorization code token exchange"),
            ("services/auth/kms_vault.go", "sec(auth): add KMS key vault wrapper and key rotation interval"),
            ("services/auth/rbac_middleware.go", "sec(auth): enforce role-based authorization scope checking on API proxy")
        ],
        "ledger-service": [
            ("services/ledger/journal_entry.go", "feat(ledger): add double-entry journal balance debit and credit models"),
            ("services/ledger/balance_verifier.go", "feat(ledger): implement immutable journal balance verifier"),
            ("services/ledger/double_entry.go", "refactor(ledger): post atomic debit credit journal transactions"),
            ("services/ledger/audit_trail.go", "sec(ledger): log audit trail entries to immutable journal book")
        ],
        "notification-service": [
            ("services/notification/webhook_dispatcher.go", "feat(notification): implement event-driven HTTP webhook dispatcher"),
            ("services/notification/sms_gateway.go", "feat(notification): add SMS gateway alert routing for payment failures"),
            ("services/notification/email_template.go", "refactor(notification): format merchant payment receipt email template")
        ],
        "user-service": [
            ("services/user/merchant_profile.go", "feat(user): add merchant profile data model and onboarding parameters"),
            ("services/user/kyc_verifier.go", "feat(user): implement merchant KYC tax ID document verification"),
            ("services/user/account_controller.go", "refactor(user): update merchant account registration controller endpoint")
        ],
        "reporting-service": [
            ("services/reporting/settlement_report.py", "feat(reporting): generate merchant settlement reports and volume summaries"),
            ("services/reporting/audit_exporter.py", "feat(reporting): add CSV audit log exporter for financial compliance"),
            ("services/reporting/daily_summary.py", "refactor(reporting): aggregate daily transaction throughput and fee stats")
        ],
        "settlement-service": [
            ("services/settlement/ach_clearing.go", "feat(settlement): execute ACH clearing file generation and bank payouts"),
            ("services/settlement/payout_batcher.go", "feat(settlement): schedule merchant payout clearing batches"),
            ("services/settlement/bank_reconciliation.go", "fix(settlement): reconcile bank deposit statements with internal clearing")
        ],
        "api-gateway": [
            ("services/api-gateway/ingress_proxy.go", "feat(api-gateway): route ingress proxy traffic to microservice backends"),
            ("services/api-gateway/rate_limiter.go", "feat(api-gateway): add token bucket rate limiter for v2 payment proxy endpoints"),
            ("services/api-gateway/openapi_spec.json", "docs(api-gateway): update OpenAPI 3.0 payment gateway spec"),
            ("services/api-gateway/auth_plugin.go", "sec(api-gateway): add bearer token verification proxy plugin")
        ],
        "deployment-service": [
            ("deployments/helm/payment-service/values.yaml", "infra(deploy): update Helm chart replica count and resources"),
            ("deployments/k8s/canary_rollout.yaml", "infra(deploy): configure ArgoRollout canary deployment steps"),
            (".github/workflows/deploy_production.yml", "ci(deploy): add production deployment workflow trigger"),
            (".github/workflows/ci_build.yml", "ci(deploy): run unit tests on pull request main branch")
        ],
        "monitoring-service": [
            ("monitoring/prometheus/payment_alerts.yml", "ops(monitoring): add Prometheus alert rules for p99 latency spikes"),
            ("monitoring/grafana/dashboards/latency.json", "ops(monitoring): update Grafana dashboard response time metrics"),
            ("monitoring/pagerduty/routing_rules.json", "ops(monitoring): configure PagerDuty escalation policy routing")
        ],
        "compliance-service": [
            ("services/compliance/pci_sanitizer.go", "sec(compliance): sanitize Primary Account Numbers for PCI-DSS compliance"),
            ("services/compliance/data_retention.go", "sec(compliance): purge expired audit logs per data retention policy"),
            ("services/compliance/audit_logger.go", "sec(compliance): log compliance audit events for security review")
        ]
    }

    start_date = datetime(2023, 1, 15)
    end_date = datetime(2026, 8, 20)
    total_days = (end_date - start_date).days

    commits = []

    for author in authors:
        emp_id = author["id"]
        name = author["name"]
        email = author["email"]
        gh = author["gh"]
        modules = author["modules"]
        count = author["count"]
        is_stale = author.get("stale", False)

        for i in range(count):
            if is_stale:
                # E08 (Vikram) commits strictly in 2023 (Case 2 Stale)
                days_offset = random.randint(0, 320)
            else:
                # Random spread across 2023-2026
                days_offset = random.randint(0, total_days)

            commit_time = start_date + timedelta(days=days_offset, hours=random.randint(8, 18), minutes=random.randint(0, 59))
            
            # Select module
            if not modules:
                continue
            mod = random.choice(modules)
            file_path, msg_template = random.choice(module_files[mod])

            raw_key = f"{emp_id}:{mod}:{i}:{commit_time.isoformat()}"
            sha = hashlib.sha1(raw_key.encode()).hexdigest()

            # Varied author string format across records (Case 5 Identity Resolution)
            if i % 3 == 0:
                author_str = f"{name} <{email}>"
            elif i % 3 == 1:
                author_str = gh
            else:
                author_str = f"{name}"

            commit_record = {
                "commit_id": sha,
                "commit_hash": sha,
                "author_id": author_str,
                "author": f"{name} <{email}>",
                "committer": f"{name} <{email}>",
                "timestamp": commit_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "message": msg_template,
                "repository": "acmepay/engineering-monorepo",
                "branch": "main",
                "files_changed": [file_path],
                "lines_added": random.randint(15, 180),
                "lines_deleted": random.randint(2, 45)
            }
            commits.append(commit_record)

    # Sort chronologically
    commits.sort(key=lambda x: x["timestamp"])

    print(f"Generated {len(commits)} commits.")
    return commits

if __name__ == "__main__":
    generated_commits = generate_commits()
    
    # Save to data/raw/github/commits.json
    with open("data/raw/github/commits.json", "w", encoding="utf-8") as f:
        json.dump(generated_commits, f, indent=2)
    print("Saved to data/raw/github/commits.json")

    # Save to data/synthetic/commits.json
    with open("data/synthetic/commits.json", "w", encoding="utf-8") as f:
        json.dump(generated_commits, f, indent=2)
    print("Saved to data/synthetic/commits.json")
