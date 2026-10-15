from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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
