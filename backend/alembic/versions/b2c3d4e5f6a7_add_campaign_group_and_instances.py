"""add lead_group and allowed_instances to campaigns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("lead_group", sa.String(100), nullable=True))
    op.add_column("campaigns", sa.Column("allowed_instances", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("campaigns", "allowed_instances")
    op.drop_column("campaigns", "lead_group")
