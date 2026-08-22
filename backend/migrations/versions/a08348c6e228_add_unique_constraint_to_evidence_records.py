"""add unique constraint to evidence_records

Revision ID: a08348c6e228
Revises: 108348c6e227
Create Date: 2026-08-22 23:12:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a08348c6e228'
down_revision: Union[str, None] = '108348c6e227'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def constraint_exists(constraint_name: str, table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = inspector.get_unique_constraints(table_name)
    for c in constraints:
        if c.get("name") == constraint_name:
            return True
    return False


def upgrade() -> None:
    if not constraint_exists('uq_evidence_record_natural_key', 'evidence_records'):
        op.create_unique_constraint(
            'uq_evidence_record_natural_key',
            'evidence_records',
            ['employee_id', 'capability_id', 'module_id', 'source', 'source_ref']
        )


def downgrade() -> None:
    if constraint_exists('uq_evidence_record_natural_key', 'evidence_records'):
        op.drop_constraint(
            'uq_evidence_record_natural_key',
            'evidence_records',
            type_='unique'
        )
