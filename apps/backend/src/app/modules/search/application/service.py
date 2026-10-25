from typing import Protocol
from uuid import UUID

from app.modules.search.domain.search import InvalidSearchInput, SearchHit, SearchQuery
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable


class SearchSource(Protocol):
    """Read current authorized content and its derived index in the caller's snapshot."""

    def search(self, user_id: UUID, query: SearchQuery) -> list[SearchHit]: ...


class SearchService:
    def __init__(
        self, users: UserAuthentication, pages: SearchSource, materials: SearchSource
    ) -> None:
        self.users, self.pages, self.materials = users, pages, materials

    def search(self, user_id: UUID, query: SearchQuery) -> list[SearchHit]:
        if not self.users.is_active(user_id):
            raise ProfileUnavailable()
        if (
            not isinstance(query.text, str)
            or not 1 <= len(query.text.strip()) <= 200
            or "\x00" in query.text
            or len(query.text.split()) > 30
            or query.source not in (None, "page", "material")
            or query.kind not in (None, "file", "link")
            or query.extension not in (None, "pdf", "docx", "pptx", "txt", "md")
            or type(query.limit) is not int
            or not 1 <= query.limit <= 50
            or type(query.offset) is not int
            or not 0 <= query.offset <= 1000
            or (query.source == "page" and (query.kind or query.extension))
            or (query.kind == "link" and query.extension)
            or any(not isinstance(item, UUID) for item in query.source_ids)
        ):
            raise InvalidSearchInput()
        hits = []
        if query.source != "material" and query.kind is None and query.extension is None:
            hits.extend(self.pages.search(user_id, query))
        if query.source != "page":
            hits.extend(self.materials.search(user_id, query))
        hits.sort(key=lambda item: (-item.score, item.source, str(item.id)))
        return hits[query.offset : query.offset + query.limit]
