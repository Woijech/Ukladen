"""add selected university groups and academic profiles"""

import sqlalchemy as sa

from alembic import op

revision = "0005_academics_profile"
down_revision = "0004_users_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "university_groups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("faculty_id", sa.BigInteger(), nullable=False),
        sa.Column("faculty_name", sa.Text(), nullable=False),
        sa.Column("faculty_abbrev", sa.Text(), nullable=False),
        sa.Column("speciality_department_education_form_id", sa.BigInteger(), nullable=False),
        sa.Column("speciality_name", sa.Text(), nullable=False),
        sa.Column("speciality_abbrev", sa.Text(), nullable=False),
        sa.Column("course", sa.Integer(), nullable=True),
        sa.Column("education_degree", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "id > 0 AND faculty_id > 0 AND speciality_department_education_form_id > 0",
            name="ck_university_groups_identifiers",
        ),
        sa.CheckConstraint("char_length(name) > 0", name="ck_university_groups_name"),
        sa.CheckConstraint("course IS NULL OR course > 0", name="ck_university_groups_course"),
        sa.CheckConstraint("education_degree > 0", name="ck_university_groups_degree"),
    )
    op.create_table(
        "academic_profiles",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "group_id", sa.BigInteger(), sa.ForeignKey("university_groups.id"), nullable=False
        ),
        sa.Column("subgroup", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "subgroup IS NULL OR subgroup > 0", name="ck_academic_profiles_subgroup"
        ),
    )


def downgrade() -> None:
    op.drop_table("academic_profiles")
    op.drop_table("university_groups")
