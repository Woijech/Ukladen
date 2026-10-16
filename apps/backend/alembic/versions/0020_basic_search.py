"""Index current page content and derived material text without OCR or embeddings."""

import sqlalchemy as sa

from alembic import op

revision = "0020_basic_search"
down_revision = "0019_materials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION ukladen_page_search_body(document jsonb) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
          SELECT coalesce(string_agg(
            CASE WHEN block->>'type' = 'list' THEN (
              SELECT string_agg(item, E'\n' ORDER BY n) FROM jsonb_array_elements_text(
                CASE WHEN jsonb_typeof(block->'items') = 'array'
                  THEN block->'items' ELSE '[]'::jsonb END
              ) WITH ORDINALITY AS items(item, n)
            ) ELSE coalesce(block->>'text', '') END, E'\n' ORDER BY ordinal
          ), '') FROM jsonb_array_elements(document->'blocks')
            WITH ORDINALITY AS blocks(block, ordinal)
        $$
    """)
    op.execute("""
        CREATE FUNCTION ukladen_search_vector(title text, body text) RETURNS tsvector
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
          SELECT setweight(
            to_tsvector('pg_catalog.simple', title) || to_tsvector('pg_catalog.russian', title)
            || to_tsvector('pg_catalog.english', title), 'A') || setweight(
            to_tsvector('pg_catalog.simple', body) || to_tsvector('pg_catalog.russian', body)
            || to_tsvector('pg_catalog.english', body), 'B')
        $$
    """)
    op.create_table(
        "search_material_documents",
        sa.Column("material_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id", "user_id"],
            ["materials.id", "materials.user_id"],
            ondelete="CASCADE",
            name="fk_search_material_owner",
        ),
        sa.CheckConstraint("octet_length(body) <= 2097152", name="ck_search_material_size"),
    )
    op.create_index(
        "ix_search_material_owner", "search_material_documents", ["user_id", "material_id"]
    )
    op.create_index(
        "ix_search_material_body",
        "search_material_documents",
        [sa.text("ukladen_search_vector('', body)")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_materials_title_search",
        "materials",
        [sa.text("ukladen_search_vector(title, '')")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_note_pages_search",
        "note_pages",
        [sa.text("ukladen_search_vector(title, ukladen_page_search_body(document))")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_note_pages_search", table_name="note_pages")
    op.drop_index("ix_materials_title_search", table_name="materials")
    op.drop_table("search_material_documents")
    op.execute("DROP FUNCTION ukladen_search_vector(text, text)")
    op.execute("DROP FUNCTION ukladen_page_search_body(jsonb)")
