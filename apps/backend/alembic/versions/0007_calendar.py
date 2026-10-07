"""Add user-owned calendar events and official-event overrides."""

import sqlalchemy as sa

from alembic import op

revision = "0007_calendar"
down_revision = "0006_schedule_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_calendar_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(10000)),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(500)),
        sa.Column("blocks_time", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_personal_calendar_events_time"),
        sa.CheckConstraint("version > 0", name="ck_personal_calendar_events_version"),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200 AND title !~ '^[[:space:]]|[[:space:]]$'",
            name="ck_personal_calendar_events_title",
        ),
    )
    op.create_index(
        "ix_personal_calendar_events_user_time",
        "personal_calendar_events",
        ["user_id", "starts_at"],
    )
    op.create_table(
        "schedule_overrides",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "official_event_id",
            sa.Uuid(),
            sa.ForeignKey("official_schedule_events.id"),
            primary_key=True,
        ),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("title", sa.String(200)),
        sa.Column("description", sa.String(10000)),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("location", sa.String(500)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(starts_at IS NULL AND ends_at IS NULL) OR "
            "(starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at)",
            name="ck_schedule_overrides_time",
        ),
        sa.CheckConstraint("version > 0", name="ck_schedule_overrides_version"),
        sa.CheckConstraint(
            "title IS NULL OR (char_length(title) BETWEEN 1 AND 200 "
            "AND title !~ '^[[:space:]]|[[:space:]]$')",
            name="ck_schedule_overrides_title",
        ),
    )
    op.create_index(
        "ix_schedule_overrides_user_time", "schedule_overrides", ["user_id", "starts_at"]
    )


def downgrade() -> None:
    op.drop_table("schedule_overrides")
    op.drop_table("personal_calendar_events")
