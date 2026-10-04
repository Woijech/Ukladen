"""add user profile fields without changing authentication data"""

import sqlalchemy as sa

from alembic import op

revision = "0003_users_profile"
down_revision = "0002_auth_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"))
    op.add_column("users", sa.Column("locale", sa.String(2), nullable=False, server_default="ru"))
    op.create_check_constraint(
        "ck_users_display_name",
        "users",
        "display_name IS NULL OR (char_length(display_name) BETWEEN 1 AND 100 "
        "AND display_name !~ '^[[:space:]]|[[:space:]]$')",
    )
    op.create_check_constraint("ck_users_timezone", "users", "char_length(timezone) > 0")
    op.create_check_constraint("ck_users_locale", "users", "locale IN ('ru', 'en')")


def downgrade() -> None:
    for name in ("locale", "timezone", "display_name"):
        op.drop_constraint(f"ck_users_{name}", "users", type_="check")
        op.drop_column("users", name)
