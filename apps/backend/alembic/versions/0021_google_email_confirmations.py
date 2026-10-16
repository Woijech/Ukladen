"""Add browser-bound email proof for Google links and recheck legacy email claims."""

import sqlalchemy as sa

from alembic import op

revision = "0021_google_email_confirmations"
down_revision = "0020_basic_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_google_email_confirmations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("canonical_email", sa.String(320), nullable=False),
        sa.Column("browser_token_hash", sa.CHAR(64), nullable=False),
        sa.Column("password_fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_google_email_token_hash"),
        sa.CheckConstraint(
            "browser_token_hash ~ '^[0-9a-f]{64}$'", name="ck_google_email_browser_hash"
        ),
        sa.CheckConstraint(
            "password_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_google_email_password_hash"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_google_email_expiry"),
    )
    op.create_index(
        "ix_auth_google_email_confirmations_user_id", "auth_google_email_confirmations", ["user_id"]
    )
    # Earlier Google-only registration treated third-party email claims as authoritative.
    op.execute("""
        UPDATE users SET email_verified_at = NULL
        WHERE email_verified_at IS NOT NULL AND lower(email) NOT LIKE '%@gmail.com'
          AND NOT EXISTS (SELECT 1 FROM auth_credentials c WHERE c.user_id = users.id)
          AND EXISTS (SELECT 1 FROM auth_identities i WHERE i.user_id = users.id
                      AND i.created_at = users.email_verified_at)
          AND NOT EXISTS (SELECT 1 FROM auth_one_time_tokens t WHERE t.user_id = users.id
                          AND t.token_type = 'email_verification' AND t.used_at IS NOT NULL)
    """)


def downgrade() -> None:
    # Do not restore an email-ownership assertion that was never independently verified.
    op.drop_index(
        "ix_auth_google_email_confirmations_user_id", table_name="auth_google_email_confirmations"
    )
    op.drop_table("auth_google_email_confirmations")
