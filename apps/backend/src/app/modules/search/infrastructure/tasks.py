import logging
from uuid import UUID

from sqlalchemy import exists, select

from app.core.config import get_settings
from app.core.logging import log_failure
from app.db.session import create_database_engine, create_session_factory
from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.search.application.indexing import IndexingService
from app.modules.search.infrastructure.index_models import IndexSourceModel
from app.modules.search.infrastructure.indexing import SqlAlchemyIndexStore
from app.modules.search.infrastructure.runtime import embedding_provider
from app.workers.celery_app import celery_app


class IndexUnavailable(Exception):
    pass


logger = logging.getLogger(__name__)


@celery_app.task(name="search.dispatch", ignore_result=True, store_errors_even_if_ignored=False)
def dispatch() -> None:
    settings = get_settings()
    if settings.search_embeddings_directory is None:
        return
    engine = create_database_engine(settings)
    try:
        sessions = create_session_factory(engine)
        provider = embedding_provider(settings.search_embeddings_directory)
        store = SqlAlchemyIndexStore(sessions, provider.profile)
        store.register()
        with sessions.begin() as database:
            index = IndexSourceModel
            active_page = exists(
                select(PageModel.id).where(
                    PageModel.id == index.source_id,
                    PageModel.user_id == index.user_id,
                    PageModel.trashed_at.is_(None),
                )
            )
            active_material = exists(
                select(MaterialModel.id).where(
                    MaterialModel.id == index.source_id,
                    MaterialModel.user_id == index.user_id,
                    MaterialModel.trashed_at.is_(None),
                )
            )
            expired = list(
                database.scalars(
                    select(index)
                    .where(
                        ((index.source == "page") & ~active_page)
                        | ((index.source == "material") & ~active_material)
                    )
                    .limit(100)
                )
            )
            for row in expired:
                database.delete(row)
        for user_id, source, source_id in store.candidates():
            celery_app.send_task(
                "search.process",
                kwargs={"user_id": str(user_id), "source": source, "source_id": str(source_id)},
                queue="embeddings",
            )
    except Exception as error:
        log_failure(logger, "search.index_task_failed", error)
        raise IndexUnavailable("Search indexing is unavailable.") from None
    finally:
        engine.dispose()


@celery_app.task(
    name="search.process",
    ignore_result=True,
    store_errors_even_if_ignored=False,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process(user_id: str, source: str, source_id: str) -> None:
    settings = get_settings()
    if settings.search_embeddings_directory is None:
        return
    engine = create_database_engine(settings)
    try:
        provider = embedding_provider(settings.search_embeddings_directory)
        store = SqlAlchemyIndexStore(create_session_factory(engine), provider.profile)
        IndexingService(store, provider, provider.count_tokens).process(
            UUID(user_id), source, UUID(source_id)
        )
    except Exception as error:
        log_failure(logger, "search.index_task_failed", error)
        raise IndexUnavailable("Search indexing is unavailable.") from None
    finally:
        engine.dispose()
