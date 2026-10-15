from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modules.materials.domain.materials import (
    MAX_FILE_BYTES,
    USER_STORAGE_BYTES,
    MaterialStatus,
)


class UploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    size_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_FILE_BYTES)]
    title: Annotated[str, Field(strict=True, min_length=1, max_length=200)] | None = None


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    url: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[int, Field(strict=True, ge=1)]


class MaterialPatch(VersionRequest):
    title: Annotated[str, Field(strict=True, min_length=1, max_length=200)] | None = None
    url: Annotated[str, Field(strict=True, min_length=1, max_length=2048)] | None = None


class MaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    kind: Literal["file", "link"]
    filename: str | None
    media_type: str | None
    size_bytes: int
    url: str | None
    status: MaterialStatus
    version: int
    error_code: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    trashed_at: AwareDatetime | None


class MaterialListResponse(BaseModel):
    items: list[MaterialResponse]
    limit: int
    offset: int


class StorageUsageResponse(BaseModel):
    used_bytes: int
    material_count: int
    limit_bytes: int = USER_STORAGE_BYTES
    max_file_bytes: int = MAX_FILE_BYTES
