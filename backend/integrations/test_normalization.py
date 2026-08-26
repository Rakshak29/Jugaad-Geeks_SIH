import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

try:
    from backend.integrations.github_adapter import GitHubAdapter
    from backend.integrations.github_mapper import (
        map_commit,
        map_issue,
        map_pull_request,
        map_review,
    )
except ImportError:
    from github_adapter import GitHubAdapter
    from github_mapper import (
        map_commit,
        map_issue,
        map_pull_request,
        map_review,
    )

from backend.ingestion.github.commit_extractor import extract_commit_event
from backend.ingestion.github.issue_extractor import extract_issue_event
from backend.ingestion.github.pr_extractor import extract_pr_event
from backend.ingestion.github.review_extractor import extract_review_event


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

REPOSITORY = os.getenv("GITHUB_REPO", "krish-exe/sih26")
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