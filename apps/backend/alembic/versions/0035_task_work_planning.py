"""Preserve explicit work accounting, preferences and task sessions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0035_task_work_planning"
down_revision = "0034_task_page_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("remaining_minutes", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_tasks_remaining", "tasks", "remaining_minutes BETWEEN 0 AND 525600"
    )
    op.create_table(
        "task_work_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pinned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("cancelled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"], ["tasks.id", "tasks.user_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "ends_at > starts_at AND ends_at <= starts_at + interval '24 hours'",
            name="ck_work_session_interval",
        ),
        sa.CheckConstraint("version > 0", name="ck_work_session_version"),
    )
    op.create_index(
        "ix_work_sessions_owner_time", "task_work_sessions", ["user_id", "starts_at", "ends_at"]
    )
    op.create_table(
        "task_work_preferences",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("session_minutes", sa.Integer(), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        sa.Column("windows", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_work_preferences_version"),
        sa.CheckConstraint(
            "session_minutes BETWEEN 15 AND 240 AND break_minutes BETWEEN 0 AND 120",
            name="ck_work_preferences_lengths",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE task_work_sessions, task_work_preferences, tasks IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM task_work_sessions) "
            "OR EXISTS (SELECT 1 FROM task_work_preferences) "
            "OR EXISTS (SELECT 1 FROM tasks WHERE remaining_minutes IS NOT NULL)"
        )
    ):
        raise RuntimeError("Cannot downgrade populated task planning data.")
    op.drop_table("task_work_preferences")
    op.drop_table("task_work_sessions")
    op.drop_constraint("ck_tasks_remaining", "tasks")
    op.drop_column("tasks", "remaining_minutes")
