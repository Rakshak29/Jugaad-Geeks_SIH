# mapper.py

# Replace these keys with your actual folder structure 
# and the values with the actual Module IDs from your database.
FILE_TO_MODULE_MAP = {
    "services/api/": "M001",           # e.g., API Gateway Module
    "services/payments/": "M002",      # e.g., Payments Module
    "frontend/src/": "M003",           # e.g., Frontend Module
    "infrastructure/": "M004"          # e.g., DevOps/Infra Module
}

def resolve_modules_from_files(file_paths: list[str]) -> set[str]:
    """
    Checks the list of changed files and returns the unique Module IDs touched.
    """
    resolved_modules = set()
    
    for file_path in file_paths:
        for prefix, module_id in FILE_TO_MODULE_MAP.items():
            if file_path.startswith(prefix):
                resolved_modules.add(module_id)
                break  # Stop checking prefixes once we find a match for this file
                
    return resolved_modules