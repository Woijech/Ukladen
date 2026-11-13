"""Use Minsk timezone for all profiles."""

from alembic import op

revision = "0042_minsk_timezone"
down_revision = "0041_ai_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET timezone = 'Europe/Minsk' WHERE timezone <> 'Europe/Minsk'")
    op.alter_column("users", "timezone", server_default="Europe/Minsk")


def downgrade() -> None:
    op.alter_column("users", "timezone", server_default="UTC")
