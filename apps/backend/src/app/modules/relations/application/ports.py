from typing import Literal, Protocol
from uuid import UUID

from app.modules.relations.domain.links import CalendarPageLink


class CalendarPageLinks(Protocol):
    """Typed owner-scoped links; the caller owns the transaction."""

    def put(self, link: CalendarPageLink) -> CalendarPageLink: ...
    def delete(
        self, user_id: UUID, source: Literal["personal", "official"], event_id: UUID, page_id: UUID
    ) -> bool: ...
    def for_event(
        self,
        user_id: UUID,
        source: Literal["personal", "official"],
        event_id: UUID,
        limit: int,
        offset: int,
    ) -> list[CalendarPageLink]: ...
    def for_page(
        self, user_id: UUID, page_id: UUID, limit: int, offset: int
    ) -> list[CalendarPageLink]: ...
