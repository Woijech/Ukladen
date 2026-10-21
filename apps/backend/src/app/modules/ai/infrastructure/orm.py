from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ConversationModel(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_user_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sequence: Mapped[int] = mapped_column(BigInteger)
    checkpoint_thread_id: Mapped[str] = mapped_column(Text, Computed("id::text", persisted=True))

    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_ai_conversations_owner"),
        UniqueConstraint("checkpoint_thread_id", name="uq_ai_conversations_thread"),
        CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 200 AND title = btrim(title)",
            name="ck_ai_conversations_title",
        ),
        CheckConstraint("next_sequence > 0", name="ck_ai_conversations_sequence"),
        CheckConstraint(
            "last_user_message_at IS NULL OR last_user_message_at >= created_at",
            name="ck_ai_conversations_activity",
        ),
        Index("ix_ai_conversations_owner", "user_id", "created_at", "id"),
    )


class MessageModel(Base):
    __tablename__ = "ai_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    conversation_id: Mapped[UUID]
    sequence: Mapped[int] = mapped_column(BigInteger)
    role: Mapped[str] = mapped_column(String(9))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_messages_owner",
        ),
        UniqueConstraint("conversation_id", "sequence", name="uq_ai_messages_sequence"),
        CheckConstraint("sequence > 0", name="ck_ai_messages_sequence"),
        CheckConstraint("role IN ('user', 'assistant', 'tool')", name="ck_ai_messages_role"),
        CheckConstraint("octet_length(content) BETWEEN 1 AND 16384", name="ck_ai_messages_content"),
    )


class RunModel(Base):
    __tablename__ = "ai_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[UUID | None]
    submission_id: Mapped[UUID]
    request_digest: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(11))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int]

    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="SET NULL (conversation_id)",
            name="fk_ai_runs_owner",
        ),
        UniqueConstraint("id", "user_id", name="uq_ai_runs_owner"),
        UniqueConstraint("user_id", "submission_id", name="uq_ai_runs_submission"),
        CheckConstraint("version > 0", name="ck_ai_runs_version"),
        CheckConstraint("request_digest ~ '^[0-9a-f]{64}$'", name="ck_ai_runs_digest"),
        CheckConstraint(
            "provider ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$' AND "
            "model ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$'",
            name="ck_ai_runs_labels",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')",
            name="ck_ai_runs_status",
        ),
        CheckConstraint(
            "updated_at >= created_at AND "
            "((status IN ('completed', 'failed', 'cancelled') AND "
            "finished_at IS NOT NULL AND finished_at = updated_at) OR "
            "(status IN ('queued', 'running', 'interrupted') AND finished_at IS NULL))",
            name="ck_ai_runs_time",
        ),
        Index(
            "uq_ai_runs_active",
            "conversation_id",
            unique=True,
            postgresql_where="status IN ('queued', 'running', 'interrupted')",
        ),
        Index("ix_ai_runs_owner", "user_id", "created_at", "id"),
    )


class ProviderAttemptModel(Base):
    __tablename__ = "ai_provider_attempts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    run_id: Mapped[UUID]
    number: Mapped[int]
    status: Mapped[str] = mapped_column(String(11))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            ondelete="CASCADE",
            name="fk_ai_attempts_owner",
        ),
        UniqueConstraint("run_id", "number", name="uq_ai_attempts_number"),
        CheckConstraint("number BETWEEN 1 AND 4", name="ck_ai_attempts_number"),
        CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'interrupted')",
            name="ck_ai_attempts_status",
        ),
        CheckConstraint(
            "(status = 'started' AND finished_at IS NULL) OR "
            "(status != 'started' AND finished_at IS NOT NULL AND finished_at >= started_at)",
            name="ck_ai_attempts_time",
        ),
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0)",
            name="ck_ai_attempts_usage",
        ),
        CheckConstraint(
            "error_code IS NULL OR (status IN ('failed', 'interrupted') AND "
            "error_code IN ('unavailable', 'invalid_response', 'timeout', 'cancelled', "
            "'interrupted'))",
            name="ck_ai_attempts_error",
        ),
    )


class ToolExecutionModel(Base):
    __tablename__ = "ai_tool_executions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    run_id: Mapped[UUID]
    number: Mapped[int]
    call_id: Mapped[str] = mapped_column(String(128))
    tool_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(11))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            ondelete="CASCADE",
            name="fk_ai_tools_owner",
        ),
        UniqueConstraint("run_id", "number", name="uq_ai_tools_number"),
        UniqueConstraint("run_id", "call_id", name="uq_ai_tools_call"),
        CheckConstraint("number BETWEEN 1 AND 8", name="ck_ai_tools_number"),
        CheckConstraint(
            "call_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$' AND "
            "tool_name ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$'",
            name="ck_ai_tools_labels",
        ),
        CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'interrupted', 'rejected')",
            name="ck_ai_tools_status",
        ),
        CheckConstraint(
            "(status = 'started' AND finished_at IS NULL) OR "
            "(status != 'started' AND finished_at IS NOT NULL AND finished_at >= started_at)",
            name="ck_ai_tools_time",
        ),
        CheckConstraint(
            "error_code IS NULL OR (status IN ('failed', 'interrupted') AND "
            "error_code IN ('unavailable', 'invalid_response', 'timeout', 'cancelled', "
            "'interrupted'))",
            name="ck_ai_tools_error",
        ),
    )
