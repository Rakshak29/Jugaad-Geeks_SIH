from jira_adapter import JiraAdapter


BASE_URL = "https://jira.atlassian.com"

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