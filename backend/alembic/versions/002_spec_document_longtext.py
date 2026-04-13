"""change spec_document to LONGTEXT

Revision ID: 002
Revises: 001
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'projects',
        'spec_document',
        existing_type=sa.Text(),
        type_=sa.Text(length=4294967295),
        existing_nullable=True
    )


def downgrade():
    op.alter_column(
        'projects',
        'spec_document',
        existing_type=sa.Text(length=4294967295),
        type_=sa.Text(),
        existing_nullable=True
    )
