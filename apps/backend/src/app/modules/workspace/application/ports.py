from typing import Protocol
from uuid import UUID

from app.modules.workspace.domain.membership import Membership, TargetFilter, TargetType
from app.modules.workspace.domain.organization import Organization, OrganizationKind


class OrganizationRepository(Protocol):
    def get(
        self, user_id: UUID, kind: OrganizationKind, identifier: UUID
    ) -> Organization | None: ...
    def list(
        self, user_id: UUID, kind: OrganizationKind, limit: int, offset: int
    ) -> list[Organization]: ...
    def create(self, organization: Organization) -> None: ...
    def save(self, organization: Organization, expected_version: int) -> None: ...
    def delete(self, organization: Organization, expected_version: int) -> None: ...


class MembershipRepository(Protocol):
    def put(self, membership: Membership) -> Membership: ...
    def delete(
        self, user_id: UUID, organization_id: UUID, target_type: TargetType, target_id: UUID
    ) -> None: ...
    def list(
        self,
        user_id: UUID,
        organization_id: UUID,
        target_type: TargetFilter | None,
        limit: int,
        offset: int,
    ) -> list[Membership]: ...
    def has_target(self, user_id: UUID, target_type: TargetType, target_id: UUID) -> bool: ...
    def for_target(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        target_type: TargetType,
        target_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Organization]: ...
