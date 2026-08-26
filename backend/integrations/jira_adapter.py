import requests
from dataclasses import dataclass


@dataclass
class JiraRecord:
    source_native_id: str
    payload: dict


class JiraAdapter:

    def __init__(self, base_url, email=None, api_token=None):
        self.base_url = base_url.rstrip("/")
        self.auth = (email, api_token) if email and api_token else None

        self.headers = {
            "Accept": "application/json"
        }

    def fetch_issue(self, issue_key):

        url = f"{self.base_url}/rest/api/latest/issue/{issue_key}"

        response = requests.get(
            url,
            headers=self.headers,
            auth=self.auth,
            timeout=30
        )

        print("URL:", url)
        print("Status:", response.status_code)
        print("Content-Type:", response.headers.get("content-type"))

        if response.status_code != 200:
            print("Response:")
            print(response.text[:1000])
            response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            print("Jira did not return JSON.")
            print("Response:")
            print(response.text[:1000])
            raise

        yield JiraRecord(
            source_native_id=issue_key,
            payload=data
        )