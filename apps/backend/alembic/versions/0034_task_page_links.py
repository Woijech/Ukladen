"""Add explicit task/page references without copying either endpoint."""

import sqlalchemy as sa

from alembic import op

revision = "0034_task_page_links"
down_revision = "0033_task_dependencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_page_links",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("task_id", "page_id"),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_task_page_links_task_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            name="fk_task_page_links_page_owner",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_task_page_links_reverse", "task_page_links", ["user_id", "page_id", "task_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE task_page_links IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM task_page_links)")):
        raise RuntimeError("Cannot downgrade populated task page links.")
    op.drop_table("task_page_links")
