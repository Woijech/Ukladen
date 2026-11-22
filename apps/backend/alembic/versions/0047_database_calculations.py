"""Preserve owned relation definitions and bounded formula/rollup settings."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0047_database_calculations"
down_revision = "0046_database_layouts"
branch_labels = None
depends_on = None

OLD_KINDS = "'text', 'number', 'checkbox', 'select', 'multi_select', 'url', 'date'"


def upgrade() -> None:
    op.add_column(
        "workspace_database_properties", sa.Column("relation_database_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "workspace_database_properties",
        sa.Column("calculation", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_foreign_key(
        "fk_database_properties_relation_owner",
        "workspace_database_properties",
        "workspace_databases",
        ["relation_database_id", "user_id"],
        ["id", "user_id"],
    )
    op.create_check_constraint(
        "ck_database_properties_relation",
        "workspace_database_properties",
        "(kind = 'relation') = (relation_database_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_database_properties_calculation",
        "workspace_database_properties",
        "jsonb_typeof(calculation) = 'object' AND octet_length(calculation::text) <= 16384 "
        "AND (kind IN ('formula', 'rollup') OR calculation = '{}'::jsonb) "
        "AND (kind <> 'formula' OR COALESCE(jsonb_typeof(calculation -> 'expression') = 'string' "
        "AND char_length(btrim(calculation ->> 'expression')) BETWEEN 1 AND 2000, false)) "
        "AND (kind <> 'rollup' OR COALESCE(calculation ->> 'operation' IN "
        "('count', 'sum', 'average', 'min', 'max') "
        "AND jsonb_typeof(calculation -> 'relation_property_id') = 'string', false))",
    )
    op.drop_constraint(
        "ck_database_properties_kind", "workspace_database_properties", type_="check"
    )
    op.create_check_constraint(
        "ck_database_properties_kind",
        "workspace_database_properties",
        f"kind IN ({OLD_KINDS}, 'relation', 'formula', 'rollup')",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workspace_database_properties "
            "WHERE kind IN ('relation', 'formula', 'rollup') OR relation_database_id IS NOT NULL "
            "OR calculation <> '{}'::jsonb)"
        )
    ):
        raise RuntimeError(
            "Remove new relation/calculation definitions explicitly before downgrading."
        )
    for name in (
        "ck_database_properties_calculation",
        "ck_database_properties_relation",
        "ck_database_properties_kind",
    ):
        op.drop_constraint(name, "workspace_database_properties", type_="check")
    op.drop_constraint(
        "fk_database_properties_relation_owner", "workspace_database_properties", type_="foreignkey"
    )
    op.create_check_constraint(
        "ck_database_properties_kind", "workspace_database_properties", f"kind IN ({OLD_KINDS})"
    )
    op.drop_column("workspace_database_properties", "calculation")
    op.drop_column("workspace_database_properties", "relation_database_id")
