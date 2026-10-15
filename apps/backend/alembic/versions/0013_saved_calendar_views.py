"""Store owner-scoped saved calendar filters without copying events."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0013_saved_calendar_views"
down_revision = "0012_workspace_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_calendar_views",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7)),
        sa.Column("sources", JSONB(), nullable=False),
        sa.Column("layout", sa.String(8), server_default="week", nullable=False),
        sa.Column("sort_order", sa.String(4), server_default="asc", nullable=False),
        sa.Column("include_hidden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_workspace_calendar_views_name",
        ),
        sa.CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name="ck_workspace_calendar_views_color"
        ),
        sa.CheckConstraint("version > 0", name="ck_workspace_calendar_views_version"),
        sa.CheckConstraint(
            "layout IN ('day', 'week', 'month')", name="ck_workspace_calendar_views_layout"
        ),
        sa.CheckConstraint(
            "sort_order IN ('asc', 'desc')", name="ck_workspace_calendar_views_sort"
        ),
        sa.CheckConstraint(
            "CASE WHEN jsonb_typeof(sources) = 'array' THEN "
            "jsonb_array_length(sources) BETWEEN 1 AND 2 ELSE false END",
            name="ck_workspace_calendar_views_sources",
        ),
    )
    op.create_index(
        "ix_workspace_calendar_views_user",
        "workspace_calendar_views",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("workspace_calendar_views")
