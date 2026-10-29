"""Allow exact owner-reviewed revisions without replaying the model interrupt."""

import sqlalchemy as sa

from alembic import op

revision = "0038_ai_action_revisions"
down_revision = "0037_task_origins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_ai_action_run", "ai_action_proposals", type_="unique")
    op.create_unique_constraint(
        "uq_ai_action_run_interrupt", "ai_action_proposals", ["run_id", "interrupt_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE ai_action_proposals IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM ai_action_proposals GROUP BY run_id HAVING count(*) > 1)"
        )
    ):
        raise RuntimeError("Cannot downgrade populated action revisions.")
    op.drop_constraint("uq_ai_action_run_interrupt", "ai_action_proposals", type_="unique")
    op.create_unique_constraint("uq_ai_action_run", "ai_action_proposals", ["run_id"])
