from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UniversityGroupModel(Base):
    __tablename__ = "university_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text)
    faculty_id: Mapped[int] = mapped_column(BigInteger)
    faculty_name: Mapped[str] = mapped_column(Text)
    faculty_abbrev: Mapped[str] = mapped_column(Text)
    speciality_department_education_form_id: Mapped[int] = mapped_column(BigInteger)
    speciality_name: Mapped[str] = mapped_column(Text)
    speciality_abbrev: Mapped[str] = mapped_column(Text)
    course: Mapped[int | None]
    education_degree: Mapped[int]

    __table_args__ = (
        CheckConstraint(
            "id > 0 AND faculty_id > 0 AND speciality_department_education_form_id > 0",
            name="ck_university_groups_identifiers",
        ),
        CheckConstraint("char_length(name) > 0", name="ck_university_groups_name"),
        CheckConstraint("course IS NULL OR course > 0", name="ck_university_groups_course"),
        CheckConstraint("education_degree > 0", name="ck_university_groups_degree"),
    )


class AcademicProfileModel(Base):
    __tablename__ = "academic_profiles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(ForeignKey("university_groups.id"))
    subgroup: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("subgroup IS NULL OR subgroup > 0", name="ck_academic_profiles_subgroup"),
    )
