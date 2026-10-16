"""Add durable calendar reminders and an owner-scoped in-app inbox."""

import sqlalchemy as sa

from alembic import op

revision = "0018_reminders_notifications"
down_revision = "0017_database_calendar_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("personal_event_id", sa.Uuid()),
        sa.Column(
            "official_event_id",
            sa.Uuid(),
            sa.ForeignKey("official_schedule_events.id", ondelete="CASCADE"),
        ),
        sa.Column("minutes_before", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["personal_event_id", "user_id"],
            ["personal_calendar_events.id", "personal_calendar_events.user_id"],
            name="fk_reminders_personal_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "num_nonnulls(personal_event_id, official_event_id) = 1", name="ck_reminders_target"
        ),
        sa.CheckConstraint("minutes_before BETWEEN 0 AND 43200", name="ck_reminders_offset"),
        sa.CheckConstraint("version > 0", name="ck_reminders_version"),
        sa.CheckConstraint(
            "due_at = starts_at - minutes_before * interval '1 minute'",
            name="ck_reminders_trigger",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'delivered', 'cancelled')", name="ck_reminders_status"
        ),
    )
    op.create_index(
        "ix_reminders_due", "reminders", ["due_at", "id"], postgresql_where="status = 'pending'"
    )
    op.create_index("ix_reminders_owner", "reminders", ["user_id", "created_at", "id"])
    op.create_index("ix_reminders_personal", "reminders", ["personal_event_id"])
    op.create_index("ix_reminders_official", "reminders", ["official_event_id"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("reminder_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("reminder_id", name="uq_notifications_reminder"),
        sa.CheckConstraint("source IN ('personal', 'official')", name="ck_notifications_source"),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 500", name="ck_notifications_title"),
        sa.CheckConstraint(
            "read_at IS NULL OR read_at >= created_at", name="ck_notifications_read"
        ),
    )
    op.create_index("ix_notifications_owner", "notifications", ["user_id", "created_at", "id"])


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM reminders) OR EXISTS (SELECT 1 FROM notifications)")
    ):
        raise RuntimeError("Cannot downgrade while reminders or notifications must be preserved.")
    op.drop_table("notifications")
    op.drop_table("reminders")
