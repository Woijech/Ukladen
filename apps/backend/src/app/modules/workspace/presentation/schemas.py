from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    OrganizationKind,
    organization_values,
)


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, strict=True)
    color: str | None = Field(default=None, max_length=7, strict=True)

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        organization_values(self.name, self.color)
        return self


class OrganizationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=100, strict=True)
    color: str | None = Field(default=None, max_length=7, strict=True)

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set - {"expected_version"}:
            raise InvalidWorkspaceInput()
        organization_values(
            self.name if "name" in self.model_fields_set else "placeholder", self.color
        )
        return self


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: OrganizationKind
    name: str
    color: str | None
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
    limit: int
    offset: int
