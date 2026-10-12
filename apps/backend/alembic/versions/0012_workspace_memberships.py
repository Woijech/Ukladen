"""Assign owned pages and authorized calendar events to collections and tags."""

import sqlalchemy as sa

from alembic import op

revision = "0012_workspace_memberships"
down_revision = "0011_workspace_organizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid()),
        sa.Column("personal_event_id", sa.Uuid()),
        sa.Column("official_event_id", sa.Uuid(), sa.ForeignKey("official_schedule_events.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["workspace_organizations.id", "workspace_organizations.user_id"],
            ondelete="CASCADE",
            name="fk_workspace_memberships_organization_owner",
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_workspace_memberships_page_owner",
        ),
        sa.ForeignKeyConstraint(
            ["personal_event_id", "user_id"],
            ["personal_calendar_events.id", "personal_calendar_events.user_id"],
            ondelete="CASCADE",
            name="fk_workspace_memberships_personal_owner",
        ),
        sa.CheckConstraint(
            "(CASE WHEN page_id IS NULL THEN 0 ELSE 1 END) + "
            "(CASE WHEN personal_event_id IS NULL THEN 0 ELSE 1 END) + "
            "(CASE WHEN official_event_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_workspace_memberships_one_target",
        ),
        sa.UniqueConstraint("organization_id", "page_id", name="uq_workspace_memberships_page"),
        sa.UniqueConstraint(
            "organization_id", "personal_event_id", name="uq_workspace_memberships_personal"
        ),
        sa.UniqueConstraint(
            "organization_id", "official_event_id", name="uq_workspace_memberships_official"
        ),
    )
    op.create_index(
        "ix_workspace_memberships_organization",
        "workspace_memberships",
        ["organization_id", "created_at", "id"],
    )
    for target in ("page", "personal", "official"):
        column = "page_id" if target == "page" else f"{target}_event_id"
        op.create_index(
            f"ix_workspace_memberships_{target}",
            "workspace_memberships",
            ["user_id", column, "organization_id"],
        )


def downgrade() -> None:
    op.drop_table("workspace_memberships")
