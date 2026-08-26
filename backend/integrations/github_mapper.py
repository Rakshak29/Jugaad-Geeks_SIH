def map_commit(record):
    payload = record.payload

    author = payload.get("author") or {}
    commit = payload.get("commit") or {}

    author_id = author.get("id")

    if not author_id:
        commit_author = commit.get("author") or {}
        author_id = commit_author.get("name")

    timestamp = None

    commit_author = commit.get("author") or {}

    if commit_author.get("date"):
        timestamp = commit_author["date"]

    files = payload.get("files") or []

    files_changed = [
        file.get("filename")
        for file in files
        if file.get("filename")
    ]

    return {
        "author_id": author_id,
        "commit_id": payload.get("sha"),
        "timestamp": timestamp,
        "message": commit.get("message"),
        "files_changed": files_changed,
        "lines_added": payload.get("stats", {}).get("additions", 0),
        "lines_deleted": payload.get("stats", {}).get("deletions", 0),
        "branch": None,
    }


def map_issue(record):
    payload = record.payload

    author = payload.get("user") or {}
    assignee = payload.get("assignee") or {}

    return {
        "author_id": author.get("id"),
        "issue_id": payload.get("id"),
        "assignee_id": assignee.get("id"),
        "timestamp": payload.get("created_at"),
        "title": payload.get("title"),
        "description": payload.get("body"),
        "status": payload.get("state"),
        "labels": [
            label.get("name")
            for label in payload.get("labels", [])
            if label.get("name")
        ],
    }


def map_pull_request(record):
    payload = record.payload

    author = payload.get("user") or {}

    status = "MERGED" if payload.get("merged_at") else payload.get("state")

    return {
        "author_id": author.get("id"),
        "pr_id": payload.get("id"),
        "timestamp": payload.get("created_at"),
        "title": payload.get("title"),
        "description": payload.get("body"),
        "status": status,
        "files": [],
        "target_branch": (
            payload.get("base") or {}
        ).get("ref"),
    }


def map_review(record):
    payload = record.payload

    reviewer = payload.get("user") or {}

    return {
        "reviewer_id": reviewer.get("id"),
        "review_id": payload.get("id"),
        "pr_id": payload.get("pull_request_number"),
        "timestamp": payload.get("submitted_at"),
        "state": payload.get("state"),
        "comments": payload.get("body") or [],
    }