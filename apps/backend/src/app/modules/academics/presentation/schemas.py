from datetime import date
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.academics.domain.profile import normalize_academic_changes


class AcademicProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    group_id: int | None = Field(default=None, gt=0, le=2**63 - 1)
    subgroup: int | None = Field(default=None, gt=0, le=2**31 - 1)

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        normalize_academic_changes(self.model_dump(exclude_unset=True))
        return self


class UniversityGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    faculty_id: int
    faculty_name: str
    faculty_abbrev: str
    speciality_department_education_form_id: int
    speciality_name: str
    speciality_abbrev: str
    course: int | None
    education_degree: int


class AcademicPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    term_label: str | None
    period_label: str | None
    starts_on: date | None
    ends_on: date | None
    exams_start_on: date | None
    exams_end_on: date | None


class GroupContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group: UniversityGroupResponse
    schedule_available: bool
    subgroups: tuple[int, ...]
    period: AcademicPeriodResponse | None


class AcademicProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group: UniversityGroupResponse
    subgroup: int | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
