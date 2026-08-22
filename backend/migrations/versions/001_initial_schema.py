"""Initial schema creation for core and raw source tables

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-22 09:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Core tables
    op.create_table(
        'employees',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('role', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'services',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'modules',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('service_id', sa.String(length=50), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'capabilities',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Raw tables
    op.create_table(
        'raw_github_commits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('commit_id', sa.String(length=100), nullable=False),
        sa.Column('author_id', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('files_changed', sa.JSON(), nullable=False),
        sa.Column('lines_added', sa.Integer(), nullable=False),
        sa.Column('lines_deleted', sa.Integer(), nullable=False),
        sa.Column('branch', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('commit_id')
    )
    op.create_index(op.f('ix_raw_github_commits_author_id'), 'raw_github_commits', ['author_id'], unique=False)
    op.create_index(op.f('ix_raw_github_commits_commit_id'), 'raw_github_commits', ['commit_id'], unique=True)

    op.create_table(
        'raw_github_pull_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pr_id', sa.String(length=100), nullable=False),
        sa.Column('author_id', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('files', sa.JSON(), nullable=False),
        sa.Column('target_branch', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pr_id')
    )
    op.create_index(op.f('ix_raw_github_pull_requests_author_id'), 'raw_github_pull_requests', ['author_id'], unique=False)
    op.create_index(op.f('ix_raw_github_pull_requests_pr_id'), 'raw_github_pull_requests', ['pr_id'], unique=True)

    op.create_table(
        'raw_github_reviews',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('review_id', sa.String(length=100), nullable=False),
        sa.Column('pr_id', sa.String(length=100), nullable=False),
        sa.Column('reviewer_id', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state', sa.String(length=50), nullable=False),
        sa.Column('comments', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('review_id')
    )
    op.create_index(op.f('ix_raw_github_reviews_pr_id'), 'raw_github_reviews', ['pr_id'], unique=False)
    op.create_index(op.f('ix_raw_github_reviews_review_id'), 'raw_github_reviews', ['review_id'], unique=True)
    op.create_index(op.f('ix_raw_github_reviews_reviewer_id'), 'raw_github_reviews', ['reviewer_id'], unique=False)

    op.create_table(
        'raw_github_issues',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('issue_id', sa.String(length=100), nullable=False),
        sa.Column('author_id', sa.String(length=50), nullable=False),
        sa.Column('assignee_id', sa.String(length=50), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('labels', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('issue_id')
    )
    op.create_index(op.f('ix_raw_github_issues_assignee_id'), 'raw_github_issues', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_raw_github_issues_author_id'), 'raw_github_issues', ['author_id'], unique=False)
    op.create_index(op.f('ix_raw_github_issues_issue_id'), 'raw_github_issues', ['issue_id'], unique=True)

    op.create_table(
        'raw_jira_issues',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('jira_id', sa.String(length=100), nullable=False),
        sa.Column('reporter_id', sa.String(length=50), nullable=False),
        sa.Column('assignee_id', sa.String(length=50), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('issue_type', sa.String(length=50), nullable=False),
        sa.Column('summary', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('components', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jira_id')
    )
    op.create_index(op.f('ix_raw_jira_issues_assignee_id'), 'raw_jira_issues', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_raw_jira_issues_jira_id'), 'raw_jira_issues', ['jira_id'], unique=True)
    op.create_index(op.f('ix_raw_jira_issues_reporter_id'), 'raw_jira_issues', ['reporter_id'], unique=False)

    op.create_table(
        'raw_incidents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('incident_id', sa.String(length=100), nullable=False),
        sa.Column('reporter_id', sa.String(length=50), nullable=False),
        sa.Column('lead_responder_id', sa.String(length=50), nullable=False),
        sa.Column('participants', sa.JSON(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('severity', sa.String(length=50), nullable=False),
        sa.Column('service', sa.String(length=100), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('action_items', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id')
    )
    op.create_index(op.f('ix_raw_incidents_incident_id'), 'raw_incidents', ['incident_id'], unique=True)
    op.create_index(op.f('ix_raw_incidents_lead_responder_id'), 'raw_incidents', ['lead_responder_id'], unique=False)
    op.create_index(op.f('ix_raw_incidents_reporter_id'), 'raw_incidents', ['reporter_id'], unique=False)

    op.create_table(
        'raw_deployments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('deployment_id', sa.String(length=100), nullable=False),
        sa.Column('deployed_by', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('environment', sa.String(length=50), nullable=False),
        sa.Column('service', sa.String(length=100), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('commit_hash', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('deployment_id')
    )
    op.create_index(op.f('ix_raw_deployments_deployed_by'), 'raw_deployments', ['deployed_by'], unique=False)
    op.create_index(op.f('ix_raw_deployments_deployment_id'), 'raw_deployments', ['deployment_id'], unique=True)

    op.create_table(
        'raw_documents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('doc_id', sa.String(length=100), nullable=False),
        sa.Column('author_id', sa.String(length=50), nullable=False),
        sa.Column('last_modified_by', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('doc_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('service', sa.String(length=100), nullable=True),
        sa.Column('content_summary', sa.Text(), nullable=True),
        sa.Column('filepath', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('doc_id')
    )
    op.create_index(op.f('ix_raw_documents_author_id'), 'raw_documents', ['author_id'], unique=False)
    op.create_index(op.f('ix_raw_documents_doc_id'), 'raw_documents', ['doc_id'], unique=True)


def downgrade() -> None:
    op.drop_table('raw_documents')
    op.drop_table('raw_deployments')
    op.drop_table('raw_incidents')
    op.drop_table('raw_jira_issues')
    op.drop_table('raw_github_issues')
    op.drop_table('raw_github_reviews')
    op.drop_table('raw_github_pull_requests')
    op.drop_table('raw_github_commits')
    op.drop_table('capabilities')
    op.drop_table('modules')
    op.drop_table('services')
    op.drop_table('employees')
