from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.notes.infrastructure.orm import PageModel
from app.modules.search.domain.search import SearchHit, SearchQuery
from app.modules.search.infrastructure.expressions import (
    search_query,
    search_snippet,
    search_vector,
)


class SqlAlchemyPageSearch:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search(self, user_id: UUID, query: SearchQuery) -> list[SearchHit]:
        body = func.ukladen_page_search_body(PageModel.document)
        vector, terms = search_vector(PageModel.title, body), search_query(query.text)
        score = func.ts_rank_cd(vector, terms)
        rows = self.session.execute(
            select(
                PageModel.id,
                PageModel.title,
                PageModel.version,
                search_snippet(body, terms).label("snippet"),
                score.label("score"),
            )
            .where(
                PageModel.user_id == user_id, PageModel.trashed_at.is_(None), vector.op("@@")(terms)
            )
            .order_by(score.desc(), PageModel.id)
            .limit(query.offset + query.limit)
        )
        return [
            SearchHit("page", row.id, row.title, row.snippet, float(row.score), row.version)
            for row in rows
        ]
