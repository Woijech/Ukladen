from functools import lru_cache
from pathlib import Path

from app.integrations.embeddings.e5 import E5EmbeddingProvider


@lru_cache(maxsize=1)
def embedding_provider(directory: Path) -> E5EmbeddingProvider:
    return E5EmbeddingProvider(directory)
