from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.modules.search.infrastructure.vector import Vector


class IndexGenerationModel(Base):
    __tablename__ = "search_index_generations"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    profile: Mapped[dict] = mapped_column(JSONB)


class IndexSourceModel(Base):
    __tablename__ = "search_index_sources"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    generation: Mapped[str] = mapped_column(
        ForeignKey("search_index_generations.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int]
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    attempts: Mapped[int] = mapped_column(server_default="0")
    lease: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("source IN ('page','material')", name="ck_search_index_source"),
        CheckConstraint(
            "status IN ('pending','processing','ready','failed')", name="ck_search_index_status"
        ),
        CheckConstraint("version > 0 AND attempts >= 0", name="ck_search_index_version"),
        Index("ix_search_index_dispatch", "generation", "status", "lease_until"),
    )


class SearchChunkModel(Base):
    __tablename__ = "search_chunks"
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    generation: Mapped[str] = mapped_column(Text, primary_key=True)
    number: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int]
    start: Mapped[int]
    end: Mapped[int]
    body: Mapped[str] = mapped_column(Text)
    locator: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(Text)
    embedding: Mapped[tuple[float, ...]] = mapped_column(Vector())
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "source", "source_id", "generation"],
            [
                "search_index_sources.user_id",
                "search_index_sources.source",
                "search_index_sources.source_id",
                "search_index_sources.generation",
            ],
            ondelete="CASCADE",
            name="fk_search_chunk_source",
        ),
        CheckConstraint(
            '"start" >= 0 AND "end" > "start" AND version > 0 AND number >= 0',
            name="ck_search_chunk_range",
        ),
    )
