"""Preserve incomplete assistant answers and safe terminal failure reasons."""

import sqlalchemy as sa

from alembic import op

revision = "0044_ai_partial_answers"
down_revision = "0043_personal_calendars"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_messages",
        sa.Column("incomplete", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_constraint("ck_ai_messages_content", "ai_messages", type_="check")
    op.create_check_constraint(
        "ck_ai_messages_content",
        "ai_messages",
        "octet_length(content) BETWEEN 1 AND "
        "CASE WHEN role = 'assistant' THEN 65536 ELSE 16384 END",
    )
    op.create_check_constraint(
        "ck_ai_messages_incomplete", "ai_messages", "NOT incomplete OR role = 'assistant'"
    )
    op.add_column("ai_runs", sa.Column("failure_reason", sa.String(32), nullable=True))
    op.create_check_constraint(
        "ck_ai_runs_failure_reason",
        "ai_runs",
        "failure_reason IS NULL OR (status IN ('failed','cancelled') AND failure_reason IN "
        "('output_limit','context_limit','step_limit','timeout','invalid_response',"
        "'unavailable','cancelled','interrupted'))",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM ai_messages "
            "WHERE incomplete OR octet_length(content) > 16384) "
            "OR EXISTS (SELECT 1 FROM ai_runs WHERE failure_reason IS NOT NULL)"
        )
    ):
        raise RuntimeError("Retained answer recovery data prevents downgrade")
    op.drop_constraint("ck_ai_runs_failure_reason", "ai_runs", type_="check")
    op.drop_column("ai_runs", "failure_reason")
    op.drop_constraint("ck_ai_messages_incomplete", "ai_messages", type_="check")
    op.drop_constraint("ck_ai_messages_content", "ai_messages", type_="check")
    op.create_check_constraint(
        "ck_ai_messages_content", "ai_messages", "octet_length(content) BETWEEN 1 AND 16384"
    )
    op.drop_column("ai_messages", "incomplete")
