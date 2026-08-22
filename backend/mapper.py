# mapper.py

# Maps exact file path prefixes to Module IDs based on your JSON config
FILE_TO_MODULE_MAP = {
    # M001: API Gateway
    "services/api/": "M001",
    
    # M002: Reconciliation Engine
    "services/reconciliation/": "M002",
    
    # M003: Database Recovery
    "db/recovery/": "M003",
    "db/config/": "M003",
    
    # M004: Deployment System
    "deployments/": "M004",
    ".github/workflows/": "M004",
    
    # M005: Incident Response
    "config/pagerduty_routing.json": "M005",
    
    # M006: Crypto Vault (Legacy)
    "services/crypto/": "M006"
}

# Maps GitHub labels / Jira components to Module IDs
LABEL_TO_MODULE_MAP = {
    "api-gateway": "M001",
    "reconciliation-engine": "M002",
    "database-recovery": "M003",
    "deployment-system": "M004",
    "incident-response": "M005",
    "crypto-vault": "M006",
    
    # You can also add aliases here if GitHub issues use shorter labels!
    "api": "M001", 
    "bug": None # Ignore generic labels
}

def resolve_modules_from_files(file_paths: list[str]) -> set[str]:
    """Checks the list of changed files and returns unique Module IDs."""
    resolved_modules = set()
    for file_path in file_paths:
        for prefix, module_id in FILE_TO_MODULE_MAP.items():
            if file_path.startswith(prefix):
                resolved_modules.add(module_id)
                break 
    return resolved_modules

def resolve_modules_from_labels(labels: list[str]) -> set[str]:
    """Checks issue/PR labels and returns unique Module IDs."""
    resolved_modules = set()
    for label in labels:
        clean_label = label.lower().strip()
        module_id = LABEL_TO_MODULE_MAP.get(clean_label)
        if module_id:
            resolved_modules.add(module_id)
    return resolved_modules