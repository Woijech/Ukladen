from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from app.modules.calendar.application.service import CalendarResult, CalendarService
from app.modules.workspace.application.ports import CalendarViewRepository, MembershipRepository
from app.modules.workspace.application.service import WorkspaceService
from app.modules.workspace.domain.calendar_views import (
    CalendarView,
    CalendarViewSource,
    view_values,
)
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    WorkspaceConflict,
    WorkspaceNotFound,
    pagination,
    require_version,
)


class CalendarViewService:
    def __init__(
        self,
        repository: CalendarViewRepository,
        organizations: WorkspaceService,
        memberships: MembershipRepository,
        calendar: CalendarService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.organizations = repository, organizations
        self.memberships, self.calendar, self.now = memberships, calendar, now

    def get(self, user_id: UUID, identifier: UUID) -> CalendarView:
        self.organizations.require_user(user_id)
        view = self.repository.get(user_id, identifier)
        if view is None:
            raise WorkspaceNotFound()
        return view

    def list(self, user_id: UUID, limit: int = 100, offset: int = 0) -> list[CalendarView]:
        self.organizations.require_user(user_id)
        pagination(limit, offset)
        return self.repository.list(user_id, limit, offset)

    def require_sources(self, user_id: UUID, sources: tuple[CalendarViewSource, ...]) -> None:
        for source in sources:
            for identifier in source.collection_ids:
                self.organizations.get(user_id, "collection", identifier)
            for identifier in source.tag_ids:
                self.organizations.get(user_id, "tag", identifier)

    def create(self, user_id: UUID, values: Mapping[str, object]) -> CalendarView:
        self.organizations.require_user(user_id, write=True)
        normalized = view_values(values)
        self.require_sources(user_id, normalized["sources"])
        now = self.now()
        view = CalendarView(
            id=uuid4(), user_id=user_id, version=1, created_at=now, updated_at=now, **normalized
        )
        self.repository.create(view)
        return view

    def update(
        self, user_id: UUID, identifier: UUID, changes: Mapping[str, object], expected_version: int
    ) -> CalendarView:
        self.organizations.require_user(user_id, write=True)
        view = self.get(user_id, identifier)
        require_version(view.version, expected_version)
        if not changes or changes.keys() - {
            "name",
            "color",
            "sources",
            "layout",
            "sort_order",
            "include_hidden",
        }:
            raise InvalidWorkspaceInput()
        stored = asdict(view)
        current = {
            field: stored[field]
            for field in ("name", "color", "sources", "layout", "sort_order", "include_hidden")
        }
        normalized = view_values(current | dict(changes))
        self.require_sources(user_id, normalized["sources"])
        updated = replace(view, **normalized, version=view.version + 1, updated_at=self.now())
        self.repository.save(updated, expected_version)
        return updated

    def delete(self, user_id: UUID, identifier: UUID, expected_version: int) -> None:
        self.organizations.require_user(user_id, write=True)
        view = self.get(user_id, identifier)
        require_version(view.version, expected_version)
        self.repository.delete(view, expected_version)

    def events(
        self, user_id: UUID, identifier: UUID, date_from: date, date_to: date
    ) -> CalendarResult:
        view = self.get(user_id, identifier)
        try:
            self.require_sources(user_id, view.sources)
        except WorkspaceNotFound:
            # A deleted filter must never turn a restricted view into an unrestricted one.
            raise WorkspaceConflict() from None
        result = self.calendar.get_calendar(
            user_id, date_from, date_to, include_hidden=view.include_hidden
        )
        organization_ids = tuple(
            {
                identifier
                for source in view.sources
                for identifier in (*source.collection_ids, *source.tag_ids)
            }
        )
        memberships = (
            self.memberships.event_organizations(
                user_id,
                organization_ids,
                tuple(item.source_event_id for item in result.events if item.source == "personal"),
                tuple(item.source_event_id for item in result.events if item.source == "official"),
            )
            if organization_ids
            else {}
        )
        sources = {source.source: source for source in view.sources}
        events = []
        for event in result.events:
            source = sources.get(event.source)
            if source is None:
                continue
            assigned = memberships.get((event.source, event.source_event_id), set())
            if (not source.collection_ids or assigned.intersection(source.collection_ids)) and (
                not source.tag_ids or assigned.intersection(source.tag_ids)
            ):
                events.append(event)
        events.sort(key=lambda item: (item.starts_at, item.id), reverse=view.sort_order == "desc")
        return replace(result, events=events)
