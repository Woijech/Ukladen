"""Add materials and object cleanup ledger"""

import sqlalchemy as sa

from alembic import op

revision = "0019_materials"
down_revision = "0018_reminders_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=4), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=True),
        sa.Column("media_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(kind = 'file' AND filename IS NOT NULL AND media_type IS NOT NULL "
            "AND size_bytes BETWEEN 1 AND 26214400 AND url IS NULL) OR "
            "(kind = 'link' AND filename IS NULL AND media_type IS NULL "
            "AND size_bytes = 0 AND url IS NOT NULL AND status = 'ready')",
            name="ck_materials_kind",
        ),
        sa.CheckConstraint(
            "(status = 'processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status != 'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="ck_materials_lease",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN ('invalid_document', 'document_limit', "
            "'storage_unavailable', 'processing_timeout', 'no_extractable_text')",
            name="ck_materials_error",
        ),
        sa.CheckConstraint(
            "status IN ('uploading', 'pending', 'processing', 'ready', 'failed')",
            name="ck_materials_status",
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 200 AND title = btrim(title)",
            name="ck_materials_title",
        ),
        sa.CheckConstraint(
            "version > 0 AND attempts BETWEEN 0 AND 3", name="ck_materials_versions"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_materials_id_owner"),
    )
    op.create_index(
        "ix_materials_owner",
        "materials",
        ["user_id", "trashed_at", "created_at", "id"],
        unique=False,
    )
    op.create_index("ix_materials_trash", "materials", ["trashed_at", "id"], unique=False)
    op.create_index("ix_materials_work", "materials", ["status", "updated_at", "id"], unique=False)
    op.create_table(
        "material_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=True),
        sa.Column("storage_key", sa.String(length=128), nullable=False),
        sa.CheckConstraint(
            "storage_key = 'materials/' || user_id::text || '/' || id::text",
            name="ck_material_objects_key",
        ),
        sa.CheckConstraint(
            "material_id IS NULL OR material_id = id", name="ck_material_objects_id"
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_material_objects_orphan", "material_objects", ["material_id"], unique=False)
    op.create_table(
        "page_material_links",
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "user_id"],
            ["materials.id", "materials.user_id"],
            name="fk_page_material_links_material_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "user_id"],
            ["note_pages.id", "note_pages.user_id"],
            name="fk_page_material_links_page_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("page_id", "material_id"),
    )
    op.create_index(
        "ix_page_material_links_reverse",
        "page_material_links",
        ["user_id", "material_id", "page_id"],
        unique=False,
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM materials) OR EXISTS (SELECT 1 FROM material_objects)"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade while materials or object cleanup records must be preserved."
        )
    op.drop_index("ix_page_material_links_reverse", table_name="page_material_links")
    op.drop_table("page_material_links")
    op.drop_index("ix_material_objects_orphan", table_name="material_objects")
    op.drop_table("material_objects")
    op.drop_index("ix_materials_work", table_name="materials")
    op.drop_index("ix_materials_trash", table_name="materials")
    op.drop_index("ix_materials_owner", table_name="materials")
    op.drop_table("materials")
