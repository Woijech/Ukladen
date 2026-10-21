"""Prepare owned AI state and pinned LangGraph PostgreSQL checkpoints."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0022_ai_persistence"
down_revision = "0021_google_email_confirmations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_user_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sequence", sa.BigInteger(), nullable=False),
        sa.Column(
            "checkpoint_thread_id",
            sa.Text(),
            sa.Computed("id::text", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 200 AND title = btrim(title)",
            name="ck_ai_conversations_title",
        ),
        sa.CheckConstraint(
            "last_user_message_at IS NULL OR last_user_message_at >= created_at",
            name="ck_ai_conversations_activity",
        ),
        sa.CheckConstraint("next_sequence > 0", name="ck_ai_conversations_sequence"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_thread_id", name="uq_ai_conversations_thread"),
        sa.UniqueConstraint("id", "user_id", name="uq_ai_conversations_owner"),
    )
    op.create_index(
        "ix_ai_conversations_owner",
        "ai_conversations",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "ai_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=9), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant', 'tool')", name="ck_ai_messages_role"),
        sa.CheckConstraint(
            "octet_length(content) BETWEEN 1 AND 16384", name="ck_ai_messages_content"
        ),
        sa.CheckConstraint("sequence > 0", name="ck_ai_messages_sequence"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            name="fk_ai_messages_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_ai_messages_sequence"),
    )
    op.create_table(
        "ai_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=11), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_ai_runs_version"),
        sa.CheckConstraint(
            "provider ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$' AND "
            "model ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$'",
            name="ck_ai_runs_labels",
        ),
        sa.CheckConstraint("request_digest ~ '^[0-9a-f]{64}$'", name="ck_ai_runs_digest"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')",
            name="ck_ai_runs_status",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at AND ((status IN ('completed', 'failed', 'cancelled') "
            "AND finished_at IS NOT NULL AND finished_at = updated_at) OR "
            "(status IN ('queued', 'running', 'interrupted') AND finished_at IS NULL))",
            name="ck_ai_runs_time",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            name="fk_ai_runs_owner",
            ondelete="SET NULL (conversation_id)",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_ai_runs_owner"),
        sa.UniqueConstraint("user_id", "submission_id", name="uq_ai_runs_submission"),
    )
    op.create_index("ix_ai_runs_owner", "ai_runs", ["user_id", "created_at", "id"], unique=False)
    op.create_index(
        "uq_ai_runs_active",
        "ai_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where="status IN ('queued', 'running', 'interrupted')",
    )
    op.create_table(
        "ai_provider_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=11), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(status = 'started' AND finished_at IS NULL) OR (status != 'started' "
            "AND finished_at IS NOT NULL AND finished_at >= started_at)",
            name="ck_ai_attempts_time",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR (status IN ('failed', 'interrupted') AND error_code IN "
            "('unavailable', 'invalid_response', 'timeout', 'cancelled', 'interrupted'))",
            name="ck_ai_attempts_error",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'interrupted')",
            name="ck_ai_attempts_status",
        ),
        sa.CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0)",
            name="ck_ai_attempts_usage",
        ),
        sa.CheckConstraint("number BETWEEN 1 AND 4", name="ck_ai_attempts_number"),
        sa.ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            name="fk_ai_attempts_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "number", name="uq_ai_attempts_number"),
    )
    op.create_table(
        "ai_tool_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=11), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(status = 'started' AND finished_at IS NULL) OR (status != 'started' "
            "AND finished_at IS NOT NULL AND finished_at >= started_at)",
            name="ck_ai_tools_time",
        ),
        sa.CheckConstraint(
            "call_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$' AND "
            "tool_name ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$'",
            name="ck_ai_tools_labels",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR (status IN ('failed', 'interrupted') AND error_code IN "
            "('unavailable', 'invalid_response', 'timeout', 'cancelled', 'interrupted'))",
            name="ck_ai_tools_error",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'interrupted', 'rejected')",
            name="ck_ai_tools_status",
        ),
        sa.CheckConstraint("number BETWEEN 1 AND 8", name="ck_ai_tools_number"),
        sa.ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            name="fk_ai_tools_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "call_id", name="uq_ai_tools_call"),
        sa.UniqueConstraint("run_id", "number", name="uq_ai_tools_number"),
    )
    op.create_table(
        "checkpoint_migrations",
        sa.Column("v", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("v"),
    )
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["ai_conversations.checkpoint_thread_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"], unique=False)
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["ai_conversations.checkpoint_thread_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "channel", "version"),
    )
    op.create_index(
        "checkpoint_blobs_thread_id_idx", "checkpoint_blobs", ["thread_id"], unique=False
    )
    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), server_default="", nullable=False),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column("task_path", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["ai_conversations.checkpoint_thread_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),
    )
    op.create_index(
        "checkpoint_writes_thread_id_idx", "checkpoint_writes", ["thread_id"], unique=False
    )
    op.execute("INSERT INTO checkpoint_migrations (v) SELECT generate_series(0, 9)")


def downgrade() -> None:
    op.execute("""
        LOCK TABLE ai_conversations, ai_messages, ai_runs, ai_provider_attempts,
            ai_tool_executions, checkpoints, checkpoint_blobs, checkpoint_writes
            IN ACCESS EXCLUSIVE MODE;
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM ai_conversations)
               OR EXISTS (SELECT 1 FROM ai_messages)
               OR EXISTS (SELECT 1 FROM ai_runs)
               OR EXISTS (SELECT 1 FROM ai_provider_attempts)
               OR EXISTS (SELECT 1 FROM ai_tool_executions)
               OR EXISTS (SELECT 1 FROM checkpoints)
               OR EXISTS (SELECT 1 FROM checkpoint_blobs)
               OR EXISTS (SELECT 1 FROM checkpoint_writes) THEN
                RAISE EXCEPTION 'Cannot downgrade while AI content or execution records remain.';
            END IF;
        END $$;
    """)
    op.drop_table("checkpoint_writes")
    op.drop_table("checkpoint_blobs")
    op.drop_table("checkpoints")
    op.drop_table("checkpoint_migrations")
    op.drop_table("ai_tool_executions")
    op.drop_table("ai_provider_attempts")
    op.drop_table("ai_runs")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
