"""Preserve Markdown as versioned blocks with one authoritative document."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0010_page_block_documents"
down_revision = "0009_page_calendar_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("note_pages", sa.Column("document", JSONB(), nullable=True))
    op.execute(
        sa.text("""
        UPDATE note_pages SET document = jsonb_build_object(
            'schema_version', 1,
            'blocks', CASE WHEN content = '' THEN '[]'::jsonb ELSE
                jsonb_build_array(jsonb_build_object(
                    'id', id::text, 'type', 'text', 'text_format', 'markdown', 'text', content
                )) END
        )
    """)
    )
    op.alter_column(
        "note_pages", "document", nullable=False, server_default='{"schema_version":1,"blocks":[]}'
    )
    op.drop_constraint("ck_note_pages_content", "note_pages", type_="check")
    op.drop_column("note_pages", "content")
    op.create_check_constraint(
        "ck_note_pages_document",
        "note_pages",
        "jsonb_typeof(document) = 'object' AND document ? 'schema_version' "
        "AND document ? 'blocks' AND document - 'schema_version' - 'blocks' = '{}'::jsonb "
        "AND document -> 'schema_version' = '1'::jsonb "
        "AND document ->> 'schema_version' = '1' "
        "AND jsonb_typeof(document -> 'blocks') = 'array'",
    )
    op.create_check_constraint(
        "ck_note_pages_document_blocks",
        "note_pages",
        "CASE WHEN jsonb_typeof(document -> 'blocks') = 'array' "
        "THEN jsonb_array_length(document -> 'blocks') <= 1000 ELSE false END",
    )
    op.create_check_constraint(
        "ck_note_pages_document_size", "note_pages", "octet_length(document::text) <= 1048576"
    )


def downgrade() -> None:
    unsafe = op.get_bind().scalar(
        sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM note_pages WHERE CASE
                WHEN jsonb_array_length(document -> 'blocks') = 0 THEN false
                ELSE jsonb_array_length(document -> 'blocks') != 1
                    OR document -> 'blocks' -> 0 ->> 'type' IS DISTINCT FROM 'text'
                    OR document -> 'blocks' -> 0 ->> 'text_format' IS DISTINCT FROM 'markdown'
                    OR document -> 'blocks' -> 0 ->> 'id' IS DISTINCT FROM id::text
                    OR document -> 'blocks' -> 0 ->> 'text' IS NOT DISTINCT FROM ''
                END
        )
    """)
    )
    if unsafe:
        raise RuntimeError("Cannot downgrade page documents without losing block structure or IDs.")
    op.add_column("note_pages", sa.Column("content", sa.Text(), nullable=True))
    op.execute(
        sa.text("""
        UPDATE note_pages SET content = CASE WHEN jsonb_array_length(document -> 'blocks') = 0
            THEN '' ELSE document -> 'blocks' -> 0 ->> 'text' END
    """)
    )
    op.alter_column("note_pages", "content", nullable=False, server_default="")
    op.create_check_constraint(
        "ck_note_pages_content", "note_pages", "char_length(content) <= 100000"
    )
    for name in (
        "ck_note_pages_document_size",
        "ck_note_pages_document_blocks",
        "ck_note_pages_document",
    ):
        op.drop_constraint(name, "note_pages", type_="check")
    op.drop_column("note_pages", "document")
