from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.workspace.application.ports import OrganizationRepository
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    Organization,
    OrganizationKind,
    WorkspaceNotFound,
    organization_values,
    pagination,
    require_version,
)


class WorkspaceService:
    def __init__(
        self,
        repository: OrganizationRepository,
        users: UserAuthentication,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.users, self.now = repository, users, now

    def require_user(self, user_id: UUID, *, write: bool = False) -> None:
        if not (self.users.lock_active(user_id) if write else self.users.is_active(user_id)):
            raise ProfileUnavailable()

    def get(self, user_id: UUID, kind: OrganizationKind, identifier: UUID) -> Organization:
        self.require_user(user_id)
        if kind not in ("collection", "tag"):
            raise InvalidWorkspaceInput()
        organization = self.repository.get(user_id, kind, identifier)
        if organization is None:
            raise WorkspaceNotFound()
        return organization

    def list(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Organization]:
        self.require_user(user_id)
        pagination(limit, offset)
        if kind not in ("collection", "tag"):
            raise InvalidWorkspaceInput()
        return self.repository.list(user_id, kind, limit, offset)

    def create(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        name: str,
        color: str | None = None,
    ) -> Organization:
        self.require_user(user_id, write=True)
        if kind not in ("collection", "tag"):
            raise InvalidWorkspaceInput()
        name, color = organization_values(name, color)
        now = self.now()
        organization = Organization(uuid4(), user_id, kind, name, color, 1, now, now)
        self.repository.create(organization)
        return organization

    def update(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        identifier: UUID,
        changes: Mapping[str, object],
        expected_version: int,
    ) -> Organization:
        self.require_user(user_id, write=True)
        organization = self.get(user_id, kind, identifier)
        require_version(organization.version, expected_version)
        if not changes or changes.keys() - {"name", "color"}:
            raise InvalidWorkspaceInput()
        name, color = organization_values(
            changes.get("name", organization.name),
            changes.get("color", organization.color),
        )
        updated = replace(
            organization,
            name=name,
            color=color,
            version=organization.version + 1,
            updated_at=self.now(),
        )
        self.repository.save(updated, expected_version)
        return updated

    def delete(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        identifier: UUID,
        expected_version: int,
    ) -> None:
        self.require_user(user_id, write=True)
        organization = self.get(user_id, kind, identifier)
        require_version(organization.version, expected_version)
        self.repository.delete(organization, expected_version)
