"""Preserve minimal replay and committed-context markers after journal expiry."""

import sqlalchemy as sa

from alembic import op

revision = "0023_ai_run_receipts"
down_revision = "0022_ai_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_run_receipts",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "submission_id", name="uq_ai_receipts_submission"),
    )


def downgrade() -> None:
    op.execute("""
        LOCK TABLE ai_run_receipts IN ACCESS EXCLUSIVE MODE;
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM ai_run_receipts) THEN
                RAISE EXCEPTION 'Cannot downgrade while AI replay receipts remain.';
            END IF;
        END $$;
    """)
    op.drop_table("ai_run_receipts")
