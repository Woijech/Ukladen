"""Versioned derived semantic index; canonical sources are untouched."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.modules.search.infrastructure.vector import Vector

revision = "0029_search_chunks"
down_revision = "0028_material_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_index_generations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("profile", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "search_index_sources",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("source", sa.Text(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "generation",
            sa.Text(),
            sa.ForeignKey("search_index_generations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("source IN ('page','material')", name="ck_search_index_source"),
        sa.CheckConstraint(
            "status IN ('pending','processing','ready','failed')", name="ck_search_index_status"
        ),
        sa.CheckConstraint("version > 0 AND attempts >= 0", name="ck_search_index_version"),
    )
    op.create_index(
        "ix_search_index_dispatch", "search_index_sources", ["generation", "status", "lease_until"]
    )
    op.create_table(
        "search_chunks",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.Text(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), primary_key=True),
        sa.Column("generation", sa.Text(), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "source", "source_id", "generation"],
            [
                "search_index_sources.user_id",
                "search_index_sources.source",
                "search_index_sources.source_id",
                "search_index_sources.generation",
            ],
            ondelete="CASCADE",
            name="fk_search_chunk_source",
        ),
        sa.CheckConstraint(
            '"start" >= 0 AND "end" > "start" AND version > 0 AND number >= 0',
            name="ck_search_chunk_range",
        ),
    )


def downgrade() -> None:
    op.drop_table("search_chunks")
    op.drop_table("search_index_sources")
    op.drop_table("search_index_generations")
