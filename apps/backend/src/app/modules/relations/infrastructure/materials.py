from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.relations.infrastructure.orm import PageMaterialLinkModel


class SqlAlchemyPageMaterialLinks:
    def __init__(self, session: Session) -> None:
        self.session = session

    def put(self, user_id: UUID, page_id: UUID, material_id: UUID) -> None:
        self.session.execute(
            insert(PageMaterialLinkModel)
            .values(user_id=user_id, page_id=page_id, material_id=material_id)
            .on_conflict_do_nothing(
                index_elements=[PageMaterialLinkModel.page_id, PageMaterialLinkModel.material_id]
            )
        )

    def delete(self, user_id: UUID, page_id: UUID, material_id: UUID) -> bool:
        return (
            self.session.scalar(
                delete(PageMaterialLinkModel)
                .where(
                    PageMaterialLinkModel.user_id == user_id,
                    PageMaterialLinkModel.page_id == page_id,
                    PageMaterialLinkModel.material_id == material_id,
                )
                .returning(PageMaterialLinkModel.page_id)
            )
            is not None
        )

    def for_page(self, user_id: UUID, page_id: UUID, limit: int, offset: int) -> list[UUID]:
        return list(
            self.session.scalars(
                select(PageMaterialLinkModel.material_id)
                .where(
                    PageMaterialLinkModel.user_id == user_id,
                    PageMaterialLinkModel.page_id == page_id,
                )
                .order_by(PageMaterialLinkModel.material_id)
                .limit(limit)
                .offset(offset)
            )
        )

    def for_material(self, user_id: UUID, material_id: UUID, limit: int, offset: int) -> list[UUID]:
        return list(
            self.session.scalars(
                select(PageMaterialLinkModel.page_id)
                .where(
                    PageMaterialLinkModel.user_id == user_id,
                    PageMaterialLinkModel.material_id == material_id,
                )
                .order_by(PageMaterialLinkModel.page_id)
                .limit(limit)
                .offset(offset)
            )
        )
