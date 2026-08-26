import os
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

try:
    from backend.integrations.github_adapter import GitHubAdapter
except ImportError:
    from github_adapter import GitHubAdapter


REPOSITORY = "RishiBakshii/mern-ecommerce"

token = os.getenv("GITHUB_TOKEN")

if not token:
    raise RuntimeError("GITHUB_TOKEN is not set")


adapter = GitHubAdapter(
    repo=REPOSITORY,
    token=token
)

records = list(adapter.fetch())

print(f"Fetched {len(records)} GitHub records")

for record in records[:5]:
    print("\n----------------------------")
    print("ID:", record.source_native_id)
    print("Payload keys:", list(record.payload.keys()))