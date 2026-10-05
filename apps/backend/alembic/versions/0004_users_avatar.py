"""add the private avatar storage reference"""

import sqlalchemy as sa

from alembic import op

revision = "0004_users_avatar"
down_revision = "0003_users_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_key", sa.String(100), nullable=True))
    op.create_check_constraint(
        "ck_users_avatar_key",
        "users",
        "avatar_key IS NULL OR avatar_key ~ ('^avatars/' || id::text || '/[0-9a-f]{32}[.]png$')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_avatar_key", "users", type_="check")
    op.drop_column("users", "avatar_key")
