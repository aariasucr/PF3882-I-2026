"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasklists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "in_progress", "done", "cancelled", name="taskstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("tasklist_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tasklist_id"], ["tasklists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_tasks_tasklist_id"), "tasks", ["tasklist_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_tasklist_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("tasklists")
