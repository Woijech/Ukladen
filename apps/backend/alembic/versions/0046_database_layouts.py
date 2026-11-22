"""Add personal list/board views without copying records."""

import sqlalchemy as sa

from alembic import op

revision = "0046_database_layouts"
down_revision = "0045_page_revisions"
branch_labels = None
depends_on = None


def constraint(layouts: str) -> str:
    return (
        f"(layout IN ({layouts}) AND date_property_id IS NULL AND calendar_layout IS NULL "
        "AND (layout <> 'board' OR "
        "COALESCE(jsonb_typeof(query -> 'group_by') = 'string', false))) OR "
        "(layout = 'calendar' AND date_property_id IS NOT NULL AND "
        "calendar_layout IS NOT NULL AND calendar_layout IN ('day', 'week', 'month'))"
    )


def upgrade() -> None:
    op.drop_constraint("ck_database_views_layout", "workspace_database_views", type_="check")
    op.create_check_constraint(
        "ck_database_views_layout",
        "workspace_database_views",
        constraint("'table', 'list', 'board'"),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workspace_database_views "
            "WHERE layout IN ('list', 'board') OR query ? 'group_by')"
        )
    ):
        raise RuntimeError("Remove new layouts/grouping explicitly before downgrading.")
    op.drop_constraint("ck_database_views_layout", "workspace_database_views", type_="check")
    op.create_check_constraint(
        "ck_database_views_layout", "workspace_database_views", constraint("'table'")
    )
