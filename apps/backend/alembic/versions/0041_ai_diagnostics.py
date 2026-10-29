"""Opt-in owned AI diagnostic capture and manual review."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0041_ai_diagnostics"
down_revision = "0040_ai_review_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_diagnostic_chats",
        sa.Column("conversation_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_diagnostic_chat_owner",
        ),
    )
    op.create_table(
        "ai_diagnostic_runs",
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_diagnostic_capture_chat",
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("events", postgresql.JSONB(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("verdict", sa.String(10), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            ondelete="CASCADE",
            name="fk_ai_diagnostic_run_owner",
        ),
        sa.CheckConstraint(
            "verdict IN ('unreviewed', 'passed', 'failed')", name="ck_ai_diagnostic_verdict"
        ),
        sa.CheckConstraint("octet_length(note) <= 8000", name="ck_ai_diagnostic_note"),
        sa.CheckConstraint(
            "jsonb_typeof(events) = 'array' AND jsonb_array_length(events) <= 64 "
            "AND octet_length(events::text) <= 262144",
            name="ck_ai_diagnostic_events",
        ),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE ai_diagnostic_chats, ai_diagnostic_runs IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM ai_diagnostic_runs)")):
        raise RuntimeError("Clear retained diagnostics before downgrade.")
    op.drop_table("ai_diagnostic_runs")
    op.drop_table("ai_diagnostic_chats")
