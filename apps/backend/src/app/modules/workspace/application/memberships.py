from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.calendar.application.service import CalendarEventReference, CalendarService
from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.pages import PageMetadata
from app.modules.workspace.application.ports import MembershipRepository
from app.modules.workspace.application.service import WorkspaceService
from app.modules.workspace.domain.membership import Membership, TargetFilter, TargetType
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    Organization,
    OrganizationKind,
    pagination,
)


@dataclass(frozen=True)
class Member:
    membership: Membership
    target: PageMetadata | CalendarEventReference


class MembershipService:
    def __init__(
        self,
        repository: MembershipRepository,
        organizations: WorkspaceService,
        notes: NoteService,
        calendar: CalendarService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.organizations = repository, organizations
        self.notes, self.calendar, self.now = notes, calendar, now

    @staticmethod
    def require_target_type(target_type: TargetType) -> None:
        if target_type not in ("page", "personal", "official"):
            raise InvalidWorkspaceInput()

    def put(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        organization_id: UUID,
        target_type: TargetType,
        target_id: UUID,
    ) -> Membership:
        self.organizations.require_user(user_id, write=True)
        self.organizations.get(user_id, kind, organization_id)
        self.require_target_type(target_type)
        if target_type == "page":
            self.notes.summary(user_id, target_id, active=True)
        else:
            self.calendar.require_link_target(user_id, target_type, target_id)
        return self.repository.put(
            Membership(uuid4(), user_id, organization_id, target_type, target_id, self.now())
        )

    def remove(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        organization_id: UUID,
        target_type: TargetType,
        target_id: UUID,
    ) -> None:
        self.organizations.require_user(user_id, write=True)
        self.organizations.get(user_id, kind, organization_id)
        self.require_target_type(target_type)
        # Owned historical references stay removable after trash or schedule/profile changes.
        self.repository.delete(user_id, organization_id, target_type, target_id)

    def list(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        organization_id: UUID,
        target_type: TargetFilter | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Member]:
        self.organizations.get(user_id, kind, organization_id)
        pagination(limit, offset)
        if target_type not in (None, "page", "personal", "official", "event"):
            raise InvalidWorkspaceInput()
        memberships = self.repository.list(user_id, organization_id, target_type, limit, offset)
        events = self.calendar.linked_event_references(
            user_id,
            tuple(
                (member.target_type, member.target_id)
                for member in memberships
                if member.target_type != "page"
            ),
        )
        # Return reference metadata, including trash/history, without loading page documents.
        return [
            Member(
                member,
                self.notes.summary(user_id, member.target_id)
                if member.target_type == "page"
                else events[(member.target_type, member.target_id)],
            )
            for member in memberships
        ]

    def for_target(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        target_type: TargetType,
        target_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Organization]:
        self.organizations.require_user(user_id)
        self.require_target_type(target_type)
        pagination(limit, offset)
        if kind not in ("collection", "tag"):
            raise InvalidWorkspaceInput()
        if target_type == "page":
            self.notes.summary(user_id, target_id)
        elif not self.repository.has_target(user_id, target_type, target_id):
            self.calendar.require_link_target(user_id, target_type, target_id)
        return self.repository.for_target(user_id, kind, target_type, target_id, limit, offset)
