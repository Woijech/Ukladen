"""Persist shared official schedules and synchronization leases."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_schedule_storage"
down_revision = "0006_personal_calendar_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_sources",
        sa.Column(
            "group_id", sa.BigInteger(), sa.ForeignKey("university_groups.id"), primary_key=True
        ),
        sa.Column("group_number", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.Text()),
        sa.Column("sync_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("snapshot", postgresql.JSONB()),
        sa.UniqueConstraint("group_number", name="uq_schedule_sources_group_number"),
        sa.CheckConstraint("char_length(group_number) > 0", name="ck_schedule_sources_number"),
        sa.CheckConstraint(
            "status IN ('syncing', 'ready', 'unpublished', 'error', 'unsupported')",
            name="ck_schedule_sources_status",
        ),
        sa.CheckConstraint(
            "(sync_token IS NULL) = (lease_until IS NULL)", name="ck_schedule_sources_lease"
        ),
    )
    op.create_table(
        "official_schedule_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "group_id", sa.BigInteger(), sa.ForeignKey("schedule_sources.group_id"), nullable=False
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("subgroup", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.Text()),
        sa.Column("subject_full_name", sa.Text()),
        sa.Column("lesson_type", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("rooms", postgresql.JSONB(), nullable=False),
        sa.Column("teacher_ids", postgresql.JSONB(), nullable=False),
        sa.Column("teacher_names", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_official_schedule_events_time"),
        sa.CheckConstraint("subgroup >= 0", name="ck_official_schedule_events_subgroup"),
        sa.CheckConstraint(
            "kind IN ('lesson', 'exam', 'announcement')", name="ck_official_schedule_events_kind"
        ),
    )
    op.create_index(
        "ix_official_schedule_events_group_time",
        "official_schedule_events",
        ["group_id", "starts_at"],
    )


def downgrade() -> None:
    op.drop_table("official_schedule_events")
    op.drop_table("schedule_sources")
