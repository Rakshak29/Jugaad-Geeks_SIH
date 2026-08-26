import os
import json
from dotenv import load_dotenv

from github_adapter import GitHubAdapter
from github_mapper import (
    map_commit,
    map_issue,
    map_pull_request,
    map_review,
)
from commit_parser import extract_commit_event
from issue_parser import extract_issue_event
from pr_parser import extract_pr_event
from review_parser import extract_review_event


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()

REPOSITORY = "krish-exe/sih26"

token = os.getenv("GITHUB_TOKEN")

if not token:
    raise RuntimeError(
        "GITHUB_TOKEN is not set."
    )


# =========================================================
# FETCH GITHUB RECORDS
# =========================================================

print("Starting GitHub ingestion...", flush=True)

adapter = GitHubAdapter(
    repo=REPOSITORY,
    token=token
)

records = list(
    adapter.fetch()
)


# =========================================================
# SAVE RAW DATA
# =========================================================

with open(
    "github_raw_data.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        adapter.raw_data,
        f,
        indent=2,
        ensure_ascii=False,
        default=str
    )


# =========================================================
# NORMALIZE RECORDS
# =========================================================

normalized_events = []

for record in records:
    if record.record_type == "commit":
        raw = map_commit(record)
        event = extract_commit_event(raw)
    elif record.record_type == "issue":
        raw = map_issue(record)
        event = extract_issue_event(raw)
    elif record.record_type == "pull_request":
        raw = map_pull_request(record)
        event = extract_pr_event(raw)
    elif record.record_type == "review":
        raw = map_review(record)
        event = extract_review_event(raw)
    else:
        event = None

    if event is not None:
        normalized_events.append(event)


# =========================================================
# SAVE NORMALIZED DATA
# =========================================================

with open(
    "normalized_output.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        normalized_events,
        f,
        indent=2,
        ensure_ascii=False,
        default=str
    )


# =========================================================
# FINAL OUTPUT
# =========================================================

print(
    f"Fetched {len(records)} GitHub records",
    flush=True
)