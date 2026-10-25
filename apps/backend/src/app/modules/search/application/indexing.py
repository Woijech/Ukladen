from collections.abc import Callable
from dataclasses import dataclass
from itertools import batched
from typing import Protocol
from uuid import UUID

from app.modules.search.application.chunking import chunks
from app.modules.search.application.embeddings import EmbeddingProvider
from app.modules.search.domain.chunks import SourceDocument, TextChunk, checked_vector


@dataclass(frozen=True)
class IndexWork:
    document: SourceDocument
    generation: str
    lease: UUID


class IndexStore(Protocol):
    def claim(self, user_id: UUID, source: str, source_id: UUID) -> IndexWork | None: ...
    def publish(
        self,
        work: IndexWork,
        start: int,
        batch: tuple[TextChunk, ...],
        vectors: list[tuple[float, ...]],
    ) -> bool: ...
    def finish(self, work: IndexWork) -> bool: ...
    def fail(self, work: IndexWork) -> None: ...


class IndexingService:
    def __init__(
        self, store: IndexStore, embeddings: EmbeddingProvider, count_tokens: Callable[[str], int]
    ):
        self.store, self.embeddings, self.count_tokens = store, embeddings, count_tokens

    def process(self, user_id: UUID, source: str, source_id: UUID) -> None:
        work = self.store.claim(user_id, source, source_id)
        if work is None:
            return
        try:
            number = 0
            for batch in batched(chunks(work.document, self.count_tokens), 4, strict=False):
                vectors = self.embeddings.embed([item.text for item in batch], purpose="document")
                if len(vectors) != len(batch):
                    raise ValueError("Embedding batch length mismatch.")
                vectors = [
                    checked_vector(vector, self.embeddings.profile.dimensions) for vector in vectors
                ]
                if not self.store.publish(work, number, batch, vectors):
                    return
                number += len(batch)
            self.store.finish(work)
        except Exception:
            self.store.fail(work)
            raise
