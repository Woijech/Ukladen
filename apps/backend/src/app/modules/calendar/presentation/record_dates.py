from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DateOnlyValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["date"]
    start: date
    end: date | None


class DateTimeValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["datetime"]
    start: AwareDatetime
    end: AwareDatetime | None


class RecordDateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source: Literal["record_date"]
    database_id: UUID
    record_id: UUID
    page_id: UUID
    property_id: UUID
    title: str
    date: Annotated[DateOnlyValue | DateTimeValue, Field(discriminator="kind")]
    record_version: int
    schema_version: int
    blocks_time: Literal[False]
