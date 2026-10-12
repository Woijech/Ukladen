"""Add personal collection and tag definitions without touching existing objects."""

import sqlalchemy as sa

from alembic import op

revision = "0011_workspace_organizations"
down_revision = "0010_page_block_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_workspace_organizations_id_user"),
        sa.CheckConstraint("kind IN ('collection', 'tag')", name="ck_workspace_organizations_kind"),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 100 AND name = btrim(name)",
            name="ck_workspace_organizations_name",
        ),
        sa.CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name="ck_workspace_organizations_color"
        ),
        sa.CheckConstraint("version > 0", name="ck_workspace_organizations_version"),
    )
    op.create_index(
        "ix_workspace_organizations_user_kind",
        "workspace_organizations",
        ["user_id", "kind", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("workspace_organizations")
