# mapper.py

# Maps exact file path prefixes to Module IDs based on your JSON config
FILE_TO_MODULE_MAP = {
    # M001: API Gateway & Core Payment Routing
    "services/api/": "M001",
    "services/gateway/": "M001",
    "services/api-gateway/": "M001",
    "services/auth/": "M001",
    "services/payment/": "M001",
    "services/payments/": "M001",
    "services/ingress/": "M001",
    
    # M002: Reconciliation Engine & Financial Ledgers
    "services/reconciliation/": "M002",
    "services/reconciliation-engine/": "M002",
    "services/reporting/": "M002",
    "services/settlement/": "M002",
    "services/ledger/": "M002",
    "services/recon/": "M002",
    
    # M003: Database Recovery & Storage Infrastructure
    "db/recovery/": "M003",
    "db/config/": "M003",
    "db/": "M003",
    "database/": "M003",
    "services/database/": "M003",
    "services/db/": "M003",
    
    # M004: Deployment System & DevOps
    "deployments/": "M004",
    ".github/workflows/": "M004",
    ".github/": "M004",
    "ci/": "M004",
    "infra/": "M004",
    "k8s/": "M004",
    "docker/": "M004",
    
    # M005: Incident Response & Observability
    "config/pagerduty_routing.json": "M005",
    "config/": "M005",
    "monitoring/": "M005",
    "incidents/": "M005",
    
    # M006: Crypto Vault, Fraud & Security Compliance
    "services/crypto/": "M006",
    "services/crypto-vault/": "M006",
    "services/compliance/": "M006",
    "services/fraud/": "M006",
    "security/": "M006",
}

# Maps GitHub labels / Jira components to Module IDs
LABEL_TO_MODULE_MAP = {
    # Original Configs
    "api-gateway": "M001",
    "reconciliation-engine": "M002",
    "database-recovery": "M003",
    "deployment-system": "M004",
    "incident-response": "M005",
    "crypto-vault": "M006",
    
    # M001: API Gateway
    "api": "M001", 
    "gateway": "M001",
    "auth": "M001",
    "payment": "M001",
    "payments": "M001",
    "validation": "M001",
    "performance": "M001",
    
    # M002: Reconciliation Engine
    "reconciliation": "M002",
    "reporting": "M002",
    "settlement": "M002",
    "ledger": "M002",
    
    # M003: Database Recovery
    "database": "M003",
    "platform": "M003",
    "db": "M003",
    
    # M004: Deployment System
    "deployment": "M004",
    "sre": "M004",
    "kubernetes": "M004",
    "devops": "M004",
    "ci-cd": "M004",
    
    # M005: Incident Response
    "alerting": "M005",
    "incident": "M005",
    "monitoring": "M005",
    
    # M006: Crypto Vault & Compliance
    "crypto": "M006",
    "security": "M006",
    "fraud": "M006",
    "compliance": "M006",
    "tech-debt": "M006",

    # --- SERVICE NAME ALIASES ---
    "acmepay-api": "M001",
    "acmepay-ingress": "M001",
    "acmepay-reconciliation": "M002",
    "acmepay-db": "M003",
    "acmepay-deployments": "M004",
    "acmepay-incidents": "M005"
}

def resolve_modules_from_files(file_paths: list[str]) -> set[str]:
    """Checks the list of changed files and returns unique Module IDs."""
    resolved_modules = set()
    for file_path in file_paths:
        matched = False
        for prefix, module_id in FILE_TO_MODULE_MAP.items():
            if file_path.startswith(prefix):
                resolved_modules.add(module_id)
                matched = True
                break
        if not matched and file_path.startswith("services/"):
            # Subdirectory fallback
            parts = file_path.split("/")
            if len(parts) >= 2:
                svc_name = parts[1].lower()
                if svc_name in ("fraud", "compliance", "crypto", "security"):
                    resolved_modules.add("M006")
                elif svc_name in ("reporting", "settlement", "ledger", "reconciliation"):
                    resolved_modules.add("M002")
                elif svc_name in ("database", "db"):
                    resolved_modules.add("M003")
                else:
                    resolved_modules.add("M001")
    return resolved_modules

def resolve_modules_from_labels(labels: list[str]) -> set[str]:
    """Checks issue/PR labels and returns unique Module IDs."""
    resolved_modules = set()
    for label in labels:
        clean_label = str(label).lower().strip()
        module_id = LABEL_TO_MODULE_MAP.get(clean_label)
        if module_id:
            resolved_modules.add(module_id)
    return resolved_modules