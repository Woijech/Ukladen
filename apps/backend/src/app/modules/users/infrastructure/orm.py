from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    display_name: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(), server_default="UTC")
    locale: Mapped[str] = mapped_column(String(2), server_default="ru")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("uq_users_email_ci", func.lower(email), unique=True),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
        CheckConstraint(
            "display_name IS NULL OR (char_length(display_name) BETWEEN 1 AND 100 "
            "AND display_name !~ '^[[:space:]]|[[:space:]]$')",
            name="ck_users_display_name",
        ),
        CheckConstraint("char_length(timezone) > 0", name="ck_users_timezone"),
        CheckConstraint("locale IN ('ru', 'en')", name="ck_users_locale"),
    )
