"""Add typed database properties and page-backed records without copying pages."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0015_database_content"
down_revision = "0014_user_databases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_database_properties",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("database_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("options", JSONB(), nullable=False, server_default="[]"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("trashed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["database_id", "user_id"],
            ["workspace_databases.id", "workspace_databases.user_id"],
            ondelete="CASCADE",
            name="fk_database_properties_owner",
        ),
        sa.UniqueConstraint(
            "id", "database_id", "user_id", name="uq_database_properties_id_database_user"
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_database_properties_name",
        ),
        sa.CheckConstraint(
            "kind IN ('text', 'number', 'checkbox', 'select', 'multi_select', 'url', 'date')",
            name="ck_database_properties_kind",
        ),
        sa.CheckConstraint(
            "version > 0 AND position BETWEEN 0 AND 100000",
            name="ck_database_properties_position_version",
        ),
        sa.CheckConstraint(
            "CASE WHEN jsonb_typeof(options) = 'array' THEN "
            "jsonb_array_length(options) <= 100 ELSE false END",
            name="ck_database_properties_options",
        ),
    )
    op.create_index(
        "ix_database_properties_database",
        "workspace_database_properties",
        ["database_id", "position", "id"],
    )
    op.create_table(
        "workspace_database_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("database_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("values", JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("trashed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["database_id", "user_id"],
            ["workspace_databases.id", "workspace_databases.user_id"],
            ondelete="CASCADE",
            name="fk_database_records_owner",
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_database_records_page_owner",
        ),
        sa.UniqueConstraint("database_id", "page_id", name="uq_database_records_database_page"),
        sa.UniqueConstraint(
            "id", "database_id", "user_id", name="uq_database_records_id_database_user"
        ),
        sa.CheckConstraint("version > 0", name="ck_database_records_version"),
        sa.CheckConstraint(
            'jsonb_typeof("values") = \'object\' AND octet_length("values"::text) <= 131072',
            name="ck_database_records_values",
        ),
    )
    op.create_index(
        "ix_database_records_database",
        "workspace_database_records",
        ["database_id", "trashed_at", "created_at", "id"],
    )
    op.create_index(
        "ix_database_records_page",
        "workspace_database_records",
        ["user_id", "page_id", "created_at", "id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workspace_database_records) "
            "OR EXISTS (SELECT 1 FROM workspace_database_properties)"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade while database properties or records exist; "
            "retained values must be preserved."
        )
    op.drop_table("workspace_database_records")
    op.drop_table("workspace_database_properties")
