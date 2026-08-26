import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

email = os.getenv("JIRA_EMAIL")
token = os.getenv("JIRA_API_TOKEN")

JIRA_URL = os.getenv("JIRA_BASE_URL", "https://acmepay-engineering.atlassian.net").rstrip("/")

response = requests.get(
    f"{JIRA_URL}/rest/api/3/myself",
    auth=(email, token),
    headers={
        "Accept": "application/json"
    },
    timeout=30
)

print("Status:", response.status_code)

if response.ok:
    data = response.json()
    print("Connected successfully!")
    print("Account:", data.get("displayName"))
else:
    print("Connection failed:")
    print(response.text)