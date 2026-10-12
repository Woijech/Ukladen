from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from app.modules.calendar.application.service import CalendarEventReference, CalendarService
from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.pages import PageMetadata
from app.modules.relations.application.ports import CalendarPageLinks
from app.modules.relations.domain.links import (
    CalendarPageLink,
    InvalidRelationInput,
    RelationNotFound,
)


@dataclass(frozen=True)
class LinkedPage:
    link: CalendarPageLink
    page: PageMetadata


@dataclass(frozen=True)
class LinkedEvent:
    link: CalendarPageLink
    event: CalendarEventReference


class RelationService:
    def __init__(
        self,
        repository: CalendarPageLinks,
        notes: NoteService,
        calendar: CalendarService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.notes, self.calendar, self.now = repository, notes, calendar, now

    @staticmethod
    def _pagination(limit: int, offset: int) -> None:
        if (
            type(limit) is not int
            or type(offset) is not int
            or not 1 <= limit <= 200
            or not 0 <= offset <= 2**31 - 1
        ):
            raise InvalidRelationInput()

    def link(
        self,
        user_id: UUID,
        source: Literal["personal", "official"],
        event_id: UUID,
        page_id: UUID,
    ) -> LinkedPage:
        self.notes.require_user(user_id, write=True)
        page = self.notes.summary(user_id, page_id, active=True)
        self.calendar.require_link_target(user_id, source, event_id)
        link = self.repository.put(
            CalendarPageLink(uuid4(), user_id, page.id, source, event_id, self.now())
        )
        return LinkedPage(link, page)

    def create_linked_page(
        self,
        user_id: UUID,
        source: Literal["personal", "official"],
        event_id: UUID,
        title: str,
        content: str = "",
        parent_id: UUID | None = None,
        document: Mapping[str, object] | None = None,
    ) -> LinkedPage:
        self.notes.require_user(user_id, write=True)
        self.calendar.require_link_target(user_id, source, event_id)
        page = self.notes.create(user_id, title, content, parent_id, document=document)
        return self.link(user_id, source, event_id, page.id)

    def unlink(
        self,
        user_id: UUID,
        source: Literal["personal", "official"],
        event_id: UUID,
        page_id: UUID,
    ) -> None:
        self.notes.require_user(user_id, write=True)
        # Historical links remain removable after the source or academic context changes.
        if not self.repository.delete(user_id, source, event_id, page_id):
            raise RelationNotFound()

    def event_pages(
        self,
        user_id: UUID,
        source: Literal["personal", "official"],
        event_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LinkedPage]:
        self.notes.require_user(user_id)
        self._pagination(limit, offset)
        links = self.repository.for_event(user_id, source, event_id, limit, offset)
        if not links and (
            offset == 0 or not self.repository.for_event(user_id, source, event_id, 1, 0)
        ):
            self.calendar.require_link_target(user_id, source, event_id)
        return [LinkedPage(link, self.notes.summary(user_id, link.page_id)) for link in links]

    def page_events(
        self,
        user_id: UUID,
        page_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LinkedEvent]:
        self.notes.summary(user_id, page_id)
        self._pagination(limit, offset)
        links = self.repository.for_page(user_id, page_id, limit, offset)
        events = self.calendar.linked_event_references(
            user_id, tuple((link.source, link.event_id) for link in links)
        )
        return [LinkedEvent(link, events[(link.source, link.event_id)]) for link in links]
