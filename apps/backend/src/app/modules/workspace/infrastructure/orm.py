from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OrganizationModel(Base):
    __tablename__ = "workspace_organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(7))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_workspace_organizations_id_user"),
        CheckConstraint("kind IN ('collection', 'tag')", name="ck_workspace_organizations_kind"),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_workspace_organizations_name",
        ),
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name="ck_workspace_organizations_color"
        ),
        CheckConstraint("version > 0", name="ck_workspace_organizations_version"),
        Index("ix_workspace_organizations_user_kind", "user_id", "kind", "created_at", "id"),
    )
