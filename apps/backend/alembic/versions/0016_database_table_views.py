"""Persist bounded saved table queries over page-backed records."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0016_database_table_views"
down_revision = "0015_database_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_database_views",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("database_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7)),
        sa.Column("layout", sa.String(16), server_default="table", nullable=False),
        sa.Column("query", JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["database_id", "user_id"],
            ["workspace_databases.id", "workspace_databases.user_id"],
            ondelete="CASCADE",
            name="fk_database_views_owner",
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_database_views_name",
        ),
        sa.CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name="ck_database_views_color"
        ),
        sa.CheckConstraint("layout = 'table'", name="ck_database_views_layout"),
        sa.CheckConstraint("version > 0", name="ck_database_views_version"),
        sa.CheckConstraint(
            "jsonb_typeof(query) = 'object' AND octet_length(query::text) <= 65536 "
            "AND COALESCE(query -> 'version' = '1'::jsonb "
            "AND query ->> 'version' = '1', false)",
            name="ck_database_views_query",
        ),
    )
    op.create_index(
        "ix_database_views_database",
        "workspace_database_views",
        ["database_id", "created_at", "id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM workspace_database_views)")):
        raise RuntimeError(
            "Cannot downgrade while database views exist; their settings must be preserved."
        )
    op.drop_table("workspace_database_views")
