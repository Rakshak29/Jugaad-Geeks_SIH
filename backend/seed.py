import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from backend.database import SessionLocal, init_db
from backend.models import (
    Employee,
    Service,
    Module,
    Capability,
    RawGitHubCommit,
    RawGitHubPullRequest,
    RawGitHubReview,
    RawGitHubIssue,
    RawJiraIssue,
    RawIncident,
    RawDeployment,
    RawDocument,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_CONFIG_DIR = BASE_DIR / "data" / "config"
DATA_RAW_DIR = BASE_DIR / "data" / "raw"


def parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO format timestamp string into python datetime object."""
    if not dt_str:
        return None
    # Standard ISO string format parse
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def load_json(filepath: Path):
    """Load JSON content if file exists and is non-empty."""
    if not filepath.exists() or filepath.stat().st_size == 0:
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_database():
    """Seed PostgreSQL database with config and raw synthetic datasets."""
    init_db()
    db = SessionLocal()

    try:
        counts = {}

        # ---------------------------------------------------------
        # 1. CORE CONFIG SEED
        # ---------------------------------------------------------
        # Seed Employees
        employees_data = load_json(DATA_CONFIG_DIR / "employees.json")
        for item in employees_data:
            if not db.query(Employee).filter_by(id=item["id"]).first():
                db.add(Employee(id=item["id"], name=item["name"], role=item["role"]))
        db.commit()
        counts["employees"] = db.query(Employee).count()

        # Seed Capabilities
        capabilities_data = load_json(DATA_CONFIG_DIR / "capabilities.json")
        for item in capabilities_data:
            if not db.query(Capability).filter_by(id=item["id"]).first():
                db.add(Capability(id=item["id"], name=item["name"], description=item.get("description")))
        db.commit()
        counts["capabilities"] = db.query(Capability).count()

        # Seed Services
        services_data = load_json(DATA_CONFIG_DIR / "services.json")
        for item in services_data:
            if not db.query(Service).filter_by(id=item["id"]).first():
                db.add(Service(id=item["id"], name=item["name"], description=item.get("description")))
        db.commit()
        counts["services"] = db.query(Service).count()

        # Seed Modules and Module Capabilities
        modules_data = load_json(DATA_CONFIG_DIR / "modules.json")
        for item in modules_data:
            module = db.query(Module).filter_by(id=item["id"]).first()
            if not module:
                module = Module(
                    id=item["id"],
                    service_id=item.get("service_id"),
                    name=item["name"],
                    description=item.get("description")
                )
                db.add(module)
                db.flush()

            # Associate capabilities linked in modules.json
            cap_ids = item.get("capability_ids", [])
            for cap_id in cap_ids:
                cap = db.query(Capability).filter_by(id=cap_id).first()
                if cap and cap not in module.capabilities:
                    module.capabilities.append(cap)

        db.commit()
        counts["modules"] = db.query(Module).count()

        # ---------------------------------------------------------
        # 2. RAW SOURCE SEED
        # ---------------------------------------------------------
        # Seed GitHub Commits
        commits_data = load_json(DATA_RAW_DIR / "github" / "commits.json")
        for item in commits_data:
            if not db.query(RawGitHubCommit).filter_by(commit_id=item["commit_id"]).first():
                db.add(RawGitHubCommit(
                    commit_id=item["commit_id"],
                    author_id=item["author_id"],
                    timestamp=parse_dt(item["timestamp"]),
                    message=item["message"],
                    files_changed=item["files_changed"],
                    lines_added=item["lines_added"],
                    lines_deleted=item["lines_deleted"],
                    branch=item["branch"]
                ))
        db.commit()
        counts["raw_github_commits"] = db.query(RawGitHubCommit).count()

        # Seed GitHub Pull Requests
        prs_data = load_json(DATA_RAW_DIR / "github" / "pull_requests.json")
        for item in prs_data:
            if not db.query(RawGitHubPullRequest).filter_by(pr_id=item["pr_id"]).first():
                db.add(RawGitHubPullRequest(
                    pr_id=item["pr_id"],
                    author_id=item["author_id"],
                    timestamp=parse_dt(item["timestamp"]),
                    title=item["title"],
                    description=item.get("description"),
                    status=item["status"],
                    files=item["files"],
                    target_branch=item["target_branch"]
                ))
        db.commit()
        counts["raw_github_pull_requests"] = db.query(RawGitHubPullRequest).count()

        # Seed GitHub Reviews
        reviews_data = load_json(DATA_RAW_DIR / "github" / "reviews.json")
        for item in reviews_data:
            if not db.query(RawGitHubReview).filter_by(review_id=item["review_id"]).first():
                db.add(RawGitHubReview(
                    review_id=item["review_id"],
                    pr_id=item["pr_id"],
                    reviewer_id=item["reviewer_id"],
                    timestamp=parse_dt(item["timestamp"]),
                    state=item["state"],
                    comments=item.get("comments")
                ))
        db.commit()
        counts["raw_github_reviews"] = db.query(RawGitHubReview).count()

        # Seed GitHub Issues
        gh_issues_data = load_json(DATA_RAW_DIR / "github" / "issues.json")
        for item in gh_issues_data:
            if not db.query(RawGitHubIssue).filter_by(issue_id=item["issue_id"]).first():
                db.add(RawGitHubIssue(
                    issue_id=item["issue_id"],
                    author_id=item["author_id"],
                    assignee_id=item.get("assignee_id"),
                    timestamp=parse_dt(item["timestamp"]),
                    title=item["title"],
                    description=item.get("description"),
                    status=item["status"],
                    labels=item.get("labels")
                ))
        db.commit()
        counts["raw_github_issues"] = db.query(RawGitHubIssue).count()

        # Seed Jira Issues
        jira_data = load_json(DATA_RAW_DIR / "jira" / "issues.json")
        for item in jira_data:
            if not db.query(RawJiraIssue).filter_by(jira_id=item["jira_id"]).first():
                db.add(RawJiraIssue(
                    jira_id=item["jira_id"],
                    reporter_id=item["reporter_id"],
                    assignee_id=item.get("assignee_id"),
                    timestamp=parse_dt(item["timestamp"]),
                    updated_at=parse_dt(item.get("updated_at")),
                    issue_type=item["issue_type"],
                    summary=item["summary"],
                    description=item.get("description"),
                    status=item["status"],
                    components=item.get("components")
                ))
        db.commit()
        counts["raw_jira_issues"] = db.query(RawJiraIssue).count()

        # Seed Incidents
        incidents_data = load_json(DATA_RAW_DIR / "incidents" / "incidents.json")
        for item in incidents_data:
            if not db.query(RawIncident).filter_by(incident_id=item["incident_id"]).first():
                db.add(RawIncident(
                    incident_id=item["incident_id"],
                    reporter_id=item["reporter_id"],
                    lead_responder_id=item["lead_responder_id"],
                    participants=item["participants"],
                    timestamp=parse_dt(item["timestamp"]),
                    resolved_at=parse_dt(item.get("resolved_at")),
                    title=item["title"],
                    severity=item["severity"],
                    service=item["service"],
                    summary=item.get("summary"),
                    root_cause=item.get("root_cause"),
                    action_items=item.get("action_items")
                ))
        db.commit()
        counts["raw_incidents"] = db.query(RawIncident).count()

        # Seed Deployments
        deployments_data = load_json(DATA_RAW_DIR / "deployments" / "deployments.json")
        for item in deployments_data:
            if not db.query(RawDeployment).filter_by(deployment_id=item["deployment_id"]).first():
                db.add(RawDeployment(
                    deployment_id=item["deployment_id"],
                    deployed_by=item["deployed_by"],
                    timestamp=parse_dt(item["timestamp"]),
                    environment=item["environment"],
                    service=item["service"],
                    action=item["action"],
                    commit_hash=item.get("commit_hash"),
                    status=item["status"],
                    notes=item.get("notes")
                ))
        db.commit()
        counts["raw_deployments"] = db.query(RawDeployment).count()

        # Seed Documents
        docs_data = load_json(DATA_RAW_DIR / "documentation" / "docs.json")
        for item in docs_data:
            if not db.query(RawDocument).filter_by(doc_id=item["doc_id"]).first():
                db.add(RawDocument(
                    doc_id=item["doc_id"],
                    author_id=item["author_id"],
                    last_modified_by=item.get("last_modified_by"),
                    created_at=parse_dt(item["created_at"]),
                    updated_at=parse_dt(item.get("updated_at")),
                    doc_type=item["doc_type"],
                    title=item["title"],
                    service=item.get("service"),
                    content_summary=item.get("content_summary"),
                    filepath=item.get("filepath")
                ))
        db.commit()
        counts["raw_documents"] = db.query(RawDocument).count()

        print("Database seed completed successfully.")
        return counts

    except Exception as e:
        db.rollback()
        print("Database seed error:", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    results = seed_database()
    for table_name, count in results.items():
        print(f"  - {table_name}: {count} records")
