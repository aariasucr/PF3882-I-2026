"""Add soft delete columns to tasklists and tasks

Revision ID: 002
Revises: 001
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasklists",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        ),
    )

    op.add_column(
        "tasks",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "deleted_at")
    op.drop_column("tasklists", "deleted_at")
