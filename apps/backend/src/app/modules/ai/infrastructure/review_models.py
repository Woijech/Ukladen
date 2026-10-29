from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
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
        CheckConstraint("version > 0", name="ck_ai_review_settings_version"),
        CheckConstraint(
            "jsonb_typeof(configuration) = 'object' AND jsonb_typeof(state) = 'object'",
            name="ck_ai_review_settings_json",
        ),
    )
