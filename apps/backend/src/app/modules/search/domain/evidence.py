import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.search.domain.web import public_web_url


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal[
        "page",
        "material",
        "personal",
        "official",
        "record_date",
        "database",
        "database_record",
        "task",
        "web",
    ]
    id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=0)
    title: str = Field(max_length=300)
    locator: str = Field(default="", max_length=256)
    parent_id: str | None = Field(default=None, max_length=128)
    url: str | None = Field(default=None, max_length=2048, exclude_if=lambda value: value is None)
    retrieved_at: datetime | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def web_origin(self):
        if self.source == "web":
            if self.url is None or self.retrieved_at is None or self.retrieved_at.tzinfo is None:
                raise ValueError("Web citations require a URL and retrieval time.")
            public_web_url(self.url)
        elif self.url is not None or self.retrieved_at is not None:
            raise ValueError("Local sources cannot impersonate web citations.")
        return self

    fingerprint: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        exclude_if=lambda value: value is None,
    )


def source_fingerprint(value: object) -> str:
    """Detect changes in source facts that have no monotonic revision column."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
