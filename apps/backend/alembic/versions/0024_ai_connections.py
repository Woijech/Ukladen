"""Add encrypted personal connections and immutable chat model selections."""

import sqlalchemy as sa

from alembic import op

revision = "0024_ai_connections"
down_revision = "0023_ai_run_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_conversations",
        sa.Column("provider", sa.String(128), nullable=False, server_default="fake"),
    )
    op.add_column(
        "ai_conversations",
        sa.Column("model", sa.String(128), nullable=False, server_default="fake-v1"),
    )
    op.create_table(
        "ai_personal_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=True),
        sa.Column("encryption_key_id", sa.String(32), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("id", "user_id", name="uq_ai_connections_owner"),
        sa.CheckConstraint(
            "char_length(btrim(label)) BETWEEN 1 AND 100 AND label = btrim(label)",
            name="ck_ai_connections_label",
        ),
        sa.CheckConstraint(
            "(disconnected_at IS NULL AND encrypted_key IS NOT NULL "
            "AND encryption_key_id IS NOT NULL)"
            " OR (disconnected_at IS NOT NULL AND encrypted_key IS NULL "
            "AND encryption_key_id IS NULL)",
            name="ck_ai_connections_secret",
        ),
        sa.CheckConstraint(
            "disconnected_at IS NULL OR disconnected_at >= created_at",
            name="ck_ai_connections_time",
        ),
    )
    op.create_index(
        "ix_ai_connections_owner", "ai_personal_connections", ["user_id", "created_at", "id"]
    )
    op.create_table(
        "ai_connection_buckets",
        sa.Column("scope", sa.String(128), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("requests >= 0", name="ck_ai_buckets_requests"),
    )
    for table in ("ai_conversations", "ai_runs"):
        op.add_column(table, sa.Column("offering_id", sa.String(64), nullable=True))
        op.add_column(table, sa.Column("offering_version", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("connection_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_connection_owner",
            table,
            "ai_personal_connections",
            ["connection_id", "user_id"],
            ["id", "user_id"],
        )
        op.create_check_constraint(
            f"ck_{table}_selection",
            table,
            "(offering_id IS NULL AND offering_version IS NULL AND connection_id IS NULL) OR "
            "(offering_id IS NOT NULL AND offering_version IS NOT NULL AND offering_version > 0)",
        )


def downgrade() -> None:
    op.execute("""
        LOCK TABLE ai_personal_connections, ai_conversations, ai_runs IN ACCESS EXCLUSIVE MODE;
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM ai_personal_connections)
               OR EXISTS (SELECT 1 FROM ai_conversations WHERE offering_id IS NOT NULL)
               OR EXISTS (SELECT 1 FROM ai_runs WHERE offering_id IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while AI connections or model selections remain.';
            END IF;
        END $$;
    """)
    for table in ("ai_runs", "ai_conversations"):
        op.drop_constraint(f"ck_{table}_selection", table, type_="check")
        op.drop_constraint(f"fk_{table}_connection_owner", table, type_="foreignkey")
        for column in ("connection_id", "offering_version", "offering_id"):
            op.drop_column(table, column)
    op.drop_table("ai_connection_buckets")
    op.drop_table("ai_personal_connections")
    op.drop_column("ai_conversations", "model")
    op.drop_column("ai_conversations", "provider")
