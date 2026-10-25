from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TextLocation:
    start: int
    end: int
    kind: Literal["page", "slide", "text"] = "text"
    number: int = 1


@dataclass(frozen=True)
class ExtractedText:
    text: str
    locations: tuple[TextLocation, ...] = ()
