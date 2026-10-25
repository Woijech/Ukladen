from dataclasses import asdict
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.materials.domain.extraction import TextLocation
from app.modules.materials.domain.materials import DocumentExtractionError
from app.modules.search.infrastructure.orm import MaterialSearchDocumentModel


class SqlAlchemyMaterialTextIndex:
    def __init__(self, session: Session) -> None:
        self.session = session

    def put(
        self, user_id: UUID, material_id: UUID, body: str, locations: tuple[TextLocation, ...] = ()
    ) -> None:
        try:
            with self.session.begin_nested():
                self.session.execute(
                    insert(MaterialSearchDocumentModel)
                    .values(
                        user_id=user_id,
                        material_id=material_id,
                        body=body,
                        locations=[asdict(item) for item in locations],
                        extraction_revision=1,
                    )
                    .on_conflict_do_update(
                        index_elements=[MaterialSearchDocumentModel.material_id],
                        set_={
                            "body": body,
                            "locations": [asdict(item) for item in locations],
                            "extraction_revision": 1,
                        },
                    )
                )
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) in {"54000", "54001", "22001"}:
                raise DocumentExtractionError("document_limit") from None
            raise
