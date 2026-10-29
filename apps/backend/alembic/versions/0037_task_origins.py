"""Preserve task extraction provenance independently of chat retention."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0037_task_origins"
down_revision = "0036_task_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_origins",
        sa.Column("task_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"], ["tasks.id", "tasks.user_id"], ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE task_origins IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM task_origins)")):
        raise RuntimeError("Cannot downgrade populated task extraction provenance.")
    op.drop_table("task_origins")
