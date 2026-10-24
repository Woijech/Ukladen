"""Retain bounded source references with their owner-scoped assistant message."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0025_ai_message_sources"
down_revision = "0024_ai_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_messages",
        sa.Column(
            "sources", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_ai_messages_sources",
        "ai_messages",
        "jsonb_typeof(sources) = 'array' AND jsonb_array_length(sources) <= 64 "
        "AND octet_length(sources::text) <= 65536 "
        "AND (role = 'assistant' OR sources = '[]'::jsonb)",
    )


def downgrade() -> None:
    op.execute("LOCK TABLE ai_messages IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM ai_messages WHERE sources <> '[]'::jsonb) THEN
            RAISE EXCEPTION 'Cannot downgrade: retained source references must be preserved';
        END IF;
    END $$""")
    op.drop_constraint("ck_ai_messages_sources", "ai_messages", type_="check")
    op.drop_column("ai_messages", "sources")
