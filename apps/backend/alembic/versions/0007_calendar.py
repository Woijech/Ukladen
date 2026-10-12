"""Extend existing personal events and add official-event overrides."""

import sqlalchemy as sa

from alembic import op

revision = "0007_calendar"
down_revision = "0006_schedule_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reject incompatible legacy data before narrowing columns; never truncate user content.
    op.execute(
        sa.text(
            "DO $migration$ BEGIN "
            "IF EXISTS (SELECT 1 FROM personal_calendar_events WHERE "
            "char_length(title) > 200 OR title ~ '^[[:space:]]|[[:space:]]$' "
            "OR char_length(description) > 10000) THEN "
            "RAISE EXCEPTION "
            "'Personal events need validation before the calendar schema upgrade.'; "
            "END IF; END $migration$;"
        )
    )
    op.drop_constraint("ck_personal_calendar_events_title", "personal_calendar_events")
    op.drop_constraint("ck_personal_calendar_events_interval", "personal_calendar_events")
    op.drop_index("ix_personal_calendar_events_user_start", table_name="personal_calendar_events")
    op.alter_column("personal_calendar_events", "title", type_=sa.String(200))
    op.alter_column("personal_calendar_events", "description", type_=sa.String(10000))
    op.alter_column("personal_calendar_events", "is_busy", new_column_name="blocks_time")
    op.add_column("personal_calendar_events", sa.Column("location", sa.String(500)))
    op.add_column(
        "personal_calendar_events",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_personal_calendar_events_time", "personal_calendar_events", "ends_at > starts_at"
    )
    op.create_check_constraint(
        "ck_personal_calendar_events_version", "personal_calendar_events", "version > 0"
    )
    op.create_check_constraint(
        "ck_personal_calendar_events_title",
        "personal_calendar_events",
        "char_length(title) BETWEEN 1 AND 200 AND title !~ '^[[:space:]]|[[:space:]]$'",
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
    for name in ("title", "time", "version"):
        op.drop_constraint(f"ck_personal_calendar_events_{name}", "personal_calendar_events")
    op.drop_index("ix_personal_calendar_events_user_time", table_name="personal_calendar_events")
    op.drop_column("personal_calendar_events", "location")
    op.drop_column("personal_calendar_events", "version")
    op.alter_column("personal_calendar_events", "blocks_time", new_column_name="is_busy")
    op.alter_column("personal_calendar_events", "title", type_=sa.Text())
    op.alter_column("personal_calendar_events", "description", type_=sa.Text())
    op.create_check_constraint(
        "ck_personal_calendar_events_title", "personal_calendar_events", "title ~ '[^[:space:]]'"
    )
    op.create_check_constraint(
        "ck_personal_calendar_events_interval", "personal_calendar_events", "ends_at > starts_at"
    )
    op.create_index(
        "ix_personal_calendar_events_user_start",
        "personal_calendar_events",
        ["user_id", "starts_at", "id"],
    )
