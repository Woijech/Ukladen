"""Preserve extracted PDF page and presentation slide locations."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0028_material_locations"
down_revision = "0027_ai_price_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_material_documents",
        sa.Column("locations", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "search_material_documents",
        sa.Column("extraction_revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("search_material_documents", "extraction_revision")
    op.drop_column("search_material_documents", "locations")
