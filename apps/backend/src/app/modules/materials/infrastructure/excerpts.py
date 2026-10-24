from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.search.infrastructure.orm import MaterialSearchDocumentModel


class SqlAlchemyExtractedTextReader:
    def __init__(self, session: Session) -> None:
        self.session = session

    def read(
        self, user_id: UUID, material_id: UUID, offset: int, limit: int
    ) -> tuple[str, int] | None:
        body = MaterialSearchDocumentModel.body
        row = self.session.execute(
            select(func.substr(body, offset + 1, limit), func.char_length(body))
            .join(
                MaterialModel,
                (MaterialModel.id == MaterialSearchDocumentModel.material_id)
                & (MaterialModel.user_id == MaterialSearchDocumentModel.user_id),
            )
            .where(
                MaterialModel.id == material_id,
                MaterialModel.user_id == user_id,
                MaterialModel.trashed_at.is_(None),
                MaterialModel.status == "ready",
                MaterialModel.kind == "file",
            )
        ).one_or_none()
        return (row[0], row[1]) if row else None
