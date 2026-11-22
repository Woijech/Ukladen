"""Preserve bounded owned page revisions, including existing page baselines."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0045_page_revisions"
down_revision = "0044_ai_partial_answers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_page_revisions",
        sa.Column("page_id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            ondelete="CASCADE",
            name="fk_page_revision_owner",
        ),
        sa.CheckConstraint("version > 0", name="ck_page_revision_version"),
        sa.CheckConstraint("octet_length(document::text) <= 1048576", name="ck_page_revision_size"),
    )
    op.execute(
        "INSERT INTO note_page_revisions (page_id, user_id, version, title, document, saved_at) "
        "SELECT id, user_id, version, title, document, updated_at FROM note_pages"
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM note_page_revisions r "
            "JOIN note_pages p ON p.id=r.page_id WHERE r.version != p.version)"
        )
    ):
        raise RuntimeError("Retained revision history prevents downgrade")
    op.drop_table("note_page_revisions")
