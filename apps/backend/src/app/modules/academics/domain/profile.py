from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


class InvalidAcademicSelection(ValueError):
    """The requested group or subgroup cannot be selected."""


class AcademicProfileConflict(Exception):
    """The group changed while a subgroup selection was being validated."""


@dataclass(frozen=True)
class UniversityGroup:
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


@dataclass(frozen=True)
class AcademicPeriod:
    term_label: str | None
    period_label: str | None
    starts_on: date | None
    ends_on: date | None
    exams_start_on: date | None
    exams_end_on: date | None


@dataclass(frozen=True)
class GroupContext:
    group: UniversityGroup
    schedule_available: bool
    subgroups: tuple[int, ...] = ()
    period: AcademicPeriod | None = None


@dataclass(frozen=True)
class AcademicProfile:
    user_id: UUID
    group: UniversityGroup
    subgroup: int | None
    created_at: datetime
    updated_at: datetime


def normalize_academic_changes(changes: Mapping[str, object]) -> dict[str, int | None]:
    if not changes or changes.keys() - {"group_id", "subgroup"}:
        raise InvalidAcademicSelection("Invalid academic profile changes.")
    result: dict[str, int | None] = {}
    for field, value in changes.items():
        if field == "subgroup" and value is None:
            result[field] = None
        elif type(value) is int and 0 < value <= (2**63 - 1 if field == "group_id" else 2**31 - 1):
            result[field] = value
        else:
            raise InvalidAcademicSelection("Invalid academic profile changes.")
    return result
