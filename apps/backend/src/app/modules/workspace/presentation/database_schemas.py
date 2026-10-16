from typing import Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.notes.presentation.schemas import PageSummary
from app.modules.workspace.domain.organization import InvalidWorkspaceInput
from app.modules.workspace.domain.properties import PropertyKind, property_spec
from app.modules.workspace.presentation.schemas import OrganizationCreate


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)


class DatabaseResponse(OrganizationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    schema_version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    trashed_at: AwareDatetime | None


class DatabaseListResponse(BaseModel):
    items: list[DatabaseResponse]
    limit: int
    offset: int


class SchemaVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_schema_version: int = Field(ge=1, le=2**31 - 2, strict=True)


class PropertyOptionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100, strict=True)


class PropertyCreate(SchemaVersionRequest):
    name: str = Field(min_length=1, max_length=100, strict=True)
    kind: PropertyKind
    options: list[PropertyOptionSchema] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        property_spec(self.name, self.kind, [item.model_dump() for item in self.options])
        return self


class PropertyVersionRequest(SchemaVersionRequest, VersionRequest):
    pass


class PropertyPatch(PropertyVersionRequest):
    name: str | None = Field(default=None, min_length=1, max_length=100, strict=True)
    kind: PropertyKind | None = None
    options: list[PropertyOptionSchema] | None = Field(default=None, max_length=100)
    position: int | None = Field(default=None, ge=0, le=100000, strict=True)

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        changes = self.model_dump(
            exclude_unset=True, exclude={"expected_version", "expected_schema_version"}
        )
        if not changes or any(value is None for value in changes.values()):
            raise InvalidWorkspaceInput()
        return self


class PropertyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    database_id: UUID
    name: str
    kind: PropertyKind
    options: list[PropertyOptionSchema]
    position: int
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    trashed_at: AwareDatetime | None


class PropertyResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    property: PropertyResponse
    schema_version: int


class PropertyListResponse(BaseModel):
    items: list[PropertyResponse]
    schema_version: int


class RecordCreate(SchemaVersionRequest):
    page_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200, strict=True)
    values: dict[str, object] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def validate_page(self) -> Self:
        if (self.page_id is None) == (self.title is None):
            raise InvalidWorkspaceInput()
        return self


class RecordPatch(PropertyVersionRequest):
    values: dict[str, object] = Field(min_length=1, max_length=100)


class RecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    database_id: UUID
    page_id: UUID
    values: dict[str, object]
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    trashed_at: AwareDatetime | None


class RecordResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    record: RecordResponse
    page: PageSummary
    schema_version: int


class RecordListResponse(BaseModel):
    items: list[RecordResultResponse]
    limit: int
    offset: int
