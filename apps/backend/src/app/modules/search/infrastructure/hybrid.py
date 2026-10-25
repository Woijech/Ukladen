from collections import defaultdict
from uuid import UUID

from pydantic import JsonValue, ValidationError
from sqlalchemy import and_, cast, func, literal, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.materials.infrastructure.search import SqlAlchemyMaterialSearch
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.notes.infrastructure.search import SqlAlchemyPageSearch
from app.modules.search.application.embeddings import EmbeddingProvider
from app.modules.search.application.evidence import EvidenceResult
from app.modules.search.application.service import SearchService
from app.modules.search.domain.chunks import checked_vector
from app.modules.search.domain.evidence import SourceReference
from app.modules.search.domain.search import SearchQuery
from app.modules.search.infrastructure.expressions import search_query, search_vector
from app.modules.search.infrastructure.index_models import IndexSourceModel, SearchChunkModel
from app.modules.search.infrastructure.indexing import generation_profile
from app.modules.search.infrastructure.vector import Vector
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def current_chunks(user_id: UUID, generation: str):
    chunk, index = SearchChunkModel, IndexSourceModel
    return (
        select(chunk, func.coalesce(PageModel.title, MaterialModel.title).label("title"))
        .join(
            index,
            and_(
                index.user_id == chunk.user_id,
                index.source == chunk.source,
                index.source_id == chunk.source_id,
                index.generation == chunk.generation,
            ),
        )
        .outerjoin(
            PageModel,
            and_(
                chunk.source == "page",
                PageModel.id == chunk.source_id,
                PageModel.user_id == chunk.user_id,
            ),
        )
        .outerjoin(
            MaterialModel,
            and_(
                chunk.source == "material",
                MaterialModel.id == chunk.source_id,
                MaterialModel.user_id == chunk.user_id,
            ),
        )
        .where(
            chunk.user_id == user_id,
            chunk.generation == generation,
            index.status == "ready",
            index.version == chunk.version,
            or_(
                and_(
                    chunk.source == "page",
                    PageModel.trashed_at.is_(None),
                    PageModel.version == chunk.version,
                ),
                and_(
                    chunk.source == "material",
                    MaterialModel.trashed_at.is_(None),
                    MaterialModel.status == "ready",
                    MaterialModel.version == chunk.version,
                ),
            ),
        )
    )


class HybridSearch:
    def __init__(self, sessions: sessionmaker[Session], embeddings: EmbeddingProvider):
        self.sessions, self.embeddings = sessions, embeddings
        self.generation = generation_profile(embeddings.profile)[0]

    def read(self, user_id: UUID, query) -> EvidenceResult:
        # Inference never holds a source transaction. Canonical checks follow inference.
        warning = None
        try:
            vector = checked_vector(
                self.embeddings.embed([query.query], purpose="query")[0],
                self.embeddings.profile.dimensions,
            )
        except Exception:
            vector, warning = None, "semantic_unavailable_lexical_fallback"
        with self.sessions.begin() as database:
            database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            users = SqlAlchemyUserAuthentication(database)
            lexical = SearchService(
                users, SqlAlchemyPageSearch(database), SqlAlchemyMaterialSearch(database)
            ).search(
                user_id,
                SearchQuery(
                    text=query.query, source=query.source, source_ids=query.source_ids, limit=50
                ),
            )
            scores, values = defaultdict(float), {}
            for rank, hit in enumerate(lexical, 1):
                key = (hit.source, str(hit.id), "lexical")
                scores[key] += 1 / (60 + rank)
                values[key] = (
                    hit.snippet,
                    SourceReference(
                        source=hit.source,
                        id=str(hit.id),
                        version=hit.version,
                        title=hit.title,
                        locator="search_snippet",
                    ),
                )
            statement = current_chunks(user_id, self.generation)
            if query.source:
                statement = statement.where(SearchChunkModel.source == query.source)
            if query.source_ids:
                statement = statement.where(SearchChunkModel.source_id.in_(query.source_ids))
            vector_order = (
                SearchChunkModel.embedding.op("<=>", return_type=None)(
                    cast(literal(vector, type_=Vector()), Vector())
                )
                if vector
                else None
            )
            terms = search_query(query.query)
            lexical_rank = func.ts_rank_cd(search_vector(literal(""), SearchChunkModel.body), terms)
            lists = [
                database.execute(
                    statement.where(
                        search_vector(literal(""), SearchChunkModel.body).op("@@")(terms)
                    )
                    .order_by(
                        lexical_rank.desc(),
                        SearchChunkModel.source,
                        SearchChunkModel.source_id,
                        SearchChunkModel.number,
                    )
                    .limit(50)
                ).all()
            ]
            if vector_order is not None:
                lists.append(
                    database.execute(
                        statement.order_by(
                            vector_order,
                            SearchChunkModel.source,
                            SearchChunkModel.source_id,
                            SearchChunkModel.number,
                        ).limit(50)
                    ).all()
                )
            for candidates in lists:
                for rank, (chunk, title) in enumerate(candidates, 1):
                    key = (chunk.source, str(chunk.source_id), str(chunk.number))
                    scores[key] += 1 / (60 + rank)
                    values[key] = (
                        chunk.body,
                        SourceReference(
                            source="page" if chunk.source == "page" else "material",
                            id=str(chunk.source_id),
                            version=chunk.version,
                            title=title,
                            locator=chunk.locator,
                        ),
                    )
            ordered = sorted(scores, key=lambda key: (-scores[key], key))
            # Prefer located chunks over duplicate document-level lexical previews.
            located = {(key[0], key[1]) for key in ordered if key[2] != "lexical"}
            ordered = [key for key in ordered if key[2] != "lexical" or key[:2] not in located]
            selected = ordered[query.offset : query.offset + query.limit]
            data, references = [], []
            for key in selected:
                body, reference = values[key]
                data.append(
                    {
                        "snippet": body.encode()[:600].decode("utf-8", errors="ignore"),
                        "source": reference.source,
                        "id": reference.id,
                        "locator": reference.locator,
                    }
                )
                references.append(reference)
            warnings = ["snippets_are_not_full_sources"]
            if warning:
                warnings.append(warning)
            incomplete = False
            for kind, model in (("page", PageModel), ("material", MaterialModel)):
                if query.source and query.source != kind:
                    continue
                ready = (
                    select(IndexSourceModel.source_id)
                    .where(
                        IndexSourceModel.user_id == user_id,
                        IndexSourceModel.source == kind,
                        IndexSourceModel.source_id == model.id,
                        IndexSourceModel.generation == self.generation,
                        IndexSourceModel.version == model.version,
                        IndexSourceModel.status == "ready",
                    )
                    .exists()
                )
                missing = select(model.id).where(
                    model.user_id == user_id, model.trashed_at.is_(None), ~ready
                )
                if kind == "material":
                    missing = missing.where(MaterialModel.kind == "file")
                if query.source_ids:
                    missing = missing.where(model.id.in_(query.source_ids))
                incomplete |= database.scalar(missing.limit(1)) is not None
            if incomplete:
                warnings.append("index_pending_or_unavailable")
            for preview_bytes in (600, 200, 0):
                bounded_data: list[JsonValue] = [
                    dict(
                        item,
                        snippet=item["snippet"]
                        .encode()[:preview_bytes]
                        .decode("utf-8", errors="ignore"),
                    )
                    for item in data
                ]
                try:
                    return EvidenceResult(
                        data=bounded_data,
                        sources=tuple(references),
                        coverage="partial",
                        warnings=tuple(warnings),
                        next_offset=query.offset + len(selected)
                        if query.offset + len(selected) < len(ordered)
                        else None,
                    )
                except ValidationError:
                    if preview_bytes == 0:
                        raise
            raise AssertionError("Evidence construction did not finish.")
