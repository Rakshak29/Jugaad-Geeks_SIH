from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from backend.database import Base


class RawGitHubCommit(Base):
    """Raw GitHub commit log record."""
    __tablename__ = "raw_github_commits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commit_id = Column(String(100), unique=True, nullable=False, index=True)
    author_id = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    message = Column(Text, nullable=False)
    files_changed = Column(JSON, nullable=False)
    lines_added = Column(Integer, nullable=False)
    lines_deleted = Column(Integer, nullable=False)
    branch = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<RawGitHubCommit(commit_id='{self.commit_id}', author_id='{self.author_id}')>"


class RawGitHubPullRequest(Base):
    """Raw GitHub pull request record."""
    __tablename__ = "raw_github_pull_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pr_id = Column(String(100), unique=True, nullable=False, index=True)
    author_id = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False)
    files = Column(JSON, nullable=False)
    target_branch = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<RawGitHubPullRequest(pr_id='{self.pr_id}', author_id='{self.author_id}')>"


class RawGitHubReview(Base):
    """Raw GitHub code review record."""
    __tablename__ = "raw_github_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(String(100), unique=True, nullable=False, index=True)
    pr_id = Column(String(100), nullable=False, index=True)
    reviewer_id = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    state = Column(String(50), nullable=False)
    comments = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<RawGitHubReview(review_id='{self.review_id}', reviewer_id='{self.reviewer_id}')>"


class RawGitHubIssue(Base):
    """Raw GitHub issue tracker record."""
    __tablename__ = "raw_github_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_id = Column(String(100), unique=True, nullable=False, index=True)
    author_id = Column(String(50), nullable=False, index=True)
    assignee_id = Column(String(50), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False)
    labels = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<RawGitHubIssue(issue_id='{self.issue_id}', author_id='{self.author_id}')>"


class RawJiraIssue(Base):
    """Raw Jira ticket record."""
    __tablename__ = "raw_jira_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jira_id = Column(String(100), unique=True, nullable=False, index=True)
    reporter_id = Column(String(50), nullable=False, index=True)
    assignee_id = Column(String(50), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    issue_type = Column(String(50), nullable=False)
    summary = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False)
    components = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<RawJiraIssue(jira_id='{self.jira_id}', assignee_id='{self.assignee_id}')>"


class RawIncident(Base):
    """Raw production incident log record."""
    __tablename__ = "raw_incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(100), unique=True, nullable=False, index=True)
    reporter_id = Column(String(50), nullable=False, index=True)
    lead_responder_id = Column(String(50), nullable=False, index=True)
    participants = Column(JSON, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    title = Column(String(255), nullable=False)
    severity = Column(String(50), nullable=False)
    service = Column(String(100), nullable=False)
    summary = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    action_items = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<RawIncident(incident_id='{self.incident_id}', lead='{self.lead_responder_id}')>"


class RawDeployment(Base):
    """Raw continuous deployment log record."""
    __tablename__ = "raw_deployments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(String(100), unique=True, nullable=False, index=True)
    deployed_by = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    environment = Column(String(50), nullable=False)
    service = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    commit_hash = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<RawDeployment(deployment_id='{self.deployment_id}', deployed_by='{self.deployed_by}')>"


class RawDocument(Base):
    """Raw technical documentation record."""
    __tablename__ = "raw_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(100), unique=True, nullable=False, index=True)
    author_id = Column(String(50), nullable=False, index=True)
    last_modified_by = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    doc_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    service = Column(String(100), nullable=True)
    content_summary = Column(Text, nullable=True)
    filepath = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<RawDocument(doc_id='{self.doc_id}', author_id='{self.author_id}')>"
