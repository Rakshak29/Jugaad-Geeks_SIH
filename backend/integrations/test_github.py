import os

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