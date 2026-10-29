from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ActionProposalModel(Base):
    __tablename__ = "ai_action_proposals"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    conversation_id: Mapped[UUID] = mapped_column()
    run_id: Mapped[UUID] = mapped_column()
    interrupt_id: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB)

    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_action_conversation",
        ),
        ForeignKeyConstraint(
            ["run_id", "user_id"],
            ["ai_runs.id", "ai_runs.user_id"],
            ondelete="CASCADE",
            name="fk_ai_action_run",
        ),
        UniqueConstraint("run_id", "interrupt_id", name="uq_ai_action_run_interrupt"),
        CheckConstraint(
            "expires_at = created_at + interval '24 hours'", name="ck_ai_action_expiry"
        ),
        CheckConstraint("digest ~ '^[a-f0-9]{64}$'", name="ck_ai_action_digest"),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 2097152",
            name="ck_ai_action_payload",
        ),
        Index("ix_ai_action_chat", "user_id", "conversation_id", "created_at", "id"),
    )


class ActionReceiptModel(Base):
    __tablename__ = "ai_action_receipts"

    proposal_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text)
    outcomes: Mapped[list] = mapped_column(JSONB)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('applied','rejected','expired','conflict','superseded')",
            name="ck_ai_action_receipt_status",
        ),
        CheckConstraint(
            "jsonb_typeof(outcomes) = 'array' AND jsonb_array_length(outcomes) <= 8",
            name="ck_ai_action_receipt_outcomes",
        ),
    )
