import os
import requests
from dotenv import load_dotenv

load_dotenv()

email = os.getenv("JIRA_EMAIL")
token = os.getenv("JIRA_API_TOKEN")

JIRA_URL = "https://acmepay-engineering.atlassian.net"

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