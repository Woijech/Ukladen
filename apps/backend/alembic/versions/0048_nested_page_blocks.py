"""Guard rollback after additive nested blocks and saved-view references."""

import sqlalchemy as sa

from alembic import op

revision = "0048_nested_page_blocks"
down_revision = "0047_database_calculations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The canonical JSON envelope is unchanged; parsing adds two validated union members.
    pass


def downgrade() -> None:
    for table in ("note_pages", "note_page_revisions"):
        found = op.get_bind().scalar(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM {table} WHERE jsonb_path_exists(document, "
                '\'$.** ? (@.type == "toggle" || @.type == "database_view")\'))'
            )
        )
        if found:
            raise RuntimeError("Retain nested/view documents and their history; downgrade refused.")
