from dataclasses import asdict
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.materials.domain.materials import Material, MaterialConflict
from app.modules.materials.infrastructure.orm import MaterialModel, MaterialObjectModel


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
