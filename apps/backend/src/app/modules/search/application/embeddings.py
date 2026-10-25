from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


class InvalidEmbeddingInput(ValueError):
    pass


class EmbeddingUnavailable(RuntimeError):
    pass


class EmbeddingBusy(EmbeddingUnavailable):
    pass


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str
    model: str
    revision: str
    dimensions: int
    max_tokens: int
    normalized: bool


class EmbeddingProvider(Protocol):
    """Synchronous inference boundary; async callers must offload bounded work."""

    @property
    def profile(self) -> EmbeddingProfile: ...

    def embed(
        self, texts: Sequence[str], *, purpose: Literal["query", "document"]
    ) -> list[tuple[float, ...]]: ...
