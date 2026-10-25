from uuid import UUID

from app.modules.search.infrastructure.index_models import IndexSourceModel
from app.modules.search.infrastructure.indexing import generation_profile
from app.modules.search.infrastructure.runtime import embedding_provider
from app.modules.search.infrastructure.source_documents import SqlAlchemySourceDocuments


def index_status(sessions, directory, user_id: UUID, source: str, source_id: UUID) -> dict | None:
    with sessions() as database:
        identity = SqlAlchemySourceDocuments(database).identity(user_id, source, source_id)
        if identity is None:
            return None
        if directory is None:
            return {"status": "unavailable", "version": identity[0]}
        generation = generation_profile(embedding_provider(directory).profile)[0]
        row = database.get(IndexSourceModel, (user_id, source, source_id, generation))
        status = row.status if row and row.version == identity[0] else "pending"
        return {"status": status, "version": identity[0]}
