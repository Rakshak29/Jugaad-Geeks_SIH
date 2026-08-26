import os
import requests
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


@dataclass
class JiraRecord:
    source_native_id: str
    payload: dict
    record_type: str = "jira_issue"


class JiraAdapter:

    def __init__(self, base_url=None, email=None, api_token=None):
        self.base_url = (base_url or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        email = (email or os.getenv("JIRA_EMAIL", "")).strip()
        api_token = (api_token or os.getenv("JIRA_API_TOKEN", "")).strip()
        self.auth = (email, api_token) if email and api_token else None

        self.headers = {
            "Accept": "application/json"
        }
        self.raw_data = {
            "issues": [],
            "base_url": self.base_url
        }

    def fetch_issue(self, issue_key):
        """Fetch a specific Jira issue by key (e.g. SCRUM-140)."""
        issue_key = issue_key.strip()
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"

        try:
            response = requests.get(
                url,
                headers=self.headers,
                auth=self.auth,
                timeout=20
            )

            if response.status_code == 200:
                data = response.json()
                self.raw_data["issues"].append(data)
                yield JiraRecord(
                    source_native_id=data.get("key", issue_key),
                    payload=data,
                    record_type="jira_issue"
                )
            else:
                print(f"Jira fetch_issue {issue_key} returned status {response.status_code}")
        except Exception as err:
            print(f"Error fetching Jira issue {issue_key}:", err)

    def fetch_all_issues(self, max_results=100):
        """Fetch all issues across all available Jira projects."""
        try:
            # 1. Discover projects
            r_proj = requests.get(
                f"{self.base_url}/rest/api/3/project",
                headers=self.headers,
                auth=self.auth,
                timeout=15
            )
            projects = r_proj.json() if r_proj.status_code == 200 else []
            project_keys = [p.get("key") for p in projects if p.get("key")]
            if not project_keys:
                project_keys = ["SCRUM"]

            fields = "summary,assignee,reporter,components,status,created,updated,description,labels,issuetype"

            for pkey in project_keys:
                next_token = None
                while True:
                    url = f"{self.base_url}/rest/api/3/search/jql"
                    params = {
                        "jql": f"project = {pkey} ORDER BY created DESC",
                        "fields": fields,
                        "maxResults": 100
                    }
                    if next_token:
                        params["nextPageToken"] = next_token

                    response = requests.get(
                        url,
                        headers=self.headers,
                        auth=self.auth,
                        params=params,
                        timeout=25
                    )

                    if response.status_code == 200:
                        data = response.json()
                        issues = data.get("issues", [])
                        for issue in issues:
                            self.raw_data["issues"].append(issue)
                            yield JiraRecord(
                                source_native_id=issue.get("key", str(issue.get("id", ""))),
                                payload=issue,
                                record_type="jira_issue"
                            )
                        next_token = data.get("nextPageToken")
                        if not next_token or data.get("isLast", False):
                            break
                    else:
                        print(f"Jira search in project {pkey} returned {response.status_code}: {response.text[:200]}")
                        break
        except Exception as err:
            print("Error in Jira fetch_all_issues:", err)