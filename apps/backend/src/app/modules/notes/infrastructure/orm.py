from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PageModel(Base):
    __tablename__ = "note_pages"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    parent_id: Mapped[UUID | None] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, server_default="")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trash_batch_id: Mapped[UUID | None] = mapped_column()

    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_note_pages_id_user"),
        ForeignKeyConstraint(
            ["parent_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            name="fk_note_pages_parent_owner",
        ),
        CheckConstraint("parent_id IS NULL OR parent_id != id", name="ck_note_pages_parent"),
        CheckConstraint("version > 0", name="ck_note_pages_version"),
        CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 200 AND title = btrim(title)",
            name="ck_note_pages_title",
        ),
        CheckConstraint("char_length(content) <= 100000", name="ck_note_pages_content"),
        CheckConstraint(
            "(trashed_at IS NULL) = (trash_batch_id IS NULL)", name="ck_note_pages_trash"
        ),
        Index("ix_note_pages_user_parent", "user_id", "parent_id"),
        Index("ix_note_pages_user_trash", "user_id", "trashed_at", "created_at", "id"),
    )
