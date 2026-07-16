"""Initial schema baseline.

Revision ID: 0001_initial_schema
Revises: None
"""
from __future__ import annotations

from alembic import op

from market_monitor.data.models import Base


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
