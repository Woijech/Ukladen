"""Personal event calendars and independent display preferences."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0043_personal_calendars"
down_revision = "0042_minsk_timezone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_calendars",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "user_id", name="uq_personal_calendars_owner"),
        sa.CheckConstraint("version > 0", name="ck_personal_calendars_version"),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100", name="ck_personal_calendars_name"
        ),
        sa.CheckConstraint("color ~ '^#[0-9a-f]{6}$'", name="ck_personal_calendars_color"),
    )
    op.add_column("personal_calendar_events", sa.Column("calendar_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_event_personal_calendar",
        "personal_calendar_events",
        "personal_calendars",
        ["calendar_id", "user_id"],
        ["id", "user_id"],
    )
    op.create_index(
        "ix_personal_events_calendar", "personal_calendar_events", ["user_id", "calendar_id"]
    )
    op.create_table(
        "calendar_visibility",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("default_visible", sa.Boolean(), nullable=False),
        sa.Column("hidden_calendar_ids", postgresql.JSONB(), nullable=False),
        sa.Column("hidden_lesson_types", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_calendar_visibility_version"),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM personal_calendars) "
            "OR EXISTS (SELECT 1 FROM calendar_visibility)"
        )
    ):
        raise RuntimeError("Retained calendar data prevents downgrade")
    op.drop_table("calendar_visibility")
    op.drop_constraint("fk_event_personal_calendar", "personal_calendar_events", type_="foreignkey")
    op.drop_index("ix_personal_events_calendar", table_name="personal_calendar_events")
    op.drop_column("personal_calendar_events", "calendar_id")
    op.drop_table("personal_calendars")
