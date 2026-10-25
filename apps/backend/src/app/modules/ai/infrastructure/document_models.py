from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DocumentJobModel(Base):
    __tablename__ = "ai_document_jobs"
    run_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    conversation_id: Mapped[UUID]
    answer_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="SET NULL")
    )
    question: Mapped[str] = mapped_column(Text)
    selection: Mapped[dict] = mapped_column(JSONB)
    manifest: Mapped[list] = mapped_column(JSONB, server_default="[]")
    notes: Mapped[list] = mapped_column(JSONB, server_default="[]")
    source_index: Mapped[int] = mapped_column(server_default="0")
    offset: Mapped[int] = mapped_column(server_default="0")
    processed_characters: Mapped[int] = mapped_column(server_default="0")
    total_characters: Mapped[int] = mapped_column(server_default="0")
    phase: Mapped[str] = mapped_column(Text, server_default="reading")
    steps: Mapped[int] = mapped_column(server_default="0")
    failures: Mapped[int] = mapped_column(server_default="0")
    lease: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            ondelete="CASCADE",
            name="fk_ai_document_run",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_document_conversation",
        ),
        CheckConstraint(
            'source_index >= 0 AND "offset" >= 0 AND steps >= 0 AND failures >= 0 '
            "AND processed_characters >= 0 AND total_characters >= processed_characters",
            name="ck_ai_document_progress",
        ),
        CheckConstraint(
            "phase IN ('reading','combining','completed','failed')", name="ck_ai_document_phase"
        ),
    )
