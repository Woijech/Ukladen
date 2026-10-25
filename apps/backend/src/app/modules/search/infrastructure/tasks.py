from uuid import UUID

from sqlalchemy import delete, exists, select

from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.search.application.indexing import IndexingService
from app.modules.search.infrastructure.index_models import IndexSourceModel
from app.modules.search.infrastructure.indexing import SqlAlchemyIndexStore
from app.modules.search.infrastructure.orm import MaterialSearchDocumentModel
from app.modules.search.infrastructure.runtime import embedding_provider
from app.workers.celery_app import celery_app


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
            # Existing PDFs/slides are re-extracted once to obtain real locations.
            old = database.scalars(
                select(MaterialModel)
                .join(
                    MaterialSearchDocumentModel,
                    MaterialSearchDocumentModel.material_id == MaterialModel.id,
                )
                .where(
                    MaterialModel.status == "ready",
                    MaterialModel.trashed_at.is_(None),
                    MaterialSearchDocumentModel.extraction_revision == 0,
                )
                .limit(100)
                .with_for_update(of=MaterialModel, skip_locked=True)
            )
            for material in old:
                material.status, material.attempts = "pending", 0
                material.version += 1
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
            database.execute(
                delete(index).where(
                    ((index.source == "page") & ~active_page)
                    | ((index.source == "material") & ~active_material)
                )
            )
        for user_id, source, source_id in store.candidates():
            celery_app.send_task(
                "search.process",
                kwargs={"user_id": str(user_id), "source": source, "source_id": str(source_id)},
                queue="embeddings",
            )
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
    finally:
        engine.dispose()
