from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MaterialModel(Base):
    __tablename__ = "materials"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(4))
    filename: Mapped[str | None] = mapped_column(String(200))
    media_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(10))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer)
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_materials_id_owner"),
        CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 200 AND title = btrim(title)",
            name="ck_materials_title",
        ),
        CheckConstraint(
            "(kind = 'file' AND filename IS NOT NULL AND media_type IS NOT NULL "
            "AND size_bytes BETWEEN 1 AND 26214400 AND url IS NULL) OR "
            "(kind = 'link' AND filename IS NULL AND media_type IS NULL "
            "AND size_bytes = 0 AND url IS NOT NULL AND status = 'ready')",
            name="ck_materials_kind",
        ),
        CheckConstraint(
            "status IN ('uploading', 'pending', 'processing', 'ready', 'failed')",
            name="ck_materials_status",
        ),
        CheckConstraint("version > 0 AND attempts BETWEEN 0 AND 3", name="ck_materials_versions"),
        CheckConstraint(
            "(status = 'processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status != 'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="ck_materials_lease",
        ),
        CheckConstraint(
            "error_code IS NULL OR error_code IN ('invalid_document', 'document_limit', "
            "'storage_unavailable', 'processing_timeout', 'no_extractable_text')",
            name="ck_materials_error",
        ),
        Index("ix_materials_owner", "user_id", "trashed_at", "created_at", "id"),
        Index("ix_materials_work", "status", "updated_at", "id"),
        Index("ix_materials_trash", "trashed_at", "id"),
    )


class MaterialObjectModel(Base):
    """Durable object ledger survives user/material deletion until S3 cleanup succeeds."""

    __tablename__ = "material_objects"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID]
    material_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("materials.id", ondelete="SET NULL"), unique=True
    )
    storage_key: Mapped[str] = mapped_column(String(128), unique=True)

    __table_args__ = (
        CheckConstraint("material_id IS NULL OR material_id = id", name="ck_material_objects_id"),
        CheckConstraint(
            "storage_key = 'materials/' || user_id::text || '/' || id::text",
            name="ck_material_objects_key",
        ),
        Index("ix_material_objects_orphan", "material_id"),
    )
