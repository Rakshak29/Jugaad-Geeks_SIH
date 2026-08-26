import os
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

try:
    from backend.integrations.jira_adapter import JiraAdapter
except ImportError:
    from jira_adapter import JiraAdapter


BASE_URL = os.getenv("JIRA_BASE_URL", "https://jira.atlassian.com")

ISSUE_KEY = "DEMO-1"


adapter = JiraAdapter(
    base_url=BASE_URL
)


records = list(
    adapter.fetch_issue(ISSUE_KEY)
)


print(f"Fetched {len(records)} Jira records")


for record in records:

    print("\n----------------------------")

    print("ID:", record.source_native_id)

    print("Payload keys:", list(record.payload.keys()))