from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class MembershipModel(Base):
    __tablename__ = "workspace_memberships"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    organization_id: Mapped[UUID] = mapped_column()
    page_id: Mapped[UUID | None] = mapped_column()
    personal_event_id: Mapped[UUID | None] = mapped_column()
    official_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("official_schedule_events.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["workspace_organizations.id", "workspace_organizations.user_id"],
            ondelete="CASCADE",
            name="fk_workspace_memberships_organization_owner",
        ),
        ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_workspace_memberships_page_owner",
        ),
        ForeignKeyConstraint(
            ["personal_event_id", "user_id"],
            ["personal_calendar_events.id", "personal_calendar_events.user_id"],
            ondelete="CASCADE",
            name="fk_workspace_memberships_personal_owner",
        ),
        CheckConstraint(
            "(CASE WHEN page_id IS NULL THEN 0 ELSE 1 END) + "
            "(CASE WHEN personal_event_id IS NULL THEN 0 ELSE 1 END) + "
            "(CASE WHEN official_event_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_workspace_memberships_one_target",
        ),
        UniqueConstraint("organization_id", "page_id", name="uq_workspace_memberships_page"),
        UniqueConstraint(
            "organization_id", "personal_event_id", name="uq_workspace_memberships_personal"
        ),
        UniqueConstraint(
            "organization_id", "official_event_id", name="uq_workspace_memberships_official"
        ),
        Index("ix_workspace_memberships_organization", "organization_id", "created_at", "id"),
        Index("ix_workspace_memberships_page", "user_id", "page_id", "organization_id"),
        Index(
            "ix_workspace_memberships_personal", "user_id", "personal_event_id", "organization_id"
        ),
        Index(
            "ix_workspace_memberships_official", "user_id", "official_event_id", "organization_id"
        ),
    )


class CalendarViewModel(Base):
    __tablename__ = "workspace_calendar_views"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(7))
    sources: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    layout: Mapped[str] = mapped_column(String(8), server_default="week")
    sort_order: Mapped[str] = mapped_column(String(4), server_default="asc")
    include_hidden: Mapped[bool] = mapped_column(Boolean, server_default="false")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_workspace_calendar_views_name",
        ),
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name="ck_workspace_calendar_views_color"
        ),
        CheckConstraint("version > 0", name="ck_workspace_calendar_views_version"),
        CheckConstraint(
            "layout IN ('day', 'week', 'month')", name="ck_workspace_calendar_views_layout"
        ),
        CheckConstraint("sort_order IN ('asc', 'desc')", name="ck_workspace_calendar_views_sort"),
        CheckConstraint(
            "CASE WHEN jsonb_typeof(sources) = 'array' THEN "
            "jsonb_array_length(sources) BETWEEN 1 AND 2 ELSE false END",
            name="ck_workspace_calendar_views_sources",
        ),
        Index("ix_workspace_calendar_views_user", "user_id", "created_at", "id"),
    )


class DatabaseModel(Base):
    __tablename__ = "workspace_databases"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(7))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    schema_version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_workspace_databases_id_user"),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_workspace_databases_name",
        ),
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name="ck_workspace_databases_color"
        ),
        CheckConstraint(
            "version > 0 AND schema_version > 0", name="ck_workspace_databases_versions"
        ),
        Index("ix_workspace_databases_user", "user_id", "trashed_at", "created_at", "id"),
    )


class DatabasePropertyModel(Base):
    __tablename__ = "workspace_database_properties"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    database_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16))
    options: Mapped[list[dict[str, str]]] = mapped_column(JSONB, server_default="[]")
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["database_id", "user_id"],
            ["workspace_databases.id", "workspace_databases.user_id"],
            ondelete="CASCADE",
            name="fk_database_properties_owner",
        ),
        UniqueConstraint(
            "id", "database_id", "user_id", name="uq_database_properties_id_database_user"
        ),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_database_properties_name",
        ),
        CheckConstraint(
            "kind IN ('text', 'number', 'checkbox', 'select', 'multi_select', 'url', 'date')",
            name="ck_database_properties_kind",
        ),
        CheckConstraint(
            "version > 0 AND position BETWEEN 0 AND 100000",
            name="ck_database_properties_position_version",
        ),
        CheckConstraint(
            "CASE WHEN jsonb_typeof(options) = 'array' THEN "
            "jsonb_array_length(options) <= 100 ELSE false END",
            name="ck_database_properties_options",
        ),
        Index("ix_database_properties_database", "database_id", "position", "id"),
    )


class DatabaseRecordModel(Base):
    __tablename__ = "workspace_database_records"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    database_id: Mapped[UUID] = mapped_column()
    page_id: Mapped[UUID] = mapped_column()
    values: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["database_id", "user_id"],
            ["workspace_databases.id", "workspace_databases.user_id"],
            ondelete="CASCADE",
            name="fk_database_records_owner",
        ),
        ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_database_records_page_owner",
        ),
        UniqueConstraint("database_id", "page_id", name="uq_database_records_database_page"),
        UniqueConstraint(
            "id", "database_id", "user_id", name="uq_database_records_id_database_user"
        ),
        CheckConstraint("version > 0", name="ck_database_records_version"),
        CheckConstraint(
            'jsonb_typeof("values") = \'object\' AND octet_length("values"::text) <= 131072',
            name="ck_database_records_values",
        ),
        Index("ix_database_records_database", "database_id", "trashed_at", "created_at", "id"),
        Index("ix_database_records_page", "user_id", "page_id", "created_at", "id"),
    )


class DatabaseViewModel(Base):
    __tablename__ = "workspace_database_views"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    database_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(7))
    layout: Mapped[str] = mapped_column(String(16), server_default="table")
    query: Mapped[dict[str, object]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(
            ["database_id", "user_id"],
            ["workspace_databases.id", "workspace_databases.user_id"],
            ondelete="CASCADE",
            name="fk_database_views_owner",
        ),
        CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_database_views_name",
        ),
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name="ck_database_views_color"
        ),
        CheckConstraint("layout = 'table'", name="ck_database_views_layout"),
        CheckConstraint("version > 0", name="ck_database_views_version"),
        CheckConstraint(
            "jsonb_typeof(query) = 'object' AND octet_length(query::text) <= 65536 "
            "AND COALESCE(query -> 'version' = '1'::jsonb "
            "AND query ->> 'version' = '1', false)",
            name="ck_database_views_query",
        ),
        Index("ix_database_views_database", "database_id", "created_at", "id"),
    )
