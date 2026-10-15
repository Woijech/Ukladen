from dataclasses import asdict
from typing import cast
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.workspace.domain.calendar_views import EventSource
from app.modules.workspace.domain.membership import Membership, TargetFilter, TargetType
from app.modules.workspace.domain.organization import (
    Organization,
    OrganizationKind,
    WorkspaceConflict,
)
from app.modules.workspace.infrastructure.orm import MembershipModel, OrganizationModel


def organization_entity(row: OrganizationModel) -> Organization:
    return Organization(
        row.id,
        row.user_id,
        cast(OrganizationKind, row.kind),
        row.name,
        row.color,
        row.version,
        row.created_at,
        row.updated_at,
    )


class SqlAlchemyOrganizations:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: UUID, kind: OrganizationKind, identifier: UUID) -> Organization | None:
        row = self.session.scalar(
            select(OrganizationModel)
            .where(
                OrganizationModel.user_id == user_id,
                OrganizationModel.kind == kind,
                OrganizationModel.id == identifier,
            )
            .execution_options(populate_existing=True)
        )
        return organization_entity(row) if row else None

    def list(
        self, user_id: UUID, kind: OrganizationKind, limit: int, offset: int
    ) -> list[Organization]:
        return [
            organization_entity(row)
            for row in self.session.scalars(
                select(OrganizationModel)
                .where(
                    OrganizationModel.user_id == user_id,
                    OrganizationModel.kind == kind,
                )
                .order_by(OrganizationModel.created_at, OrganizationModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def create(self, organization: Organization) -> None:
        self.session.add(OrganizationModel(**asdict(organization)))
        self.session.flush()

    def save(self, organization: Organization, expected_version: int) -> None:
        values = asdict(organization)
        for field in ("id", "user_id", "kind"):
            values.pop(field)
        identifier = self.session.scalar(
            update(OrganizationModel)
            .where(
                OrganizationModel.id == organization.id,
                OrganizationModel.user_id == organization.user_id,
                OrganizationModel.kind == organization.kind,
                OrganizationModel.version == expected_version,
            )
            .values(**values)
            .returning(OrganizationModel.id)
        )
        if identifier is None:
            raise WorkspaceConflict()

    def delete(self, organization: Organization, expected_version: int) -> None:
        identifier = self.session.scalar(
            delete(OrganizationModel)
            .where(
                OrganizationModel.id == organization.id,
                OrganizationModel.user_id == organization.user_id,
                OrganizationModel.kind == organization.kind,
                OrganizationModel.version == expected_version,
            )
            .returning(OrganizationModel.id)
        )
        if identifier is None:
            raise WorkspaceConflict()


def target_column(target_type: TargetType) -> InstrumentedAttribute[UUID | None]:
    return {
        "page": MembershipModel.page_id,
        "personal": MembershipModel.personal_event_id,
        "official": MembershipModel.official_event_id,
    }[target_type]


def membership_entity(row: MembershipModel) -> Membership:
    if row.page_id is not None:
        target_type, target_id = "page", row.page_id
    elif row.personal_event_id is not None:
        target_type, target_id = "personal", row.personal_event_id
    else:
        target_type, target_id = "official", row.official_event_id
    assert target_id is not None
    return Membership(
        row.id,
        row.user_id,
        row.organization_id,
        cast(TargetType, target_type),
        target_id,
        row.created_at,
    )


class SqlAlchemyMemberships:
    def __init__(self, session: Session) -> None:
        self.session = session

    def event_organizations(
        self,
        user_id: UUID,
        organization_ids: tuple[UUID, ...],
        personal_ids: tuple[UUID, ...],
        official_ids: tuple[UUID, ...],
    ) -> dict[tuple[EventSource, UUID], set[UUID]]:
        result: dict[tuple[EventSource, UUID], set[UUID]] = {}
        for row in self.session.scalars(
            select(MembershipModel).where(
                MembershipModel.user_id == user_id,
                MembershipModel.organization_id.in_(organization_ids),
                or_(
                    MembershipModel.personal_event_id.in_(personal_ids),
                    MembershipModel.official_event_id.in_(official_ids),
                ),
            )
        ):
            member = membership_entity(row)
            if member.target_type != "page":
                result.setdefault((member.target_type, member.target_id), set()).add(
                    member.organization_id
                )
        return result

    def put(self, membership: Membership) -> Membership:
        column = target_column(membership.target_type)
        self.session.execute(
            insert(MembershipModel)
            .values(
                id=membership.id,
                user_id=membership.user_id,
                organization_id=membership.organization_id,
                created_at=membership.created_at,
                **{column.key: membership.target_id},
            )
            .on_conflict_do_nothing(index_elements=[MembershipModel.organization_id, column])
        )
        row = self.session.scalar(
            select(MembershipModel).where(
                MembershipModel.user_id == membership.user_id,
                MembershipModel.organization_id == membership.organization_id,
                column == membership.target_id,
            )
        )
        assert row is not None
        return membership_entity(row)

    def delete(
        self, user_id: UUID, organization_id: UUID, target_type: TargetType, target_id: UUID
    ) -> None:
        self.session.execute(
            delete(MembershipModel).where(
                MembershipModel.user_id == user_id,
                MembershipModel.organization_id == organization_id,
                target_column(target_type) == target_id,
            )
        )

    def list(
        self,
        user_id: UUID,
        organization_id: UUID,
        target_type: TargetFilter | None,
        limit: int,
        offset: int,
    ) -> list[Membership]:
        query = select(MembershipModel).where(
            MembershipModel.user_id == user_id, MembershipModel.organization_id == organization_id
        )
        if target_type == "event":
            query = query.where(MembershipModel.page_id.is_(None))
        elif target_type is not None:
            query = query.where(target_column(target_type).is_not(None))
        return [
            membership_entity(row)
            for row in self.session.scalars(
                query.order_by(MembershipModel.created_at, MembershipModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def has_target(self, user_id: UUID, target_type: TargetType, target_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(MembershipModel.id)
                .where(MembershipModel.user_id == user_id, target_column(target_type) == target_id)
                .limit(1)
            )
            is not None
        )

    def for_target(
        self,
        user_id: UUID,
        kind: OrganizationKind,
        target_type: TargetType,
        target_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Organization]:
        return [
            organization_entity(row)
            for row in self.session.scalars(
                select(OrganizationModel)
                .join(MembershipModel, MembershipModel.organization_id == OrganizationModel.id)
                .where(
                    MembershipModel.user_id == user_id,
                    OrganizationModel.user_id == user_id,
                    OrganizationModel.kind == kind,
                    target_column(target_type) == target_id,
                )
                .order_by(OrganizationModel.created_at, OrganizationModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]
