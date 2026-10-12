from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.notes.domain.pages import InvalidPageInput, page_text


class PageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200, strict=True)
    content: str = Field(default="", max_length=100000, strict=True)
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_text(self) -> Self:
        page_text(self.title, self.content)
        return self


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)


class PagePatch(VersionRequest):
    title: str | None = Field(default=None, min_length=1, max_length=200, strict=True)
    content: str | None = Field(default=None, max_length=100000, strict=True)
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        changes = self.model_dump(exclude_unset=True, exclude={"expected_version"})
        if not changes or any(changes.get(field, True) is None for field in ("title", "content")):
            raise InvalidPageInput()
        return self


class PageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    parent_id: UUID | None
    title: str
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    trashed_at: AwareDatetime | None
    trash_batch_id: UUID | None


class PageResponse(PageSummary):
    content: str
    content_format: Literal["markdown"] = "markdown"
    content_format_version: Literal[1] = 1


class PageListResponse(BaseModel):
    items: list[PageSummary]
    limit: int
    offset: int
