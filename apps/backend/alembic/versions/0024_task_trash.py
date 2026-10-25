"""Add recoverable task branch trash markers."""

import sqlalchemy as sa

from alembic import op

revision = "0024_task_trash"
down_revision = "0023_task_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("trash_batch_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        "ck_tasks_trash", "tasks", "(trashed_at IS NULL) = (trash_batch_id IS NULL)"
    )
    op.create_index("ix_tasks_owner_trash", "tasks", ["user_id", "trashed_at", "created_at", "id"])
    op.create_index("ix_tasks_owner_trash_batch", "tasks", ["user_id", "trash_batch_id"])


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM tasks WHERE trashed_at IS NOT NULL)")
    ):
        raise RuntimeError("Cannot downgrade populated task trash.")
    op.drop_index("ix_tasks_owner_trash_batch", table_name="tasks")
    op.drop_index("ix_tasks_owner_trash", table_name="tasks")
    op.drop_constraint("ck_tasks_trash", "tasks", type_="check")
    op.drop_column("tasks", "trash_batch_id")
    op.drop_column("tasks", "trashed_at")
