from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.notes.domain.blocks import parse_document

Text = Annotated[str, Field(strict=True, max_length=100000)]


class BlockSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID


class TextBlockSchema(BlockSchema):
    type: Literal["text"]
    text: Text
    text_format: Literal["plain", "markdown"] = "plain"


class HeadingBlockSchema(BlockSchema):
    type: Literal["heading"]
    text: Text
    level: int = Field(ge=1, le=6, strict=True)


class ListBlockSchema(BlockSchema):
    type: Literal["list"]
    items: list[Text] = Field(min_length=1, max_length=1000)
    style: Literal["bulleted", "numbered"] = "bulleted"


class CheckboxBlockSchema(BlockSchema):
    type: Literal["checkbox"]
    text: Text
    checked: bool = Field(default=False, strict=True)


class LinkBlockSchema(BlockSchema):
    type: Literal["link"]
    text: Text
    url: str = Field(min_length=1, max_length=2048, strict=True)


BlockValue = Annotated[
    TextBlockSchema | HeadingBlockSchema | ListBlockSchema | CheckboxBlockSchema | LinkBlockSchema,
    Field(discriminator="type"),
]


class DocumentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    schema_version: int = Field(ge=1, le=1, strict=True)
    blocks: list[BlockValue] = Field(max_length=1000)

    @model_validator(mode="after")
    def validate_document(self) -> Self:
        parse_document(self.model_dump())
        return self


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, le=2**31 - 2, strict=True)


class DocumentPut(VersionRequest):
    document: DocumentSchema


class DocumentResponse(BaseModel):
    page_id: UUID
    version: int
    document: DocumentSchema
