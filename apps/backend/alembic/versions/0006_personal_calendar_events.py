"""Add user-owned personal calendar events."""

import sqlalchemy as sa

from alembic import op

revision = "0006_personal_calendar_events"
down_revision = "0005_academics_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_calendar_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_busy", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("title ~ '[^[:space:]]'", name="ck_personal_calendar_events_title"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_personal_calendar_events_interval"),
    )
    op.create_index(
        "ix_personal_calendar_events_user_start",
        "personal_calendar_events",
        ["user_id", "starts_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("personal_calendar_events")
