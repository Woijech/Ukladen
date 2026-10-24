"""Provider-neutral evidence shared by lexical reads and future hybrid retrieval."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal[
        "page", "material", "personal", "official", "record_date", "database", "database_record"
    ]
    id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=0)
    title: str = Field(max_length=300)
    locator: str = Field(default="", max_length=256)
    parent_id: str | None = Field(default=None, max_length=128)


class EvidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok", "not_found", "not_ready", "unavailable", "invalid", "limit"] = "ok"
    data: JsonValue = None
    sources: tuple[SourceReference, ...] = Field(default=(), max_length=50)
    coverage: Literal["complete", "partial", "none"] = "none"
    warnings: tuple[str, ...] = ()
    next_offset: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(self.model_dump_json().encode("utf-8")) > 16384:
            raise ValueError("Evidence exceeds the 16 KiB result budget.")
        return self
