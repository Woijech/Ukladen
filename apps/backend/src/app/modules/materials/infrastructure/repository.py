from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.modules.materials.domain.materials import Material, MaterialConflict
from app.modules.materials.infrastructure.orm import MaterialModel, MaterialObjectModel
from app.modules.users.infrastructure.orm import UserModel


def material_entity(row: MaterialModel) -> Material:
    return Material(**{name: getattr(row, name) for name in Material.__dataclass_fields__})


class SqlAlchemyMaterialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def usage(self, user_id: UUID) -> tuple[int, int]:
        row = self.session.execute(
            select(
                func.coalesce(func.sum(MaterialModel.size_bytes), 0), func.count(MaterialModel.id)
            ).where(MaterialModel.user_id == user_id)
        ).one()
        return int(row[0]), int(row[1])

    def create(self, material: Material) -> None:
        self.session.add(MaterialModel(**asdict(material)))
        self.session.flush()
        if material.kind == "file":
            self.session.add(
                MaterialObjectModel(
                    id=material.id,
                    user_id=material.user_id,
                    material_id=material.id,
                    storage_key=material.storage_key,
                )
            )
            self.session.flush()

    def get(self, user_id: UUID, material_id: UUID) -> Material | None:
        row = self.session.scalar(
            select(MaterialModel)
            .where(MaterialModel.id == material_id, MaterialModel.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        return material_entity(row) if row else None

    def list(self, user_id: UUID, trashed: bool, limit: int, offset: int) -> list[Material]:
        return [
            material_entity(row)
            for row in self.session.scalars(
                select(MaterialModel)
                .where(
                    MaterialModel.user_id == user_id,
                    MaterialModel.trashed_at.is_not(None)
                    if trashed
                    else MaterialModel.trashed_at.is_(None),
                )
                .order_by(MaterialModel.created_at.desc(), MaterialModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def save(self, material: Material, expected_version: int) -> None:
        values = asdict(material)
        for name in ("id", "user_id", "kind", "filename", "media_type", "size_bytes", "created_at"):
            values.pop(name)
        identifier = self.session.scalar(
            update(MaterialModel)
            .where(
                MaterialModel.id == material.id,
                MaterialModel.user_id == material.user_id,
                MaterialModel.version == expected_version,
            )
            .values(**values)
            .returning(MaterialModel.id)
        )
        if identifier is None:
            raise MaterialConflict()

    def system_get(self, material_id: UUID) -> Material | None:
        row = self.session.get(MaterialModel, material_id)
        return material_entity(row) if row else None

    def processing_candidates(self, now: datetime) -> list[UUID]:
        return list(
            self.session.scalars(
                select(MaterialModel.id)
                .join(UserModel, MaterialModel.user_id == UserModel.id)
                .where(
                    UserModel.status == "active",
                    MaterialModel.kind == "file",
                    MaterialModel.trashed_at.is_(None),
                    or_(
                        and_(
                            MaterialModel.status == "pending",
                            or_(
                                MaterialModel.error_code.is_(None),
                                MaterialModel.updated_at <= now - timedelta(seconds=30),
                            ),
                        ),
                        and_(
                            MaterialModel.status == "processing", MaterialModel.lease_until <= now
                        ),
                    ),
                )
                .order_by(MaterialModel.updated_at, MaterialModel.id)
                .limit(20)
            )
        )

    def cleanup_candidates(self, now: datetime) -> list[tuple[UUID, UUID]]:
        return [
            (row.user_id, row.id)
            for row in self.session.execute(
                select(MaterialModel.user_id, MaterialModel.id)
                .where(
                    or_(
                        and_(
                            MaterialModel.status == "uploading",
                            MaterialModel.created_at <= now - timedelta(hours=1),
                        ),
                        MaterialModel.trashed_at <= now - timedelta(days=30),
                    )
                )
                .order_by(MaterialModel.created_at, MaterialModel.id)
                .limit(50)
            )
        ]

    def purge(self, user_id: UUID, material_id: UUID) -> None:
        self.session.execute(
            delete(MaterialModel).where(
                MaterialModel.user_id == user_id, MaterialModel.id == material_id
            )
        )
        self.session.execute(
            delete(MaterialObjectModel).where(
                MaterialObjectModel.id == material_id, MaterialObjectModel.material_id.is_(None)
            )
        )

    def orphan_ids(self) -> list[UUID]:
        return list(
            self.session.scalars(
                select(MaterialObjectModel.id)
                .where(MaterialObjectModel.material_id.is_(None))
                .order_by(MaterialObjectModel.id)
                .limit(50)
            )
        )

    def orphan_key(self, object_id: UUID) -> str | None:
        return self.session.scalar(
            select(MaterialObjectModel.storage_key)
            .where(MaterialObjectModel.id == object_id, MaterialObjectModel.material_id.is_(None))
            .with_for_update()
        )

    def remove_orphan(self, object_id: UUID) -> None:
        self.session.execute(
            delete(MaterialObjectModel).where(
                MaterialObjectModel.id == object_id, MaterialObjectModel.material_id.is_(None)
            )
        )
