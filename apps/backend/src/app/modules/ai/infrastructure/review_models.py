from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ReviewSettingsModel(Base):
    __tablename__ = "ai_review_settings"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int]
    configuration: Mapped[dict] = mapped_column(JSONB)
    offering_version: Mapped[int | None]
    next_scan_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    __table_args__ = (
        Index(
            "ix_ai_review_settings_due",
            "next_scan_at",
            "user_id",
            postgresql_where=text("(configuration ->> 'enabled')::boolean"),
        ),
        CheckConstraint("version > 0", name="ck_ai_review_settings_version"),
        CheckConstraint(
            "jsonb_typeof(configuration) = 'object' AND jsonb_typeof(state) = 'object'",
            name="ck_ai_review_settings_json",
        ),
    )


class ReviewModel(Base):
    __tablename__ = "ai_reviews"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[UUID]
    configuration_version: Mapped[int]
    kind: Mapped[str] = mapped_column(String(8))
    slot: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    snapshot: Mapped[str] = mapped_column(String(64))
    configuration: Mapped[dict] = mapped_column(JSONB)
    issue_state: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Historical receipt; normal AI run retention is independent of review content.
    run_id: Mapped[UUID | None]
    discussed: Mapped[bool] = mapped_column(default=False, server_default="false")
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_ai_reviews_owner"),
        UniqueConstraint("conversation_id", name="uq_ai_reviews_conversation"),
        UniqueConstraint(
            "user_id", "configuration_version", "kind", "slot", name="uq_ai_reviews_slot"
        ),
        ForeignKeyConstraint(
            ["conversation_id", "user_id"],
            ["ai_conversations.id", "ai_conversations.user_id"],
            ondelete="CASCADE",
            name="fk_ai_reviews_conversation_owner",
        ),
        CheckConstraint("kind IN ('daily', 'weekly', 'warnings')", name="ck_ai_reviews_kind"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_ai_reviews_status",
        ),
        CheckConstraint(
            "configuration_version > 0 AND expires_at > created_at", name="ck_ai_reviews_lifetime"
        ),
        CheckConstraint(
            "jsonb_typeof(issue_state) = 'array' AND jsonb_typeof(configuration) = 'object'",
            name="ck_ai_reviews_issues",
        ),
        Index("ix_ai_reviews_pending", "status", "created_at"),
    )
