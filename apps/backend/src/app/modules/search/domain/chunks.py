import hashlib
import math
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class SourceDocument:
    user_id: UUID
    source: Literal["page", "material"]
    id: UUID
    version: int
    title: str
    text: str
    locations: tuple[tuple[int, int, str], ...] = ()


@dataclass(frozen=True)
class TextChunk:
    start: int
    end: int
    text: str
    locator: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


def checked_vector(values, dimensions: int) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if len(vector) != dimensions or any(not math.isfinite(value) for value in vector):
        raise ValueError("Invalid embedding vector.")
    norm = sum(value * value for value in vector)
    if abs(norm - 1) > 0.01:
        raise ValueError("Expected a normalized embedding vector.")
    return vector
