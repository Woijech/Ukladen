"""Exact confirmed actions and content-free execution receipts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0031_ai_action_proposals"
down_revision = "0030_ai_document_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_action_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("interrupt_id", sa.Text(), nullable=False),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_action_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            ondelete="CASCADE",
            name="fk_ai_action_run",
        ),
        sa.UniqueConstraint("run_id", name="uq_ai_action_run"),
        sa.CheckConstraint(
            "expires_at = created_at + interval '24 hours'", name="ck_ai_action_expiry"
        ),
        sa.CheckConstraint("digest ~ '^[a-f0-9]{64}$'", name="ck_ai_action_digest"),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 2097152",
            name="ck_ai_action_payload",
        ),
    )
    op.create_index(
        "ix_ai_action_chat",
        "ai_action_proposals",
        ["user_id", "conversation_id", "created_at", "id"],
    )
    op.create_table(
        "ai_action_receipts",
        sa.Column("proposal_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("outcomes", postgresql.JSONB(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('applied','rejected','expired','conflict','superseded')",
            name="ck_ai_action_receipt_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(outcomes) = 'array' AND jsonb_array_length(outcomes) <= 8",
            name="ck_ai_action_receipt_outcomes",
        ),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE ai_action_proposals, ai_action_receipts IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM ai_action_proposals) OR
            EXISTS (SELECT 1 FROM ai_action_receipts) THEN
            RAISE EXCEPTION 'Cannot downgrade: retained action data/replay protection';
        END IF;
    END $$""")
    op.drop_table("ai_action_receipts")
    op.drop_table("ai_action_proposals")
