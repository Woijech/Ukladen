from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.modules.academics.application.ports import AcademicProviderUnavailable
from app.modules.academics.domain.profile import AcademicPeriod, GroupContext, UniversityGroup

IIS_API = "https://iis.bsuir.by/api/v1"


class IisGroup(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int = Field(gt=0, le=2**63 - 1)
    name: str = Field(min_length=1)
    facultyId: int = Field(gt=0)
    facultyName: str = Field(min_length=1)
    facultyAbbrev: str = Field(min_length=1)
    specialityDepartmentEducationFormId: int = Field(gt=0)
    specialityName: str = Field(min_length=1)
    specialityAbbrev: str = Field(min_length=1)
    course: int | None = Field(gt=0)
    educationDegree: int = Field(gt=0)

    def to_domain(self) -> UniversityGroup:
        return UniversityGroup(
            self.id,
            self.name,
            self.facultyId,
            self.facultyName,
            self.facultyAbbrev,
            self.specialityDepartmentEducationFormId,
            self.specialityName,
            self.specialityAbbrev,
            self.course,
            self.educationDegree,
        )


class IisLesson(BaseModel):
    model_config = ConfigDict(strict=True)

    numSubgroup: int = Field(ge=0, le=2**31 - 1)


class IisScheduleIdentity(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int
    name: str


class IisSchedule(BaseModel):
    model_config = ConfigDict(strict=True)

    studentGroupDto: IisScheduleIdentity
    schedules: dict[str, list[IisLesson]] | None
    exams: list[IisLesson] | None
    currentTerm: str | None = None
    currentPeriod: str | None = None
    startDate: str | None
    endDate: str | None
    startExamsDate: str | None
    endExamsDate: str | None

    def to_context(self, group: UniversityGroup) -> GroupContext:
        if (self.studentGroupDto.id, self.studentGroupDto.name) != (group.id, group.name):
            raise ValueError("Mismatched schedule group.")
        dates = [
            datetime.strptime(value, "%d.%m.%Y").date() if value is not None else None
            for value in (self.startDate, self.endDate, self.startExamsDate, self.endExamsDate)
        ]
        for start, end in (dates[:2], dates[2:]):
            if start is not None and end is not None and start > end:
                raise ValueError("Invalid period dates.")
        period = (
            AcademicPeriod(self.currentTerm, self.currentPeriod, *dates)
            if self.currentTerm or self.currentPeriod or any(dates)
            else None
        )
        lessons = [lesson for day in (self.schedules or {}).values() for lesson in day]
        lessons.extend(self.exams or [])
        subgroups = tuple(
            sorted({lesson.numSubgroup for lesson in lessons if lesson.numSubgroup > 0})
        )
        return GroupContext(group, True, subgroups, period)


class IisAcademicProvider:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def list_groups(self) -> list[UniversityGroup]:
        try:
            response = self._get("/student-groups")
            rows = TypeAdapter(list[IisGroup]).validate_json(response.content)
            if len({row.id for row in rows}) != len(rows) or len({row.name for row in rows}) != len(
                rows
            ):
                raise ValueError("Duplicate group identity.")
            return [row.to_domain() for row in rows]
        except httpx.HTTPError, ValidationError, ValueError:
            raise AcademicProviderUnavailable() from None

    def get_context(self, group: UniversityGroup) -> GroupContext:
        try:
            response = self._get(
                "/schedule", params={"studentGroup": group.name}, allow_missing=True
            )
            if response.status_code == 404:
                return GroupContext(group, False)
            return IisSchedule.model_validate_json(response.content).to_context(group)
        except httpx.HTTPError, ValidationError, ValueError:
            raise AcademicProviderUnavailable() from None

    def _get(
        self, path: str, *, params: dict[str, str] | None = None, allow_missing: bool = False
    ) -> httpx.Response:
        request = self.client.build_request(
            "GET",
            IIS_API + path,
            params=params,
            timeout=httpx.Timeout(5, connect=3),
            headers={"Accept": "application/json"},
        )
        request.headers.pop("cookie", None)
        request.headers.pop("authorization", None)
        response = self.client.send(request, auth=None, follow_redirects=False)
        if not (allow_missing and response.status_code == 404):
            response.raise_for_status()
        return response
