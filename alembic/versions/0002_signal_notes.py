"""Add independent human notes for immutable signal events.

Revision ID: 0002_signal_notes
Revises: 0001_initial_schema
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0002_signal_notes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("signal_note"):
        op.create_table(
            "signal_note",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("signal_event_id", sa.Integer(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["signal_event_id"], ["signal_event.id"]),
        )
        op.create_index("ix_signal_note_signal_event_id", "signal_note", ["signal_event_id"])
        op.create_index(
            "idx_signal_note_created",
            "signal_note",
            ["signal_event_id", "created_at"],
        )

    paper_trade_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("paper_trade")
    }
    if "request_id" not in paper_trade_columns:
        op.add_column("paper_trade", sa.Column("request_id", sa.String(64), nullable=True))
        op.create_index(
            "ix_paper_trade_request_id",
            "paper_trade",
            ["request_id"],
            unique=True,
        )


def downgrade() -> None:
    paper_trade_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("paper_trade")
    }
    if "request_id" in paper_trade_columns:
        op.drop_index("ix_paper_trade_request_id", table_name="paper_trade")
        op.drop_column("paper_trade", "request_id")
    if sa.inspect(op.get_bind()).has_table("signal_note"):
        op.drop_table("signal_note")
