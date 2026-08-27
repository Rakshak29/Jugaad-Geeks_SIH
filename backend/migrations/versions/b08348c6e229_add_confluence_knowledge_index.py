"""add confluence knowledge index tables

Creates the three tables the Capability Gap RAG needs. Purely additive: no
existing table is altered and the scoring pipeline is untouched.

Written to be safe to run against a database where `Base.metadata.create_all`
(via `doctor.py --fix`) already made these tables, which is how they came to
exist during development -- each object is created only when absent, so a
mixed-history database converges instead of erroring.

Revision ID: b08348c6e229
Revises: a08348c6e228
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b08348c6e229'
down_revision: Union[str, None] = 'a08348c6e228'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return any(ix.get("name") == index_name for ix in _inspector().get_indexes(table_name))


def create_index_if_absent(index_name: str, table_name: str, columns: list[str]) -> None:
    if not index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def drop_index_if_present(index_name: str, table_name: str) -> None:
    if index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not table_exists('confluence_pages'):
        op.create_table(
            'confluence_pages',
            # Confluence's own numeric page id, kept as text.
            sa.Column('id', sa.String(length=50), nullable=False),
            sa.Column('space_key', sa.String(length=100), nullable=False),
            sa.Column('space_name', sa.String(length=255), nullable=True),
            sa.Column('title', sa.String(length=500), nullable=False),
            sa.Column('url', sa.String(length=1000), nullable=False),
            # version is kept for provenance; content_hash is the re-sync gate,
            # because a deployment that omits `version` from the pages listing
            # would otherwise make every page look permanently unchanged.
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('content_hash', sa.String(length=64), nullable=True),
            sa.Column('labels', sa.JSON(), nullable=False),
            sa.Column('ancestor_titles', sa.JSON(), nullable=False),
            sa.Column('body_text', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
    create_index_if_absent('ix_confluence_pages_space_key', 'confluence_pages', ['space_key'])
    create_index_if_absent('ix_confluence_pages_content_hash', 'confluence_pages', ['content_hash'])

    if not table_exists('confluence_sections'):
        op.create_table(
            'confluence_sections',
            # "<page_id>#<ordinal>" -- deterministic, so re-parsing the same
            # body yields the same section ids.
            sa.Column('id', sa.String(length=120), nullable=False),
            sa.Column('page_id', sa.String(length=50), nullable=False),
            sa.Column('ordinal', sa.Integer(), nullable=False),
            # NULL heading = the lead-in text before a page's first heading.
            sa.Column('heading', sa.String(length=500), nullable=True),
            sa.Column('level', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('text', sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(['page_id'], ['confluence_pages.id']),
            sa.PrimaryKeyConstraint('id'),
        )
    create_index_if_absent('ix_confluence_sections_page_id', 'confluence_sections', ['page_id'])

    if not table_exists('confluence_page_capabilities'):
        op.create_table(
            'confluence_page_capabilities',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('page_id', sa.String(length=50), nullable=False),
            sa.Column('capability_id', sa.String(length=50), nullable=False),
            # 'label' | 'ancestor' | 'space' -- structural, exact lookups.
            # Keyword matches are computed per query and never stored.
            sa.Column('match_type', sa.String(length=20), nullable=False),
            # Human-readable justification, e.g. ["label:database-recovery -> M003"].
            sa.Column('evidence', sa.JSON(), nullable=False),
            sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
            sa.ForeignKeyConstraint(['page_id'], ['confluence_pages.id']),
            sa.ForeignKeyConstraint(['capability_id'], ['capabilities.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'page_id', 'capability_id', 'match_type', name='uq_page_capability_match'
            ),
        )
    create_index_if_absent(
        'ix_confluence_page_capabilities_page_id', 'confluence_page_capabilities', ['page_id'])
    create_index_if_absent(
        'ix_confluence_page_capabilities_capability_id',
        'confluence_page_capabilities', ['capability_id'])


def downgrade() -> None:
    # Dropped children-first so the foreign keys unwind cleanly.
    if table_exists('confluence_page_capabilities'):
        drop_index_if_present(
            'ix_confluence_page_capabilities_capability_id', 'confluence_page_capabilities')
        drop_index_if_present(
            'ix_confluence_page_capabilities_page_id', 'confluence_page_capabilities')
        op.drop_table('confluence_page_capabilities')

    if table_exists('confluence_sections'):
        drop_index_if_present('ix_confluence_sections_page_id', 'confluence_sections')
        op.drop_table('confluence_sections')

    if table_exists('confluence_pages'):
        drop_index_if_present('ix_confluence_pages_content_hash', 'confluence_pages')
        drop_index_if_present('ix_confluence_pages_space_key', 'confluence_pages')
        op.drop_table('confluence_pages')
