"""Link pages to authorized personal and historical official events."""

import sqlalchemy as sa

from alembic import op

revision = "0009_page_calendar_links"
down_revision = "0008_note_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_personal_calendar_events_id_user", "personal_calendar_events", ["id", "user_id"]
    )
    op.create_table(
        "page_calendar_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("personal_event_id", sa.Uuid()),
        sa.Column("official_event_id", sa.Uuid(), sa.ForeignKey("official_schedule_events.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_page_calendar_links_page_owner",
        ),
        sa.ForeignKeyConstraint(
            ["personal_event_id", "user_id"],
            ["personal_calendar_events.id", "personal_calendar_events.user_id"],
            ondelete="CASCADE",
            name="fk_page_calendar_links_event_owner",
        ),
        sa.CheckConstraint(
            "(personal_event_id IS NULL) != (official_event_id IS NULL)",
            name="ck_page_calendar_links_target",
        ),
        sa.UniqueConstraint("page_id", "personal_event_id", name="uq_page_calendar_links_personal"),
        sa.UniqueConstraint("page_id", "official_event_id", name="uq_page_calendar_links_official"),
    )
    for kind, columns in (
        ("page", ["user_id", "page_id", "created_at", "id"]),
        ("personal", ["user_id", "personal_event_id", "created_at", "id"]),
        ("official", ["user_id", "official_event_id", "created_at", "id"]),
    ):
        op.create_index(f"ix_page_calendar_links_user_{kind}", "page_calendar_links", columns)


def downgrade() -> None:
    op.drop_table("page_calendar_links")
    op.drop_constraint(
        "uq_personal_calendar_events_id_user", "personal_calendar_events", type_="unique"
    )
