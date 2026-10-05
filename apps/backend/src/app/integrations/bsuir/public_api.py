import re
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
from app.modules.schedule.application.provider import (
    Announcement,
    AnnouncementPage,
    Schedule,
    UpdateDate,
)

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
    if key in {"job_positions", "repeat_group"}:
        return value
    if isinstance(value, Mapping):
        if key in {"schedules", "next_schedules"}:
            return {day: normalize_payload(lessons) for day, lessons in value.items()}
        result = {
            ALIASES.get(name, to_snake(name)): normalize_payload(
                item, ALIASES.get(name, to_snake(name))
            )
            for name, item in value.items()
        }
        if len(result) != len(value):
            raise ValueError("Ambiguous source fields.")
        return result
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


def require_url_id(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value) is None:
        raise InvalidUniversityRequest()


def require_group_number(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
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
            return result.validate_python(normalize_payload(response.json()), strict=True)
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

    def get_group_schedule(self, group_number: str) -> Schedule | None:
        require_group_number(group_number)
        group = next((row for row in self.list_groups() if row.name == group_number), None)
        if group is None:
            raise UniversityEntityNotFound()
        schedule = self._read(
            "/schedule",
            TypeAdapter(Schedule),
            params={"studentGroup": group.name},
            allow_missing=True,
        )
        if schedule is not None and (
            schedule.group is None
            or (schedule.group.id, schedule.group.name) != (group.id, group.name)
            or schedule.teacher is not None
        ):
            raise AcademicProviderUnavailable()
        return schedule

    def get_teacher_schedule(self, teacher_id: int) -> Schedule | None:
        teacher = self.get_teacher(teacher_id)
        schedule = self.get_teacher_schedule_by_url_id(teacher.url_id)
        if schedule is not None and (schedule.teacher is None or schedule.teacher.id != teacher_id):
            raise AcademicProviderUnavailable()
        return schedule

    def get_teacher_schedule_by_url_id(self, url_id: str) -> Schedule | None:
        require_url_id(url_id)
        schedule = self._read(
            f"/employees/schedule/{url_id}", TypeAdapter(Schedule), allow_missing=True
        )
        if schedule is not None and (
            schedule.teacher is None
            or schedule.teacher.url_id != url_id
            or schedule.group is not None
        ):
            raise AcademicProviderUnavailable()
        return schedule

    def get_teacher_announcements(
        self, teacher_id: int, *, page: int = 0, size: int = 20, date_from: date | None = None
    ) -> AnnouncementPage:
        return self.get_teacher_announcements_by_url_id(
            self.get_teacher(teacher_id).url_id, page=page, size=size, date_from=date_from
        )

    def get_teacher_announcements_by_url_id(
        self, url_id: str, *, page: int = 0, size: int = 20, date_from: date | None = None
    ) -> AnnouncementPage:
        require_url_id(url_id)
        if type(page) is not int or page < 0 or type(size) is not int or not 1 <= size <= 100:
            raise InvalidUniversityRequest()
        if date_from is not None and type(date_from) is not date:
            raise InvalidUniversityRequest()
        params = {"url-id": url_id, "page": str(page), "size": str(size)}
        if date_from is not None:
            params["dateFrom"] = date_from.isoformat()
        result = self._read(
            "/announcements/employees", TypeAdapter(AnnouncementPage), params=params
        )
        assert result is not None
        if result.number != page or result.size != size or len(result.content) > size:
            raise AcademicProviderUnavailable()
        return result

    def get_department_announcements(self, department_id: int) -> list[Announcement]:
        require_identifier(department_id)
        department = next((row for row in self.list_departments() if row.id == department_id), None)
        if department is None:
            raise UniversityEntityNotFound()
        if department.url_id is None:
            raise AcademicProviderUnavailable()
        require_url_id(department.url_id)
        result = self._read(
            "/announcements/departments",
            TypeAdapter(list[Announcement]),
            params={"url-id": department.url_id},
        )
        assert result is not None
        return result

    def get_group_update_date(
        self, *, group_number: str | None = None, group_id: int | None = None
    ) -> date | None:
        if (group_number is None) == (group_id is None):
            raise InvalidUniversityRequest()
        if group_id is not None:
            require_identifier(group_id)
            params = {"id": str(group_id)}
        else:
            assert group_number is not None
            require_group_number(group_number)
            params = {"groupNumber": group_number}
        return self._update_date("/last-update-date/student-group", params)

    def get_teacher_update_date(
        self, *, teacher_id: int | None = None, url_id: str | None = None
    ) -> date | None:
        if (teacher_id is None) == (url_id is None):
            raise InvalidUniversityRequest()
        if teacher_id is not None:
            require_identifier(teacher_id)
            params = {"id": str(teacher_id)}
        else:
            assert url_id is not None
            require_url_id(url_id)
            params = {"url-id": url_id}
        return self._update_date("/last-update-date/employee", params)

    def _update_date(self, path: str, params: dict[str, str]) -> date | None:
        result = self._read(path, TypeAdapter(UpdateDate), params=params, allow_missing=True)
        return result.date if result else None

    def get_current_week(self) -> int:
        result = self._read("/schedule/current-week", TypeAdapter(int))
        if type(result) is not int or not 1 <= result <= 4:
            raise AcademicProviderUnavailable()
        return result
