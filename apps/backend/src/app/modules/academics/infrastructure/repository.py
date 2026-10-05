from dataclasses import asdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.academics.domain.profile import AcademicProfile, UniversityGroup
from app.modules.academics.infrastructure.orm import AcademicProfileModel, UniversityGroupModel


class SqlAlchemyAcademicProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID) -> AcademicProfile | None:
        row = self.session.execute(
            select(AcademicProfileModel, UniversityGroupModel)
            .join(UniversityGroupModel, AcademicProfileModel.group_id == UniversityGroupModel.id)
            .where(AcademicProfileModel.user_id == user_id)
            .execution_options(populate_existing=True)
        ).one_or_none()
        if row is None:
            return None
        profile, group = row
        return AcademicProfile(
            profile.user_id,
            UniversityGroup(
                group.id,
                group.name,
                group.faculty_id,
                group.faculty_name,
                group.faculty_abbrev,
                group.speciality_department_education_form_id,
                group.speciality_name,
                group.speciality_abbrev,
                group.course,
                group.education_degree,
            ),
            profile.subgroup,
            profile.created_at,
            profile.updated_at,
        )

    def save(self, user_id: UUID, group: UniversityGroup, subgroup: int | None) -> AcademicProfile:
        values = asdict(group)
        self.session.execute(
            insert(UniversityGroupModel)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[UniversityGroupModel.id],
                set_={key: value for key, value in values.items() if key != "id"},
            )
        )
        self.session.execute(
            insert(AcademicProfileModel)
            .values(user_id=user_id, group_id=group.id, subgroup=subgroup)
            .on_conflict_do_update(
                index_elements=[AcademicProfileModel.user_id],
                set_={"group_id": group.id, "subgroup": subgroup, "updated_at": func.now()},
            )
        )
        profile = self.get(user_id)
        assert profile is not None
        return profile
