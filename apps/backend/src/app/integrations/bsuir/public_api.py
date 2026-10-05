from collections.abc import Mapping
from datetime import date, datetime, time
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError
from pydantic.alias_generators import to_snake

from app.integrations.bsuir.academics import IisAcademicProvider
from app.modules.academics.application.directory import (
    Department,
    DirectoryRecord,
    Faculty,
    InvalidUniversityRequest,
    Room,
    Speciality,
    Teacher,
    UniversityEntityNotFound,
)
from app.modules.academics.application.ports import AcademicProviderUnavailable

# These aliases translate the verified IIS transport into application DTOs.
ALIASES = {
    "academicDepartment": "departments",
    "studentGroupDto": "group",
    "employeeDto": "teacher",
    "numSubgroup": "subgroup",
    "weekNumber": "week_numbers",
    "studentGroups": "groups",
    "employees": "teachers",
    "auditories": "rooms",
    "startLessonTime": "starts_at",
    "endLessonTime": "ends_at",
    "startTime": "starts_at",
    "endTime": "ends_at",
    "startLessonDate": "starts_on",
    "endLessonDate": "ends_on",
    "dateLesson": "date",
    "startDate": "starts_on",
    "endDate": "ends_on",
    "startExamsDate": "exams_start_on",
    "endExamsDate": "exams_end_on",
    "lastUpdateDate": "date",
}
DATE_KEYS = {"date", "starts_on", "ends_on", "exams_start_on", "exams_end_on"}
TIME_KEYS = {"starts_at", "ends_at"}


def normalize_payload(value: Any, key: str = "") -> Any:
    if isinstance(value, Mapping):
        return {
            ALIASES.get(name, to_snake(name)): normalize_payload(
                item, ALIASES.get(name, to_snake(name))
            )
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_payload(item) for item in value]
    if isinstance(value, str) and key in DATE_KEYS:
        return (
            datetime.strptime(value, "%d.%m.%Y").date()
            if "." in value
            else date.fromisoformat(value)
        )
    if isinstance(value, str) and key in TIME_KEYS:
        return time.fromisoformat(value)
    return value


def require_identifier(value: int) -> None:
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise InvalidUniversityRequest()


class IisPublicProvider(IisAcademicProvider):
    """Cookie-free JSON reads; the injected HTTP client is owned by the caller."""

    def _read[T](
        self,
        path: str,
        result: TypeAdapter[T],
        *,
        params: dict[str, str] | None = None,
        allow_missing: bool = False,
    ) -> T | None:
        try:
            response = self._get(path, params=params, allow_missing=allow_missing)
            if response.status_code == 404:
                return None
            return result.validate_python(normalize_payload(response.json()))
        except httpx.HTTPError, ValidationError, ValueError, TypeError:
            raise AcademicProviderUnavailable() from None

    def _catalogue[T: DirectoryRecord](self, path: str, result: TypeAdapter[list[T]]) -> list[T]:
        rows = self._read(path, result)
        assert rows is not None
        if len({row.id for row in rows}) != len(rows):
            raise AcademicProviderUnavailable() from None
        return rows

    def list_teachers(self) -> list[Teacher]:
        rows = self._catalogue("/employees/all", TypeAdapter(list[Teacher]))
        if len({row.url_id for row in rows}) != len(rows):
            raise AcademicProviderUnavailable()
        return rows

    def get_teacher(self, teacher_id: int) -> Teacher:
        require_identifier(teacher_id)
        teacher = next((row for row in self.list_teachers() if row.id == teacher_id), None)
        if teacher is None:
            raise UniversityEntityNotFound()
        return teacher

    def list_faculties(self) -> list[Faculty]:
        return self._catalogue("/faculties", TypeAdapter(list[Faculty]))

    def list_departments(self) -> list[Department]:
        return self._catalogue("/departments", TypeAdapter(list[Department]))

    def list_specialities(self) -> list[Speciality]:
        return self._catalogue("/specialities", TypeAdapter(list[Speciality]))

    def list_rooms(self) -> list[Room]:
        return self._catalogue("/auditories", TypeAdapter(list[Room]))
