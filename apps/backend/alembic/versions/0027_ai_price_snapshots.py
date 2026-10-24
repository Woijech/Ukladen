"""Keep configured price metadata with each admitted run, never infer invoices."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0027_ai_price_snapshots"
down_revision = "0026_ai_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_runs", sa.Column("price", postgresql.JSONB(), nullable=True))
    op.create_check_constraint(
        "ck_ai_runs_price",
        "ai_runs",
        "price IS NULL OR (jsonb_typeof(price) = 'object' AND octet_length(price::text) <= 1024)",
    )


def downgrade() -> None:
    op.execute("LOCK TABLE ai_runs IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM ai_runs WHERE price IS NOT NULL) THEN
            RAISE EXCEPTION 'Cannot downgrade: retained price snapshots must be preserved';
        END IF;
    END $$""")
    op.drop_constraint("ck_ai_runs_price", "ai_runs", type_="check")
    op.drop_column("ai_runs", "price")
