from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.orm import Session

from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.search.domain.search import SearchHit, SearchQuery
from app.modules.search.infrastructure.expressions import (
    search_query,
    search_snippet,
    search_vector,
)
from app.modules.search.infrastructure.orm import MaterialSearchDocumentModel


class SqlAlchemyMaterialSearch:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search(self, user_id: UUID, query: SearchQuery) -> list[SearchHit]:
        terms = search_query(query.text)
        title_vector = search_vector(MaterialModel.title, literal(""))
        body = func.coalesce(
            MaterialSearchDocumentModel.body, MaterialModel.url, MaterialModel.title
        )
        body_vector = search_vector(
            literal(""), func.coalesce(MaterialSearchDocumentModel.body, "")
        )
        score = func.ts_rank_cd(title_vector, terms) + func.ts_rank_cd(body_vector, terms)
        statement = (
            select(
                MaterialModel.id,
                MaterialModel.title,
                MaterialModel.kind,
                MaterialModel.version,
                search_snippet(body, terms).label("snippet"),
                score.label("score"),
            )
            .outerjoin(
                MaterialSearchDocumentModel,
                and_(
                    MaterialSearchDocumentModel.material_id == MaterialModel.id,
                    MaterialSearchDocumentModel.user_id == MaterialModel.user_id,
                    MaterialModel.status == "ready",
                ),
            )
            .where(
                MaterialModel.user_id == user_id,
                MaterialModel.trashed_at.is_(None),
                or_(title_vector.op("@@")(terms), body_vector.op("@@")(terms)),
            )
        )
        if query.kind is not None:
            statement = statement.where(MaterialModel.kind == query.kind)
        if query.source_ids:
            statement = statement.where(MaterialModel.id.in_(query.source_ids))
        if query.extension is not None:
            statement = statement.where(
                func.lower(MaterialModel.filename).endswith("." + query.extension)
            )
        rows = self.session.execute(
            statement.order_by(score.desc(), MaterialModel.id).limit(query.offset + query.limit)
        )
        return [
            SearchHit(
                "material", row.id, row.title, row.snippet, float(row.score), row.version, row.kind
            )
            for row in rows
        ]
