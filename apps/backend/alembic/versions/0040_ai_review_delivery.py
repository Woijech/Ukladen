"""Durable review slots and typed delivery through the existing inbox."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0040_ai_review_delivery"
down_revision = "0039_ai_review_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_ai_review_settings_due",
        "ai_review_settings",
        ["next_scan_at", "user_id"],
        postgresql_where=sa.text("(configuration ->> 'enabled')::boolean"),
    )
    op.create_table(
        "ai_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("slot", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("snapshot", sa.String(64), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("issue_state", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.Uuid()),
        sa.Column("discussed", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("id", "user_id", name="uq_ai_reviews_owner"),
        sa.UniqueConstraint("conversation_id", name="uq_ai_reviews_conversation"),
        sa.UniqueConstraint(
            "user_id", "configuration_version", "kind", "slot", name="uq_ai_reviews_slot"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_reviews_conversation_owner",
        ),
        sa.CheckConstraint("kind IN ('daily', 'weekly', 'warnings')", name="ck_ai_reviews_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_ai_reviews_status",
        ),
        sa.CheckConstraint(
            "configuration_version > 0 AND expires_at > created_at", name="ck_ai_reviews_lifetime"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(issue_state) = 'array' AND jsonb_typeof(configuration) = 'object'",
            name="ck_ai_reviews_issues",
        ),
    )
    op.create_index("ix_ai_reviews_pending", "ai_reviews", ["status", "created_at"])
    for name, kind in (
        ("reminder_id", sa.Uuid()),
        ("source", sa.String(8)),
        ("event_id", sa.Uuid()),
        ("starts_at", sa.DateTime(timezone=True)),
    ):
        op.alter_column("notifications", name, existing_type=kind, nullable=True)
    op.add_column(
        "notifications", sa.Column("kind", sa.String(16), nullable=False, server_default="reminder")
    )
    op.add_column("notifications", sa.Column("review_id", sa.Uuid()))
    op.create_unique_constraint("uq_notifications_review", "notifications", ["review_id"])
    op.create_foreign_key(
        "fk_notifications_review_owner",
        "notifications",
        "ai_reviews",
        ["review_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_notifications_kind",
        "notifications",
        "(kind = 'reminder' AND reminder_id IS NOT NULL AND source IS NOT NULL "
        "AND event_id IS NOT NULL AND starts_at IS NOT NULL AND review_id IS NULL) OR "
        "(kind = 'ai_review' AND reminder_id IS NULL AND source IS NULL "
        "AND event_id IS NULL AND starts_at IS NULL AND review_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.execute("LOCK TABLE ai_reviews, notifications IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM ai_reviews)")):
        raise RuntimeError("Cannot discard retained AI reviews.")
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.drop_constraint("fk_notifications_review_owner", "notifications", type_="foreignkey")
    op.drop_constraint("uq_notifications_review", "notifications", type_="unique")
    op.drop_column("notifications", "review_id")
    op.drop_column("notifications", "kind")
    for name, kind in (
        ("reminder_id", sa.Uuid()),
        ("source", sa.String(8)),
        ("event_id", sa.Uuid()),
        ("starts_at", sa.DateTime(timezone=True)),
    ):
        op.alter_column("notifications", name, existing_type=kind, nullable=False)
    op.drop_table("ai_reviews")
    op.drop_index("ix_ai_review_settings_due", table_name="ai_review_settings")
