"""Store exact task plan previews and durable application receipts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0036_task_plans"
down_revision = "0035_task_work_planning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'rejected', 'expired')", name="ck_task_plan_status"
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE task_plans IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM task_plans)")):
        raise RuntimeError("Cannot downgrade populated task plans or receipts.")
    op.drop_table("task_plans")
