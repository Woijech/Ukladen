"""Persist independent owner assistant preferences."""

import sqlalchemy as sa

from alembic import op

revision = "0026_ai_preferences"
down_revision = "0025_ai_message_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_preferences",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "octet_length(instructions) <= 8192", name="ck_ai_preferences_instructions"
        ),
        sa.CheckConstraint("version > 0", name="ck_ai_preferences_version"),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE ai_preferences IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM ai_preferences WHERE instructions <> '') THEN
            RAISE EXCEPTION 'Cannot downgrade: retained assistant instructions must be preserved';
        END IF;
    END $$""")
    op.drop_table("ai_preferences")
