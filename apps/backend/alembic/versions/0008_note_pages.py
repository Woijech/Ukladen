"""Add independent, nested pages with recoverable branch trash."""

import sqlalchemy as sa

from alembic import op

revision = "0008_note_pages"
down_revision = "0007_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("parent_id", sa.Uuid()),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("trashed_at", sa.DateTime(timezone=True)),
        sa.Column("trash_batch_id", sa.Uuid()),
        sa.UniqueConstraint("id", "user_id", name="uq_note_pages_id_user"),
        sa.ForeignKeyConstraint(
            ["parent_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            name="fk_note_pages_parent_owner",
        ),
        sa.CheckConstraint("parent_id IS NULL OR parent_id != id", name="ck_note_pages_parent"),
        sa.CheckConstraint("version > 0", name="ck_note_pages_version"),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 200 AND title = btrim(title)",
            name="ck_note_pages_title",
        ),
        sa.CheckConstraint("char_length(content) <= 100000", name="ck_note_pages_content"),
        sa.CheckConstraint(
            "(trashed_at IS NULL) = (trash_batch_id IS NULL)", name="ck_note_pages_trash"
        ),
    )
    op.create_index("ix_note_pages_user_parent", "note_pages", ["user_id", "parent_id"])
    op.create_index(
        "ix_note_pages_user_trash", "note_pages", ["user_id", "trashed_at", "created_at", "id"]
    )


def downgrade() -> None:
    op.drop_table("note_pages")
