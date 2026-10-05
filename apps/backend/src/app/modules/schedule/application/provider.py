from datetime import date, time
from typing import Annotated, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.modules.academics.application.directory import DirectoryItem, Identifier, Teacher


class ScheduleData(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)


class GroupDetails(DirectoryItem):
    faculty_id: Identifier
    faculty_name: str
    faculty_abbrev: str
    speciality_department_education_form_id: Identifier
    speciality_name: str
    speciality_abbrev: str
    course: Annotated[int, Field(gt=0)] | None
    education_degree: Annotated[int, Field(gt=0)]
    calendar_id: str | None = None


class LessonGroup(ScheduleData):
    name: str = Field(min_length=1)
    speciality_name: str
    speciality_code: str
    number_of_students: Annotated[int, Field(ge=0)]
    education_degree: Annotated[int, Field(gt=0)]


class Lesson(ScheduleData):
    subgroup: Annotated[int, Field(ge=0, le=2**31 - 1)]
    week_numbers: list[Annotated[int, Field(ge=1, le=4)]]
    groups: list[LessonGroup]
    teachers: list[Teacher] | None
    rooms: list[str]
    starts_at: time
    ends_at: time
    subject: str | None
    subject_full_name: str | None
    lesson_type_abbrev: str | None
    note: str | None
    date: date | None
    starts_on: date | None
    ends_on: date | None
    announcement: bool
    split: bool


class Schedule(ScheduleData):
    group: GroupDetails | None
    teacher: Teacher | None
    schedules: dict[str, list[Lesson]] | None
    exams: list[Lesson] | None
    starts_on: date | None
    ends_on: date | None
    exams_start_on: date | None
    exams_end_on: date | None
    next_schedules: dict[str, list[Lesson]] | None = None
    current_term: str | None = None
    current_period: str | None = None
    next_term: str | None = None
    is_zaoch_or_dist: bool | None = None

    @model_validator(mode="after")
    def valid_periods(self) -> Self:
        for start, end in (
            (self.starts_on, self.ends_on),
            (self.exams_start_on, self.exams_end_on),
        ):
            if start is not None and end is not None and start > end:
                raise ValueError("Invalid schedule period.")
        return self


class AnnouncementGroup(DirectoryItem):
    zaoch_or_dist: bool | None = None


class AnnouncementRoom(DirectoryItem):
    building_number: str
    auditory_type: str


class Announcement(ScheduleData):
    id: Identifier
    employee: str
    content: str
    date: date
    employee_departments: list[str]
    groups: list[AnnouncementGroup]
    url_id: str | None = None
    auditory: AnnouncementRoom | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    repeat_group: JsonValue = None


class AnnouncementPage(ScheduleData):
    content: list[Announcement]
    number: Annotated[int, Field(ge=0)]
    size: Annotated[int, Field(gt=0)]
    total_elements: Annotated[int, Field(ge=0)]
    total_pages: Annotated[int, Field(ge=0)]
    last: bool


class UpdateDate(ScheduleData):
    date: date | None


class ScheduleProvider(Protocol):
    def get_group_schedule(self, group_number: str) -> Schedule | None: ...
    def get_teacher_schedule(self, teacher_id: int) -> Schedule | None: ...
    def get_teacher_schedule_by_url_id(self, url_id: str) -> Schedule | None: ...
    def get_teacher_announcements(
        self, teacher_id: int, *, page: int = 0, size: int = 20, date_from: date | None = None
    ) -> AnnouncementPage: ...
    def get_teacher_announcements_by_url_id(
        self, url_id: str, *, page: int = 0, size: int = 20, date_from: date | None = None
    ) -> AnnouncementPage: ...
    def get_department_announcements(self, department_id: int) -> list[Announcement]: ...
    def get_group_update_date(
        self, *, group_number: str | None = None, group_id: int | None = None
    ) -> date | None: ...
    def get_teacher_update_date(
        self, *, teacher_id: int | None = None, url_id: str | None = None
    ) -> date | None: ...
    def get_current_week(self) -> int: ...
