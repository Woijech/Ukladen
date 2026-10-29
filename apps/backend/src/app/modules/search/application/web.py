"""Bounded public evidence contract, independent of the answering model/provider."""

import re
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.modules.search.domain.web import public_web_url


class WebQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    query: str = Field(min_length=1, max_length=512)

    @field_validator("query")
    @classmethod
    def minimal_terms(cls, value: str) -> str:
        if (
            not value.strip()
            or any(ord(c) < 32 for c in value)
            or re.search(
                r"https?://|www\.|@|\b(?:sk-|Bearer |api[_ -]?key|password|secret)", value, re.I
            )
        ):
            raise ValueError("Use public search terms without URLs or credentials.")
        return value.strip()


class WebHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str = Field(max_length=2048)
    title: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(min_length=1, max_length=1200)
    retrieved_at: AwareDatetime

    _public_url = field_validator("url")(public_web_url)


class WebResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok", "not_found", "unavailable", "limit"]
    results: tuple[WebHit, ...] = Field(default=(), max_length=5)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class WebSearch(Protocol):
    def search(self, query: WebQuery) -> WebResult: ...
