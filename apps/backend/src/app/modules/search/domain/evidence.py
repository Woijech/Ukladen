import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    fingerprint: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        exclude_if=lambda value: value is None,
    )


def source_fingerprint(value: object) -> str:
    """Detect changes in source facts that have no monotonic revision column."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
