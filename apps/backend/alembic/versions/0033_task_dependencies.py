"""Add owner-scoped task dependencies without changing existing task data."""

import sqlalchemy as sa

from alembic import op

revision = "0033_task_dependencies"
down_revision = "0032_merge_ai_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("predecessor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.PrimaryKeyConstraint("task_id", "predecessor_id"),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_task_dependencies_task_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_task_dependencies_predecessor_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("task_id != predecessor_id", name="ck_task_dependencies_not_self"),
    )
    op.create_index(
        "ix_task_dependencies_reverse",
        "task_dependencies",
        ["user_id", "predecessor_id", "task_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE task_dependencies IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM task_dependencies)")):
        raise RuntimeError("Cannot downgrade populated task dependencies.")
    op.drop_table("task_dependencies")
