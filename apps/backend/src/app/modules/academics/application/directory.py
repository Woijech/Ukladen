from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Identifier = Annotated[int, Field(gt=0, le=2**63 - 1)]


class DirectoryRecord(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, from_attributes=True)

    id: Identifier


class DirectoryItem(DirectoryRecord):
    name: str = Field(min_length=1)


class Faculty(DirectoryItem):
    abbrev: str


class Department(Faculty):
    url_id: str | None = None


class Speciality(Faculty):
    education_form: DirectoryItem
    faculty_id: Identifier
    code: str


class RoomDepartment(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    id_department: Identifier
    name: str
    abbrev: str
    name_and_abbrev: str


class Room(DirectoryItem):
    note: str | None
    capacity: Annotated[int, Field(ge=0)] | None
    auditory_type: Faculty
    building_number: DirectoryItem
    department: RoomDepartment | None


class Teacher(DirectoryRecord):
    url_id: str = Field(min_length=1)
    first_name: str
    last_name: str
    middle_name: str | None
    degree: str | None
    rank: str | None
    degree_abbrev: str | None = None
    photo_link: str | None = None
    calendar_id: str | None = None
    departments: list[str] | None = None
    fio: str | None = None
    email: str | None = None
    job_positions: JsonValue = None
    chief: bool | None = None


class UniversityEntityNotFound(Exception):
    pass


class InvalidUniversityRequest(ValueError):
    pass


class UniversityDirectory(Protocol):
    def list_teachers(self) -> list[Teacher]: ...
    def get_teacher(self, teacher_id: int) -> Teacher: ...
    def list_faculties(self) -> list[Faculty]: ...
    def list_departments(self) -> list[Department]: ...
    def list_specialities(self) -> list[Speciality]: ...
    def list_rooms(self) -> list[Room]: ...
