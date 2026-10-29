"""Owner-selected, default-disabled proactive review settings."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0039_ai_review_settings"
down_revision = "0038_ai_action_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_review_settings",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("offering_version", sa.Integer()),
        sa.Column("next_scan_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.CheckConstraint("version > 0", name="ck_ai_review_settings_version"),
        sa.CheckConstraint(
            "jsonb_typeof(configuration) = 'object' AND jsonb_typeof(state) = 'object'",
            name="ck_ai_review_settings_json",
        ),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE ai_review_settings IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM ai_review_settings)")):
        raise RuntimeError("Cannot discard retained AI review settings.")
    op.drop_table("ai_review_settings")
