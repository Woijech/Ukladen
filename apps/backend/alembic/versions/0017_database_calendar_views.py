"""Bind calendar views to owned database date properties."""

import sqlalchemy as sa

from alembic import op

revision = "0017_database_calendar_views"
down_revision = "0016_database_table_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspace_database_views", sa.Column("date_property_id", sa.Uuid()))
    op.add_column("workspace_database_views", sa.Column("calendar_layout", sa.String(8)))
    op.create_foreign_key(
        "fk_database_views_date_property",
        "workspace_database_views",
        "workspace_database_properties",
        ["date_property_id", "database_id", "user_id"],
        ["id", "database_id", "user_id"],
    )
    op.drop_constraint("ck_database_views_layout", "workspace_database_views", type_="check")
    op.create_check_constraint(
        "ck_database_views_layout",
        "workspace_database_views",
        "(layout = 'table' AND date_property_id IS NULL AND calendar_layout IS NULL) OR "
        "(layout = 'calendar' AND date_property_id IS NOT NULL AND "
        "calendar_layout IS NOT NULL AND calendar_layout IN ('day', 'week', 'month'))",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM workspace_database_views WHERE layout = 'calendar')")
    ):
        raise RuntimeError(
            "Cannot downgrade while calendar database views exist; preserve their bindings."
        )
    op.drop_constraint(
        "fk_database_views_date_property", "workspace_database_views", type_="foreignkey"
    )
    op.drop_constraint("ck_database_views_layout", "workspace_database_views", type_="check")
    op.drop_column("workspace_database_views", "calendar_layout")
    op.drop_column("workspace_database_views", "date_property_id")
    op.create_check_constraint(
        "ck_database_views_layout", "workspace_database_views", "layout = 'table'"
    )
