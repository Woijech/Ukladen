"""Record atomic portable imports for retry-safe creation."""

import sqlalchemy as sa

from alembic import op

revision = "0049_workspace_transfer"
down_revision = "0048_nested_page_blocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_transfer_receipts",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("root_page_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["root_page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_transfer_receipt_page_owner",
        ),
        sa.CheckConstraint("digest ~ '^[a-f0-9]{64}$'", name="ck_transfer_receipt_digest"),
    )


def downgrade() -> None:
    op.drop_table("workspace_transfer_receipts")
