"""Add recoverable user-owned databases, preserving existing pages."""

import sqlalchemy as sa

from alembic import op

revision = "0014_user_databases"
down_revision = "0013_saved_calendar_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_databases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("trashed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("id", "user_id", name="uq_workspace_databases_id_user"),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_workspace_databases_name",
        ),
        sa.CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name="ck_workspace_databases_color"
        ),
        sa.CheckConstraint(
            "version > 0 AND schema_version > 0", name="ck_workspace_databases_versions"
        ),
    )
    op.create_index(
        "ix_workspace_databases_user",
        "workspace_databases",
        ["user_id", "trashed_at", "created_at", "id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM workspace_databases)")):
        raise RuntimeError(
            "Cannot downgrade while user databases exist; their metadata must be preserved."
        )
    op.drop_table("workspace_databases")
