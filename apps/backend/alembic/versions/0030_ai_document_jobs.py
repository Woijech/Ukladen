"""Durable complete-source processing, with no per-job provider-call allowance."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0030_ai_document_jobs"
down_revision = "0029_search_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_ai_attempts_number", "ai_provider_attempts", type_="check")
    op.create_check_constraint("ck_ai_attempts_number", "ai_provider_attempts", "number >= 1")
    op.create_table(
        "ai_document_jobs",
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "answer_message_id",
            sa.Uuid(),
            sa.ForeignKey("ai_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("selection", postgresql.JSONB(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("notes", postgresql.JSONB(), nullable=False, server_default="[]"),
        *[
            sa.Column(name, sa.Integer(), nullable=False, server_default="0")
            for name in (
                "source_index",
                "offset",
                "processed_characters",
                "total_characters",
                "steps",
                "failures",
            )
        ],
        sa.Column("phase", sa.Text(), nullable=False, server_default="reading"),
        sa.Column("lease", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            ondelete="CASCADE",
            name="fk_ai_document_run",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_document_conversation",
        ),
        sa.CheckConstraint(
            'source_index >= 0 AND "offset" >= 0 AND steps >= 0 AND failures >= 0 '
            "AND processed_characters >= 0 AND total_characters >= processed_characters",
            name="ck_ai_document_progress",
        ),
        sa.CheckConstraint(
            "phase IN ('reading','combining','completed','failed')", name="ck_ai_document_phase"
        ),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE ai_document_jobs, ai_provider_attempts IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM ai_document_jobs) OR EXISTS
            (SELECT 1 FROM ai_provider_attempts WHERE number > 4) THEN
            RAISE EXCEPTION 'Cannot downgrade: document analyses and their usage must be preserved';
        END IF;
    END $$""")
    op.drop_table("ai_document_jobs")
    op.drop_constraint("ck_ai_attempts_number", "ai_provider_attempts", type_="check")
    op.create_check_constraint(
        "ck_ai_attempts_number", "ai_provider_attempts", "number BETWEEN 1 AND 4"
    )
