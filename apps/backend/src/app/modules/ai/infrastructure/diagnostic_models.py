from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DiagnosticChatModel(Base):
    __tablename__ = "ai_diagnostic_chats"
    conversation_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_diagnostic_chat_owner",
        ),
    )


class DiagnosticRunModel(Base):
    __tablename__ = "ai_diagnostic_runs"
    run_id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID]
    user_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    events: Mapped[list[dict]] = mapped_column(JSONB)
    truncated: Mapped[bool]
    verdict: Mapped[str] = mapped_column(String(10), default="unreviewed")
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_diagnostic_capture_chat",
        ),
        ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            ondelete="CASCADE",
            name="fk_ai_diagnostic_run_owner",
        ),
        CheckConstraint(
            "verdict IN ('unreviewed', 'passed', 'failed')", name="ck_ai_diagnostic_verdict"
        ),
        CheckConstraint("octet_length(note) <= 8000", name="ck_ai_diagnostic_note"),
        CheckConstraint(
            "jsonb_typeof(events) = 'array' AND jsonb_array_length(events) <= 64 "
            "AND octet_length(events::text) <= 262144",
            name="ck_ai_diagnostic_events",
        ),
    )
