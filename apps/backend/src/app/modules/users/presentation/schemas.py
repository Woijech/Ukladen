from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.users.domain.profile import normalize_profile_changes


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    display_name: str | None = Field(default=None, max_length=100)
    timezone: str = Field(default="UTC", min_length=1)
    locale: Literal["ru", "en"] = "ru"

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_display_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        normalize_profile_changes(self.model_dump(exclude_unset=True))
        return self


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    email_verified_at: AwareDatetime | None
    status: Literal["active", "disabled"]
    display_name: str | None
    timezone: str
    locale: Literal["ru", "en"]
    created_at: AwareDatetime
    updated_at: AwareDatetime
