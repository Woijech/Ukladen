"""Add optional owner-scoped task parent references."""

import sqlalchemy as sa

from alembic import op

revision = "0023_task_hierarchy"
down_revision = "0022_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("parent_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("uq_tasks_id_user", "tasks", ["id", "user_id"])
    op.create_foreign_key(
        "fk_tasks_parent_owner", "tasks", "tasks", ["parent_id", "user_id"], ["id", "user_id"]
    )
    op.create_check_constraint("ck_tasks_parent", "tasks", "parent_id IS NULL OR parent_id != id")
    op.create_index("ix_tasks_owner_parent", "tasks", ["user_id", "parent_id"])


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM tasks WHERE parent_id IS NOT NULL)")
    ):
        raise RuntimeError("Cannot downgrade populated task hierarchy.")
    op.drop_index("ix_tasks_owner_parent", table_name="tasks")
    op.drop_constraint("ck_tasks_parent", "tasks", type_="check")
    op.drop_constraint("fk_tasks_parent_owner", "tasks", type_="foreignkey")
    op.drop_constraint("uq_tasks_id_user", "tasks", type_="unique")
    op.drop_column("tasks", "parent_id")
