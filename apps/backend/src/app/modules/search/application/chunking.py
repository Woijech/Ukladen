from collections.abc import Callable, Iterator

from app.modules.search.domain.chunks import SourceDocument, TextChunk

CHUNKER_REVISION = "token-window-v1-384-64"


def chunks(document: SourceDocument, count_tokens: Callable[[str], int]) -> Iterator[TextChunk]:
    """Keep canonical character offsets and real locations; never truncate model input."""
    ranges = document.locations or ((0, len(document.text), "text"),)
    for left, right, locator in ranges:
        start = left
        while start < right:
            low, high = start + 1, min(right, start + 8000)
            if count_tokens(document.text[start:low]) > 384:
                raise ValueError("Tokenizer cannot encode a source character.")
            while low < high:
                middle = (low + high + 1) // 2
                if count_tokens(document.text[start:middle]) <= 384:
                    low = middle
                else:
                    high = middle - 1
            end = low
            text = document.text[start:end]
            if text.strip():
                yield TextChunk(start, end, text, f"{locator};chars:{start}:{end}")
            if end == right:
                break
            overlap = end
            while overlap > start and count_tokens(document.text[overlap - 1 : end]) <= 64:
                overlap -= 1
            start = max(start + 1, overlap)
