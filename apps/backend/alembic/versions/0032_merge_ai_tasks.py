"""Join independent AI and task migration histories without rewriting either branch."""

revision = "0032_merge_ai_tasks"
down_revision = ("0031_ai_action_proposals", "0024_task_trash")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
