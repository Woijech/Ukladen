"""Add independent versioned tasks without scheduling side effects."""

import sqlalchemy as sa

from alembic import op

revision = "0022_tasks"
down_revision = "0021_google_email_confirmations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(16), server_default="todo", nullable=False),
        sa.Column("priority", sa.String(16), server_default="normal", nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("estimated_minutes", sa.Integer()),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200 AND title = btrim(title) "
            "AND title ~ '[^[:space:]]'",
            name="ck_tasks_title",
        ),
        sa.CheckConstraint("char_length(description) <= 10000", name="ck_tasks_description"),
        sa.CheckConstraint(
            "status IN ('todo', 'in_progress', 'done', 'cancelled')", name="ck_tasks_status"
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')", name="ck_tasks_priority"
        ),
        sa.CheckConstraint("estimated_minutes BETWEEN 1 AND 525600", name="ck_tasks_effort"),
        sa.CheckConstraint("version > 0", name="ck_tasks_version"),
    )
    op.create_index("ix_tasks_owner_created", "tasks", ["user_id", "created_at", "id"])


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM tasks)")):
        raise RuntimeError("Cannot downgrade populated task storage.")
    op.drop_table("tasks")
