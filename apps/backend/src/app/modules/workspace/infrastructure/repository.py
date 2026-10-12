from dataclasses import asdict
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.modules.workspace.domain.organization import (
    Organization,
    OrganizationKind,
    WorkspaceConflict,
)
from app.modules.workspace.infrastructure.orm import OrganizationModel


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
