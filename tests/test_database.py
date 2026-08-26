import pytest
from sqlalchemy import inspect, text
from backend.database import engine, init_db, SessionLocal, drop_db
from backend.models import (
    Employee,
    Capability,
    Service,
    Module,
    RawGitHubCommit,
    RawGitHubPullRequest,
    RawGitHubReview,
    RawGitHubIssue,
    RawJiraIssue,
    RawIncident,
    RawDeployment,
    RawDocument,
)
from backend.seed import seed_database


def test_database_connection():
    """Verify that PostgreSQL database connection works."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_table_creation_and_migration():
    """Verify that core and raw tables can be created/migrated successfully."""
    init_db(bind_engine=engine)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    expected_tables = {
        "employees",
        "services",
        "modules",
        "capabilities",
        "raw_github_commits",
        "raw_github_pull_requests",
        "raw_github_reviews",
        "raw_github_issues",
        "raw_jira_issues",
        "raw_incidents",
        "raw_deployments",
        "raw_documents",
    }

    assert expected_tables.issubset(existing_tables), f"Missing tables: {expected_tables - existing_tables}"


def test_seed_data_insertion_and_counts():
    """Verify that seed script populates data and record counts match JSON files exactly."""
    drop_db()
    init_db()
    counts = seed_database()
    db = SessionLocal()

    try:
        # Core config record counts
        assert db.query(Employee).count() == 5
        assert db.query(Capability).count() == 5
        assert db.query(Service).count() == 4
        assert db.query(Module).count() == 6


        # Raw telemetry record counts
        assert db.query(RawGitHubCommit).count() == 35
        assert db.query(RawGitHubPullRequest).count() == 12
        assert db.query(RawGitHubReview).count() == 16
        assert db.query(RawGitHubIssue).count() == 12
        assert db.query(RawJiraIssue).count() == 16
        assert db.query(RawIncident).count() == 9
        assert db.query(RawDeployment).count() == 9
        assert db.query(RawDocument).count() == 6

        # Total raw records assertion
        total_raw = (
            db.query(RawGitHubCommit).count()
            + db.query(RawGitHubPullRequest).count()
            + db.query(RawGitHubReview).count()
            + db.query(RawGitHubIssue).count()
            + db.query(RawJiraIssue).count()
            + db.query(RawIncident).count()
            + db.query(RawDeployment).count()
            + db.query(RawDocument).count()
        )
        assert total_raw == 115

    finally:
        db.close()
